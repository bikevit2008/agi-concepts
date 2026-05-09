"""Contracts layer — Protocol interfaces for all subsystems.

This layer defines the contracts (typing.Protocol) that the rest of the
application depends on. Concrete implementations live elsewhere
(src/persistence/, src/governance/, etc.) and are wired into the application
via dependency injection in src/main.py.

Design rationale:
- Protocols (PEP 544) give us structural typing: any object with the right
  shape satisfies the contract, no inheritance required. This is friendlier
  to Agno-style dataclasses and mocks.
- Each contract has a Null implementation (Null Object Pattern) so the loop
  can run with subsystems disabled (feature-flag gated) without conditionals.
- The application layer (ConsciousnessLoop, ConsciousnessTeam) only knows
  about contracts, never about concrete implementations.
"""

from src.contracts.bus import EventEnvelope, IEventBus, NullEventBus
from src.contracts.cost import (
    CostBudgetExceeded,
    ICostTracker,
    IModelInvoker,
    NullCostTracker,
    TokenUsage,
)
from src.contracts.governance import (
    GovernanceDecision,
    ICircuitBreaker,
    IGovernanceKernel,
    NullCircuitBreaker,
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
    RecalledMemory,
)
from src.contracts.observability import (
    IObservabilityCollector,
    ISpan,
    NullObservabilityCollector,
    NullSpan,
)
from src.contracts.persistence import (
    EventRecord,
    ICheckpoint,
    IEventStore,
    NullCheckpoint,
    NullEventStore,
    Snapshot,
)
from src.contracts.sleep import (
    IMemoryConsolidator,
    ISleepManager,
    NullMemoryConsolidator,
    NullSleepManager,
    SleepPhase,
    WakeState,
)
from src.contracts.tools import (
    IToolRegistry,
    ITool,
    NullToolRegistry,
    ToolCall,
    ToolResult,
)

__all__ = [
    # Bus
    "EventEnvelope",
    "IEventBus",
    "NullEventBus",
    # Cost
    "CostBudgetExceeded",
    "ICostTracker",
    "IModelInvoker",
    "NullCostTracker",
    "TokenUsage",
    # Governance
    "GovernanceDecision",
    "ICircuitBreaker",
    "IGovernanceKernel",
    "NullCircuitBreaker",
    "NullGovernanceKernel",
    "StimulationRequest",
    # Memory
    "IMemoryStore",
    "IProvenanceTracker",
    "MemoryEntry",
    "NullMemoryStore",
    "NullProvenanceTracker",
    "ProvenanceVerdict",
    "RecalledMemory",
    # Observability
    "IObservabilityCollector",
    "ISpan",
    "NullObservabilityCollector",
    "NullSpan",
    # Persistence
    "EventRecord",
    "ICheckpoint",
    "IEventStore",
    "NullCheckpoint",
    "NullEventStore",
    "Snapshot",
    # Sleep
    "IMemoryConsolidator",
    "ISleepManager",
    "NullMemoryConsolidator",
    "NullSleepManager",
    "SleepPhase",
    "WakeState",
    # Tools
    "IToolRegistry",
    "ITool",
    "NullToolRegistry",
    "ToolCall",
    "ToolResult",
]
