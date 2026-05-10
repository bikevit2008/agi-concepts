from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

import structlog

from src.agents.base import EmotionState, MemoryResult, PerceptionResult, PlanningResult, ReflectionResult
from src.agents.emotion import create_emotion_agent
from src.agents.memory import create_memory_agent
from src.agents.perception import create_perception_agent
from src.agents.planning import create_planning_agent
from src.agents.reflection import create_reflection_agent
from src.config.flags import FeatureFlags
from src.config.settings import ModelSettings
from src.contracts.cost import ICostTracker, NullCostTracker
from src.contracts.governance import (
    GovernanceDecision,
    IGovernanceKernel,
    NullGovernanceKernel,
    StimulationRequest,
)
from src.contracts.memory import (
    IMemoryStore,
    IProvenanceTracker,
    MemoryEntry,
    NullMemoryStore,
    NullProvenanceTracker,
    ProvenanceVerdict,
)
from src.core.event_bus import EventBus
from src.core.hysteresis import HysteresisEngine
from src.core.runtime_state import RuntimeState
from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine
from src.persistence.cost_aware_agent import AgnoModelInvoker

logger = structlog.get_logger("consciousness.team")


@dataclass
class ConsciousnessTeam:
    """Orchestrates the four consciousness agents in a pipeline:
    Perception -> Emotion -> Memory -> Planning

    Uses RuntimeState + HysteresisEngine to create embodied effects:
    emotions literally change how the system thinks.
    """

    model_settings: ModelSettings
    runtime_state: RuntimeState
    hysteresis: HysteresisEngine | HomeostaticHysteresisEngine
    flags: FeatureFlags
    event_bus: EventBus

    # Stage 3 — governance kernel (Null impl when disabled, allows everything)
    governance: IGovernanceKernel = field(default_factory=NullGovernanceKernel)

    # Stage 5 — vector memory store + provenance tracker (Null impl when disabled)
    memory_store: IMemoryStore = field(default_factory=NullMemoryStore)
    provenance_tracker: IProvenanceTracker = field(default_factory=NullProvenanceTracker)

    # Stage 6 — cost tracker (Null impl when disabled)
    cost_tracker: ICostTracker = field(default_factory=NullCostTracker)

    # Internal state
    memories: List[str] = field(default_factory=list)
    emotion_history: List[Dict[str, Any]] = field(default_factory=list)
    state_journal: List[Dict[str, Any]] = field(default_factory=list)
    current_tick: int = 0  # set externally by ConsciousnessLoop for governance traceability
    _agents_created: bool = False

    def __post_init__(self) -> None:
        agent_model_settings = (
            self.model_settings
            if self.flags.model_fallback_enabled
            else replace(self.model_settings, fallback_models=[])
        )
        self._perception_agent = create_perception_agent(agent_model_settings)
        self._emotion_agent = create_emotion_agent(agent_model_settings)
        self._memory_agent = create_memory_agent(agent_model_settings)
        self._planning_agent = create_planning_agent(agent_model_settings)
        self._reflection_agent = create_reflection_agent(agent_model_settings)
        self._agents_created = True

    def record_state_snapshot(self) -> None:
        """Record current state to journal for reflection context."""
        snapshot = {
            "runtime": self.runtime_state.to_dict(),
            "active_channels": self.hysteresis.get_active_channels(),
            "channel_values": {n: round(c.value, 3) for n, c in self.hysteresis.channels.items()},
        }
        self.state_journal.append(snapshot)
        if len(self.state_journal) > 30:
            self.state_journal = self.state_journal[-30:]

    def _run_agent(self, agent: Any, prompt: str, agent_name: str) -> Any:
        tracker = self.cost_tracker if self.flags.cost_tracking_enabled else NullCostTracker()
        result = AgnoModelInvoker(
            agent=agent,
            cost_tracker=tracker,
            agent_name=agent_name,
            primary_model_id=self.model_settings.id,
        ).invoke(prompt, agent_name=agent_name, tick=self.current_tick)
        if not result.success:
            raise RuntimeError(result.error or "model invocation failed")
        return result.raw

    def _stored_memory_count(self) -> int:
        if self.flags.memory_store_enabled:
            try:
                return self.memory_store.count()
            except Exception as e:
                logger.warning("memory_count_failed", error=str(e))
        return len(self.memories)

    def _stored_memory_contents(self, limit: int) -> List[str]:
        if self.flags.memory_store_enabled:
            try:
                return [entry.content for entry in self.memory_store.all_entries()][-limit:]
            except Exception as e:
                logger.warning("memory_contents_failed", error=str(e))
        return self.memories[-limit:]

    def snapshot_memories(self) -> List[str]:
        if self.flags.memory_store_enabled:
            try:
                return [entry.content for entry in self.memory_store.all_entries()]
            except Exception as e:
                logger.warning("memory_snapshot_failed", error=str(e))
        return list(self.memories)

    def restore_memories(self, memories: List[str]) -> None:
        self.memories = list(memories)
        if not self.flags.memory_store_enabled:
            return
        try:
            if self.memory_store.count() > 0:
                return
            for content in memories:
                self.memory_store.store(
                    MemoryEntry(
                        id="",
                        content=content,
                        source="checkpoint_restore",
                        confidence=0.7,
                    )
                )
        except Exception as e:
            logger.warning("memory_restore_failed", error=str(e))

    def _gated_stimulate(
        self,
        agent: str,
        channel: str,
        intensity: float,
        reason: Optional[str] = None,
    ) -> GovernanceDecision:
        """Apply a hysteresis stimulation through the governance kernel.

        Negative intensity (self-soothing) is always allowed.
        Positive intensity passes through governance caps.
        """
        if intensity == 0:
            return GovernanceDecision.ALLOW
        request = StimulationRequest(
            agent=agent,
            channel=channel,
            intensity=intensity,
            tick=self.current_tick,
            reason=reason,
        )
        decision = self.governance.authorize(request)
        if decision == GovernanceDecision.ALLOW:
            self.hysteresis.stimulate(channel, intensity)
            self.governance.record(request)
        else:
            logger.info(
                "team_stimulation_denied",
                agent=agent,
                channel=channel,
                intensity=round(intensity, 4),
                decision=decision.value,
                reason=reason,
            )
        return decision

    def _update_agent_states(self) -> None:
        """Push current runtime state into agent session_states."""
        rt = self.runtime_state
        active = self.hysteresis.get_active_channels()

        # Perception
        self._perception_agent.session_state = {
            "energy_level": rt.energy_level,
            "attention_focus": rt.attention_focus,
            "bandwidth": rt.bandwidth,
        }

        # Emotion
        recent_emotions = self.emotion_history[-5:] if self.emotion_history else []
        self._emotion_agent.session_state = {
            "temperature": rt.temperature,
            "energy_level": rt.energy_level,
            "emotion_history": recent_emotions,
            "active_channels": active,
        }

        # Memory
        self._memory_agent.session_state = {
            "bandwidth": rt.bandwidth,
            "attention_focus": rt.attention_focus,
            "energy_level": rt.energy_level,
            "stored_memories": self._stored_memory_contents(20),
            "store_size": self._stored_memory_count(),
            "pre_retrieved_memories": [],  # populated per-call by process_stimulus_sync
        }

        # Planning
        self._planning_agent.session_state = {
            "temperature": rt.temperature,
            "context_window": rt.context_window,
            "energy_level": rt.energy_level,
            "attention_focus": rt.attention_focus,
            "current_perception": "",
            "current_emotion": "",
            "recalled_memories": [],
            "active_channels": active,
        }

    def process_stimulus_sync(self, stimulus: str) -> Dict[str, Any]:
        """Run the full consciousness pipeline for a given stimulus (blocking).

        Called from asyncio.to_thread() to not block the Textual event loop.
        Pipeline: Perception -> Emotion -> Memory -> Planning
        Each step feeds into the next. Disabled agents are skipped.
        """
        self._update_agent_states()
        result: Dict[str, Any] = {"stimulus": stimulus}

        # 1. Perception
        perception_data: Optional[PerceptionResult] = None
        if self.flags.perception_enabled:
            try:
                logger.info("agent_run", agent="Perception", stimulus=stimulus[:100])
                self._perception_agent.model.temperature = self.runtime_state.temperature
                resp = self._run_agent(self._perception_agent, stimulus, "Perception")
                if resp and resp.content is not None:
                    perception_data = _parse_structured(resp.content, PerceptionResult)
                    result["perception"] = perception_data.model_dump() if perception_data else str(resp.content)
            except Exception as e:
                logger.error("agent_error", agent="Perception", error=str(e))
                result["perception_error"] = str(e)

        # 2. Emotion
        emotion_data: Optional[EmotionState] = None
        if self.flags.emotion_enabled:
            try:
                emotion_input = _build_emotion_input(stimulus, perception_data)
                self._emotion_agent.session_state["active_channels"] = self.hysteresis.get_active_channels()
                logger.info("agent_run", agent="Emotion")
                resp = self._run_agent(self._emotion_agent, emotion_input, "Emotion")
                if resp and resp.content is not None:
                    emotion_data = _parse_structured(resp.content, EmotionState)
                    if not emotion_data:
                        raw = str(resp.content)[:200]
                        logger.warning("emotion_parse_fallback", raw=raw)
                        emotion_data = _infer_emotion_from_text(str(resp.content))
                    result["emotion"] = emotion_data.model_dump()
                    self.emotion_history.append(result["emotion"])
                    if len(self.emotion_history) > 50:
                        self.emotion_history = self.emotion_history[-50:]
                    # Stimulate hysteresis channels through governance kernel
                    applied: Dict[str, float] = {}
                    denied: Dict[str, str] = {}
                    for channel, intensity in emotion_data.hysteresis_stimuli.items():
                        decision = self._gated_stimulate(
                            agent="Emotion",
                            channel=channel,
                            intensity=intensity,
                            reason=f"emotion={emotion_data.primary_emotion}",
                        )
                        if decision == GovernanceDecision.ALLOW:
                            applied[channel] = intensity
                        else:
                            denied[channel] = decision.value
                    logger.info(
                        "hysteresis_stimulated",
                        applied=applied,
                        denied=denied or None,
                    )
            except Exception as e:
                logger.error("agent_error", agent="Emotion", error=str(e))
                result["emotion_error"] = str(e)

        # 3. Memory — Stage 5: retrieval-first architecture.
        # Step 3a: Pre-retrieve real candidates from the vector store.
        # Step 3b: Inject ONLY real candidates into the LLM context.
        # Step 3c: Verify the LLM's "recalled" outputs against the store.
        memory_data: Optional[MemoryResult] = None
        if self.flags.memory_enabled:
            try:
                # 3a — vector retrieval before LLM call
                pre_retrieved: List[MemoryEntry] = []
                if self.flags.memory_store_enabled and self.memory_store.count() > 0:
                    recalled = self.memory_store.retrieve(
                        query=stimulus,
                        limit=5,
                        min_similarity=0.0,
                    )
                    pre_retrieved = [
                        r.entry for r in recalled
                        if r.verdict in (ProvenanceVerdict.REAL, ProvenanceVerdict.UNCERTAIN)
                    ]
                    self._memory_agent.session_state["pre_retrieved_memories"] = [
                        {
                            "content": e.content,
                            "source": e.source,
                            "similarity": next(
                                (r.similarity for r in recalled if r.entry.id == e.id), 0.0
                            ),
                        }
                        for e in pre_retrieved
                    ]

                # 3b — run the agent (it sees ONLY real, retrieved candidates)
                memory_input = _build_memory_input(
                    stimulus, perception_data, emotion_data, pre_retrieved
                )
                logger.info(
                    "agent_run",
                    agent="Memory",
                    pre_retrieved=len(pre_retrieved),
                    store_size=self._stored_memory_count(),
                )
                resp = self._run_agent(self._memory_agent, memory_input, "Memory")

                if resp and resp.content is not None:
                    memory_data = _parse_structured(resp.content, MemoryResult)
                    if memory_data:
                        # 3c — provenance verification on agent's claimed recalls
                        if (
                            self.flags.provenance_tracking_enabled
                            and memory_data.recalled_memories
                        ):
                            store_entries = self.memory_store.all_entries()
                            verified: List[str] = []
                            verdicts: Dict[str, str] = {}
                            for recalled_text in memory_data.recalled_memories:
                                v = self.provenance_tracker.verify_recall(
                                    recalled_text, store_entries
                                )
                                verdicts[recalled_text[:80]] = v.value
                                if v in (ProvenanceVerdict.REAL, ProvenanceVerdict.UNCERTAIN):
                                    verified.append(recalled_text)
                            memory_data.recalled_memories = verified
                            if verdicts:
                                result["memory_provenance"] = verdicts

                        # Post-processing: legacy hallucination guard (Bug #4 belt + suspenders)
                        stored_count = self._stored_memory_count()
                        if memory_data.recalled_memories and stored_count == 0 and not pre_retrieved:
                            logger.warning(
                                "memory_hallucination_detected",
                                recalled_count=len(memory_data.recalled_memories),
                                stored_count=stored_count,
                            )
                            memory_data.recalled_memories = []

                        # Persist new memory in BOTH the legacy list and the vector store
                        if memory_data.new_memory_to_store:
                            self.memories.append(memory_data.new_memory_to_store)
                            if self.flags.memory_store_enabled:
                                self.memory_store.store(
                                    MemoryEntry(
                                        id="",  # store auto-generates
                                        content=memory_data.new_memory_to_store,
                                        source="memory_agent",
                                        emotion_associations=memory_data.emotional_associations or {},
                                        confidence=float(memory_data.relevance_score or 0.5),
                                    )
                                )

                        result["memory"] = memory_data.model_dump()
            except Exception as e:
                logger.error("agent_error", agent="Memory", error=str(e))
                result["memory_error"] = str(e)

        # 4. Planning
        if self.flags.planning_enabled:
            try:
                planning_input = _build_planning_input(stimulus, perception_data, emotion_data, memory_data)
                self._planning_agent.session_state.update({
                    "current_perception": json.dumps(perception_data.model_dump()) if perception_data else "",
                    "current_emotion": json.dumps(emotion_data.model_dump()) if emotion_data else "",
                    "recalled_memories": memory_data.recalled_memories if memory_data else [],
                    "active_channels": self.hysteresis.get_active_channels(),
                })
                self._planning_agent.model.temperature = self.runtime_state.temperature
                # max_tokens driven by vitality (energy + bandwidth)
                # Suppressed (low vitality) → short answers (min 64)
                # Euphoric (high vitality >1.0) → verbose, expansive (up to 2048)
                vitality = (self.runtime_state.energy_level + self.runtime_state.bandwidth) / 2.0
                max_tok = max(64, min(2048, int(1024 * vitality)))
                self._planning_agent.model.max_tokens = max_tok
                logger.info("agent_run", agent="Planning", max_tokens=max_tok, vitality=round(vitality, 3))
                resp = self._run_agent(self._planning_agent, planning_input, "Planning")
                if resp and resp.content is not None:
                    planning_data = _parse_structured(resp.content, PlanningResult)
                    if planning_data:
                        result["planning"] = planning_data.model_dump()
                        result["response"] = planning_data.response
                    else:
                        result["response"] = resp.content
            except Exception as e:
                logger.error("agent_error", agent="Planning", error=str(e))
                result["planning_error"] = str(e)
                result["response"] = f"[Planning error: {e}]"

        if "response" not in result:
            result["response"] = "[No active agents produced a response]"

        return result

    def reflect_sync(self) -> Optional[Dict[str, Any]]:
        """Run self-reflection — inner monologue without external stimulus.

        Called periodically during idle ticks.
        Returns reflection result or None on failure.
        """
        rt = self.runtime_state
        active = self.hysteresis.get_active_channels()

        # Update reflection agent state
        recent_emotions = self.emotion_history[-5:] if self.emotion_history else []
        recent_journal = self.state_journal[-10:] if self.state_journal else []

        self._reflection_agent.session_state = {
            "temperature": rt.temperature,
            "context_window": rt.context_window,
            "energy_level": rt.energy_level,
            "attention_focus": rt.attention_focus,
            "bandwidth": rt.bandwidth,
            "processing_latency": rt.processing_latency,
            "active_channels": active,
            "emotion_history": recent_emotions,
            "state_journal": recent_journal,
        }

        self._reflection_agent.model.temperature = min(2.0, rt.temperature + 0.2)

        try:
            logger.info("agent_run", agent="Reflection")
            resp = self._run_agent(
                self._reflection_agent,
                "Reflect on your current internal state.",
                "Reflection",
            )
            if resp and resp.content is not None:
                reflection = _parse_structured(resp.content, ReflectionResult)
                if not reflection:
                    raw = str(resp.content)
                    reflection = ReflectionResult(
                        thought=raw[:500],
                        mood_assessment="unknown",
                    )
                result = reflection.model_dump()
                # Self-stimulate hysteresis channels through the governance kernel.
                # Negative (self-soothing) stimulation is always allowed; positive
                # stimulation is capped by `reflection_self_stim_cap`.
                if reflection.hysteresis_stimuli:
                    applied: Dict[str, float] = {}
                    denied: Dict[str, str] = {}
                    for channel, intensity in reflection.hysteresis_stimuli.items():
                        decision = self._gated_stimulate(
                            agent="Reflection",
                            channel=channel,
                            intensity=intensity,
                            reason="self_reflection",
                        )
                        if decision == GovernanceDecision.ALLOW:
                            applied[channel] = intensity
                        else:
                            denied[channel] = decision.value
                    logger.info(
                        "reflection_self_stimulated",
                        applied=applied,
                        denied=denied or None,
                    )
                logger.info("reflection_complete", thought=reflection.thought[:100])
                return result
        except Exception as e:
            logger.error("agent_error", agent="Reflection", error=str(e))
        return None

    def spontaneous_thought_sync(self) -> Optional[Dict[str, Any]]:
        """Generate a spontaneous thought — autonomous thinking without stimulus.

        Uses Planning agent with internal context to produce a free-form thought.
        """
        rt = self.runtime_state
        active = self.hysteresis.get_active_channels()
        recent_journal = self.state_journal[-5:] if self.state_journal else []
        recent_emotions = self.emotion_history[-3:] if self.emotion_history else []

        self._planning_agent.session_state.update({
            "temperature": rt.temperature,
            "context_window": rt.context_window,
            "energy_level": rt.energy_level,
            "attention_focus": rt.attention_focus,
            "current_perception": "",
            "current_emotion": json.dumps(recent_emotions) if recent_emotions else "",
            "recalled_memories": self._stored_memory_contents(5),
            "active_channels": active,
        })

        self._planning_agent.model.temperature = min(2.0, rt.temperature + 0.3)
        vitality = (rt.energy_level + rt.bandwidth) / 2.0
        self._planning_agent.model.max_tokens = max(64, min(512, int(512 * vitality)))

        prompt = (
            "У тебя нет внешнего стимула. Подумай о чём хочешь.\n"
            f"Твоё текущее состояние: energy={rt.energy_level:.2f}, stress_channels={active}\n"
            f"Недавний журнал: {json.dumps(recent_journal, default=str)[:300]}\n"
            "Сгенерируй свободную мысль — о чём ты сейчас думаешь?"
        )

        try:
            logger.info("agent_run", agent="SpontaneousThought")
            resp = self._run_agent(self._planning_agent, prompt, "SpontaneousThought")
            if resp and resp.content is not None:
                thought_data = _parse_structured(resp.content, PlanningResult)
                if thought_data:
                    result = thought_data.model_dump()
                    result["_type"] = "spontaneous_thought"
                    logger.info("spontaneous_thought", thought=thought_data.response[:100])
                    return result
                else:
                    content = str(resp.content)[:500]
                    logger.info("spontaneous_thought", thought=content[:100])
                    return {"response": content, "_type": "spontaneous_thought"}
        except Exception as e:
            logger.error("agent_error", agent="SpontaneousThought", error=str(e))
        return None


