# Implementation Plan: AGI Concept v3 → Production MVP
# План внедрения: от простого к сложному, с кворумом на каждом этапе

Версия: `v1-implementation`  
Дата: 2026-05-09  
Основание: AGI_CONCEPT_V3_RU.md + AGI_CONCEPT_V3_EN.md + полный codebase audit

---

## Принципы выполнения

1. **Каждый этап → кворум из 2 сабагентов** (ChatGPT 5.5 xhigh + Claude Opus 4.7 Max)
2. **Каждый этап → Perplexity Sonar Pro research** через curl
3. **Каждый этап → commit** с осмысленным сообщением
4. **Приоритизация: от простого к сложному** (минимальные изменения → новые компоненты)
5. **Критика обязательна**: сабагенты должны жестко проверять друг друга

---

## Этап 0: Подготовка инфраструктуры

**Сложность**: Минимальная  
**Новые файлы**: `pyproject.toml` (добавить deps), директории  
**Описание**: Добавить недостающие зависимости, создать структуру директорий для новых компонентов

### Задачи:
- Добавить `lancedb`, `nats-py`, `rerun-sdk` в pyproject.toml (как optional)
- Создать директории: `src/engine/`, `src/persistence/`, `src/governance/`, `src/bus/`, `src/observability/`, `src/visualization/`, `src/ml/`
- Создать `__init__.py` во всех новых директориях

### Метрика успеха: `pip install -e .` проходит без ошибок

---

## Этап 1: Исправление 4 критических багов

**Сложность**: Низкая (изменения существующего кода, без новой логики)  
**Изменяемые файлы**: `consciousness_loop.py`, `runtime_state.py`, `consciousness_team.py`, `memory.py`  
**Описание**: Исправить баги, найденные кворумом v3, без добавления новых компонентов

### Баги к исправлению:
1. **Tick Interval Scaling Bug** (`consciousness_loop.py:93`): decay масштабировать по dt
2. **Reset-to-Defaults Bug** (`consciousness_loop.py:190-197`): аддитивные deltas + мягкий decay
3. **Unlimited Self-Stimulation** (`consciousness_team.py:249`): per-tick лимит 0.1
4. **Memory Hallucination** (`memory.py`): retrieval-first prompt

### Метрика успеха: Все существующие тесты проходят + нет регрессий

---

## Этап 2: Homeostatic Hysteresis Engine

**Сложность**: Средняя (новый компонент с математикой)  
**Новые файлы**: `src/engine/__init__.py`, `src/engine/homeostatic_hysteresis.py`  
**Изменяемые файлы**: `hysteresis.py` (рефакторинг), `consciousness_loop.py` (wire new engine)  
**Описание**: Bouc-Wen-inspired гомеостатический гистерезис с нелинейным decay и restoration forces

### Компоненты:
- `HysteresisChannel` с setpoint, nonlinear decay, restoration_gain, _hysteretic state
- `HomeostaticHysteresisEngine` — замена текущего HysteresisEngine
- Time-scaled dynamics: все обновления зависят от dt
- Математическая гарантия: restoration_gain ≥ 0.4 → guaranteed escape from saturation

### Метрика успеха: Тесты на стабильность (inject stress=0.9 → recovery < 20 ticks)

---

## Этап 3: Circuit Breakers + Governance Kernel (минимальный)

**Сложность**: Средняя  
**Новые файлы**: `src/engine/circuit_breaker.py`, `src/governance/__init__.py`, `src/governance/kernel.py`  
**Изменяемые файлы**: `consciousness_loop.py` (wire circuit breaker + governance)  
**Описание**: Детекция saturation lock + emergency reset + rate limiting стимуляции

### Компоненты:
- `CircuitBreaker`: saturation counter per channel, emergency trigger при >50 тиков на 1.0
- `GovernanceKernel`: per-tick stimulus cap, per-agent cap, reflection limit
- Интеграция в tick loop: проверка перед каждой стимуляцией

### Метрика успеха: Death spiral детектится и прерывается в течение 100 тиков

---

## Этап 4: SQLite WAL Persistence + Checkpoint/Restore

**Сложность**: Средняя  
**Новые файлы**: `src/persistence/__init__.py`, `src/persistence/event_store.py`, `src/persistence/checkpoint.py`  
**Изменяемые файлы**: `consciousness_loop.py` (checkpoint на каждом тике), `main.py` (graceful shutdown)  
**Описание**: Event sourcing через SQLite WAL, сохранение/восстановление полного состояния

### Компоненты:
- `EventStore`: SQLite с таблицей events, append-only, WAL mode
- `Checkpoint`: сериализация emotional state + message queues + memory
- Graceful shutdown: save checkpoint on SIGTERM/SIGINT
- Restore: загрузка последнего чекпойнта при старте

### Метрика успеха: Перезапуск системы → поведение неотличимо от продолжения (cosine sim >0.9)

---

## Этап 5: Memory Provenance Tracking

**Сложность**: Средняя-Высокая  
**Новые файлы**: `src/persistence/memory_store.py` (LanceDB), `src/persistence/provenance.py`  
**Изменяемые файлы**: `memory.py` (retrieval-first rewrite)  
**Описание**: Retrieval-first архитектура памяти с embedding-based reality check

### Компоненты:
- `MemoryStore` (LanceDB): хранение воспоминаний с эмбеддингами и метаданными
- `ProvenanceTracker`: embedding similarity check между recalled и stored
- Memory agent rewrite: сначала retrieve из LanceDB, потом передать LLM для reflection
- Маркировка: source='recall' vs source='hallucination'