def _parse_structured(content: Any, model_class: type) -> Any:
    """Try to parse structured output from agent response.

    Handles:
    - Already-parsed Pydantic model (from Agno output_schema)
    - Dict (from Agno structured output)
    - Raw JSON string
    - Markdown-wrapped JSON (```json...```)
    - Partial JSON in text
    """
    if content is None:
        return None

    # Already the right type (Agno parsed it via output_schema)
    if isinstance(content, model_class):
        return content

    # Dict from Agno
    if isinstance(content, dict):
        try:
            return model_class(**content)
        except (TypeError, ValueError):
            pass

    # BaseModel but wrong type — extract dict
    from pydantic import BaseModel
    if isinstance(content, BaseModel):
        try:
            return model_class(**content.model_dump())
        except (TypeError, ValueError):
            pass

    # String — try JSON parsing
    if isinstance(content, str):
        text = content.strip()
        for candidate in _extract_json_candidates(text):
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return model_class(**data)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

    return None


def _extract_json_candidates(text: str) -> list[str]:
    """Extract possible JSON strings from text, handling markdown code blocks."""
    import re

    candidates = []

    # 1. Try the whole text as JSON
    candidates.append(text)

    # 2. Extract from ```json ... ``` or ``` ... ``` blocks
    for match in re.finditer(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL):
        candidates.append(match.group(1).strip())

    # 3. Find first { ... last } (greedy brace match)
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidates.append(text[first_brace : last_brace + 1])

    return candidates


def _infer_emotion_from_text(content: str) -> EmotionState:
    """Fallback: infer emotion from unstructured agent response text."""
    text_lower = content.lower()

    # Simple keyword-based emotion inference
    stress_words = ["стресс", "тревог", "напряж", "угроз", "опасн", "конфликт", "агресс",
                    "оскорбл", "провокац", "негатив", "злость", "гнев", "ярость", "бесит"]
    euphoria_words = ["радость", "счастье", "восторг", "прекрасн", "замечательн", "отлично",
                      "позитив", "удоволь", "приятн", "восхищ"]
    pain_words = ["боль", "обид", "ранен", "травм", "потер", "утрат", "отвержен", "тоск"]
    fatigue_words = ["устал", "скуч", "однообразн", "монотон", "повтор", "лень"]
    calm_words = ["привет", "здравств", "спокой", "нейтральн", "обычн"]

    hysteresis: dict[str, float] = {}
    valence = 0.0
    intensity = 0.3
    primary = "calm"

    stress_score = sum(1 for w in stress_words if w in text_lower)
    euphoria_score = sum(1 for w in euphoria_words if w in text_lower)
    pain_score = sum(1 for w in pain_words if w in text_lower)
    fatigue_score = sum(1 for w in fatigue_words if w in text_lower)

    if stress_score > 0:
        intensity = min(1.0, 0.3 + stress_score * 0.2)
        hysteresis["stress"] = min(1.0, stress_score * 0.4)
        valence = -0.6
        primary = "anger"
    if pain_score > 0:
        intensity = max(intensity, min(1.0, 0.3 + pain_score * 0.2))
        hysteresis["pain"] = min(1.0, pain_score * 0.4)
        valence = min(valence, -0.5)
        primary = "sadness"
    if euphoria_score > 0:
        intensity = max(intensity, min(1.0, 0.3 + euphoria_score * 0.2))
        hysteresis["euphoria"] = min(1.0, euphoria_score * 0.4)
        valence = 0.7
        primary = "joy"
    if fatigue_score > 0:
        hysteresis["fatigue"] = min(1.0, fatigue_score * 0.3)

    return EmotionState(
        primary_emotion=primary,
        intensity=intensity,
        valence=valence,
        arousal=intensity,
        hysteresis_stimuli=hysteresis,
        reasoning=f"Inferred from text (keywords matched: stress={stress_score}, euphoria={euphoria_score}, pain={pain_score}, fatigue={fatigue_score})",
    )