### Метрика успеха: Memory provenance accuracy > 90%

---

## Этап 6: Cost Tracking + Model Fallback Chain

**Сложность**: Низкая-Средняя  
**Новые файлы**: `src/persistence/cost_tracker.py`  
**Изменяемые файлы**: `consciousness_team.py` (fallback logic), `consciousness_loop.py` (cost tracking)  
**Описание**: Учет стоимости токенов + автоматический fallback при отказе модели

### Компоненты:
- `CostTracker`: per-tick token counting, daily budget cap, алерты
- `ModelFallback`: использовать fallback_models из конфига при ошибке
- `--headless` flag: запуск без TUI для production

### Метрика успеха: Cost стабилен (±20% от baseline), отказ модели → автоматический fallback

---

## Этап 7: Rerun Observability + OpenTelemetry

**Сложность**: Высокая (интеграция внешних фреймворков)  
**Новые файлы**: `src/observability/__init__.py`, `src/observability/tracing.py`, `src/observability/spans.py`, `src/observability/metrics.py`, `src/visualization/__init__.py`, `src/visualization/rerun_logger.py`  
**Изменяемые файлы**: `consciousness_loop.py` (instrument), `consciousness_team.py` (instrument)  
**Описание**: Полный tracing каждого thought cycle + real-time visualization через Rerun

### Компоненты:
- **RerunLogger**: real-time визуализация emotional state trajectory в PAD space, hysteresis curves, agent message stream
- **OpenTelemetry**: spans для каждого agent tick, span links для inter-agent messages, span attributes = emotional state
- **Metrics**: экспорт MTTDS, recovery time, provenance accuracy, cost stability
- Feature flag: `observability_enabled` (можно выключить для экономии)

### Метрика успеха: Rerun viewer показывает real-time состояние, OTel трейсы reconstructable

---

## Этап 8: NATS Event Bus + Typed Messages

**Сложность**: Высокая (асинхронная распределенная архитектура)  
**Новые файлы**: `src/bus/__init__.py`, `src/bus/message_bus.py`, `src/bus/event_types.py`  
**Изменяемые файлы**: `consciousness_team.py` (переход на event-driven), `consciousness_loop.py` (wire bus)  
**Описание**: Типизированная событийная шина на NATS JetStream для inter-agent коммуникации

### Компоненты:
- `TypedMessageBus`: publish/subscribe с JSON Schema валидацией
- `EventType`: PerceptionOutput, EmotionOutput, MemoryOutput, PlanningOutput, ReflectionOutput, StateSnapshot, HysteresisUpdate
- JetStream для persistence и replay событий

### Метрика успеха: Все агенты коммуницируют через шину, replay reconstructs state

---

## Этап 9: Sleep/Recovery Modes

**Сложность**: Высокая  
**Новые файлы**: `src/engine/sleep_manager.py`, `src/engine/circadian.py`, `src/engine/memory_consolidator.py`  
**Изменяемые файлы**: `consciousness_loop.py` (sleep mode integration)  
**Описание**: Автономный вход в sleep mode, консолидация памяти, восстановление

### Компоненты:
- `SleepManager`: оркестрация sleep/recovery
- `CircadianOscillator`: циркадный ритм (~6 часов активности → sleep)
- `MemoryConsolidator`: replay, clustering, strengthening, pruning
- NREM-like + REM-like фазы сна

### Метрика успеха: После sleep mode система восстанавливается до baseline

---

## Этап 10: Tools/World Interfaces

**Сложность**: Очень высокая (безопасность, sandboxing)  
**Новые файлы**: `src/tools/tool_registry.py`, `src/tools/web_search.py`, `src/tools/code_executor.py`  
**Описание**: Внешние инструменты с capability-gated доступом

---

## Приоритетный порядок выполнения

```
Этап 0 → Этап 1 → Этап 2 → Этап 3 → Этап 4 → Этап 5 → Этап 6 → Этап 7 → Этап 8 → Этап 9 → Этап 10
  ↑        ↑        ↑        ↑        ↑        ↑        ↑        ↑        ↑        ↑        ↑
  инфра    баги     матем    защита   хранилище память   $        Rerun    шина     сон      tools
```

## Текущий статус

| Этап | Статус | Коммит | Дата |
|------|--------|--------|------|
| 0 | ✅ done | b0445b2 | 2026-05-09 |
| 1 | ✅ done | 9fed620 | 2026-05-09 |
| 2 | ✅ done | 58dedb2 | 2026-05-09 |
| 3 | ✅ done | f220dce | 2026-05-09 |
| 4 | ✅ done | 5d76b2f | 2026-05-09 |
| 5 | ✅ done | 80f4551 | 2026-05-09 |
| 6 | ✅ done | 719da01 | 2026-05-09 |
| 7 | ✅ done | 8cb05c9 | 2026-05-09 |
| 8 | ✅ done | fac3631 | 2026-05-09 |
| 9 | ✅ done | (prev) | 2026-05-09 |
| 10 | ✅ done | e77d087 | 2026-05-09 |
| 11 | ✅ done | (this) | 2026-05-09 | Constitutional Governance Kernel (YAML + 7 policies) |

## Архитектурный слой контрактов

В дополнение к 10 этапам выше, добавлен слой `src/contracts/` —
typing.Protocol-интерфейсы для всех подсистем (persistence, memory,
cost, governance, observability, bus, sleep, tools). Каждый контракт
имеет Null-реализацию (Null Object Pattern), так что loop / team всегда
получают валидную зависимость даже когда подсистема выключена флагом.