def _build_emotion_input(stimulus: str, perception: Optional[PerceptionResult]) -> str:
    parts = [f"Stimulus: {stimulus}"]
    if perception:
        parts.append(f"Perception: type={perception.stimulus_type}, valence={perception.emotional_valence}, urgency={perception.urgency}")
        parts.append(f"Context: {', '.join(perception.relevant_context)}")
    return "\n".join(parts)


def _build_memory_input(
    stimulus: str,
    perception: Optional[PerceptionResult],
    emotion: Optional[EmotionState],
    pre_retrieved: Optional[List[MemoryEntry]] = None,
) -> str:
    parts = [f"Stimulus: {stimulus}"]
    if perception:
        parts.append(f"Perception summary: {perception.content_summary}")
    if emotion:
        parts.append(f"Current emotion: {emotion.primary_emotion} (intensity={emotion.intensity})")
    if pre_retrieved:
        parts.append("=== Pre-retrieved REAL stored memories (use ONLY these for recall) ===")
        for i, entry in enumerate(pre_retrieved, 1):
            parts.append(f"  [{i}] (source={entry.source}) {entry.content}")
    else:
        parts.append("=== Pre-retrieved memories: NONE — do NOT fabricate; recalled_memories must be empty list ===")
    return "\n".join(parts)


def _build_planning_input(
    stimulus: str,
    perception: Optional[PerceptionResult],
    emotion: Optional[EmotionState],
    memory: Optional[MemoryResult],
) -> str:
    parts = [f"Original stimulus: {stimulus}"]
    if perception:
        parts.append(f"Perception: {perception.content_summary} (urgency={perception.urgency})")
    if emotion:
        parts.append(f"Emotional state: {emotion.primary_emotion} (intensity={emotion.intensity}, valence={emotion.valence})")
        if emotion.reasoning:
            parts.append(f"Emotional reasoning: {emotion.reasoning}")
    if memory:
        if memory.recalled_memories:
            parts.append(f"Recalled memories: {'; '.join(memory.recalled_memories)}")
        if memory.new_memory_to_store:
            parts.append(f"New memory forming: {memory.new_memory_to_store}")
    parts.append("Please synthesize all of the above and produce a coherent response.")
    return "\n".join(parts)
