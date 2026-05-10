# Production Reference Stack for AGI / Context Runtime
## Detailed Architecture With Rationale
## April 2026

---

# 0. Goal

Design a production-grade multimodal context / memory runtime for agents / AGI-like systems.

The system must support:

- semantic memory
- episodic memory
- working memory
- procedural memory
- capability graph
- tool permission graph
- multimodal perception memory
- vector recall
- graph traversal
- hypergraph facts
- provenance
- confidence
- contradiction tracking
- branchable persona state
- replayable runtime traces
- Docker Compose deployment
- later Kubernetes migration

---

# 1. Core Design Principle

Do not search for one magical database.

Use layered storage:

1. Hypergraph semantic core
2. Property graph traversal core
3. Multimodal vector layer
4. Versioned state layer
5. Operational metadata store
6. Analytical/evaluation layer
7. Runtime trace/observability layer
8. Multimodal pipeline layer

Each layer has a clear responsibility.

---

# 2. Recommended Stack: Maximum Feature Coverage

## 2.1 Hypergraph Semantic Core

Technology:

TypeDB

Purpose:

- canonical facts
- n-ary relations
- roles
- typed domain model
- inference rules
- complex relation modeling

Why:

TypeDB is the best fit when a "fact" is not a simple edge.

Example fact:

shipment(
  vessel,
  cargo,
  port,
  contract,
  receiver,
  date,
  risk,
  source,
  confidence
)

In a property graph this becomes a relation node.
In TypeDB this is closer to the native model.

Use TypeDB for:

- durable semantic facts
- domain ontology
- role-based relations
- policy facts
- high-confidence memory
- validated inferred knowledge
- compliance-like rules

Do not use TypeDB for:

- raw embeddings
- high-volume vector search
- raw multimodal blob storage
- event logs

---

## 2.2 Property Graph Traversal Layer

Technology options:

Option A:
KuzuDB

Option B:
Neo4j

Option C:
ArcadeDB

Recommended split:

- local-first / embedded / GraphRAG dev: KuzuDB
- mature server / GDS / enterprise graph analytics: Neo4j
- all-in-one multi-model pragmatic stack: ArcadeDB

Purpose:

- Cypher queries
- GraphRAG
- dependency graph
- code graph
- ownership graph
- tool/capability graph
- k-hop traversal
- shortest paths
- centrality
- contextual neighborhood expansion

Use graph layer for:

- "what is connected to this?"
- "what depends on this?"
- "which entities explain this chunk?"
- "what capabilities are available in this state?"
- "what context should be retrieved after vector search?"

Recommended for your case:

KuzuDB for embedded/local experiments.
Neo4j for server/production graph analytics.
ArcadeDB if you want one JVM multi-model engine.

---

## 2.3 Multimodal Vector Layer

Technology options:

Option A:
LanceDB

Option B:
Qdrant

Option C:
pgvector

Option D:
Milvus

Recommended split:

- embedded/local multimodal lakehouse: LanceDB
- production vector service: Qdrant
- boring transactional vector extension: pgvector
- very large vector infra: Milvus

Purpose:

- text embeddings
- image embeddings
- audio embeddings
- video scene embeddings
- chunk embeddings
- entity embeddings
- multi-vector retrieval
- hybrid search
- payload filtering
- reranking integration

Use vector layer for:

- semantic recall
- multimodal search
- nearest neighbor retrieval
- chunk/entity candidates
- prefilter before graph expansion

Recommended for your case:

LanceDB for local-first multimodal development.
Qdrant for Docker/production vector service.
pgvector for small/medium operational embeddings inside Postgres.

---

## 2.4 Versioned State / Persona Layer

Technology options:

Option A:
TerminusDB

Option B:
Dolt

Option C:
LakeFS

Option D:
CozoDB

Recommended:

TerminusDB for versioned document graph / git-for-data.
Dolt for SQL tables with git semantics.
LakeFS for object-store-level dataset versioning.
CozoDB for lightweight embedded time-travel + Datalog memory.

Purpose:

- branch persona
- snapshot memory graph
- diff state
- rollback state
- compare versions
- preserve history
- reproduce old agent context

Use versioned state for:

- persona_v1 vs persona_v2
- experiment branches
- "what did the agent know at commit X?"
- "why did it act differently yesterday?"
- "restore pre-corruption memory state"

Recommended for your case:

TerminusDB as versioned high-level state graph.
LakeFS if multimodal raw datasets live in object storage.
CozoDB if you want embedded reasoning/time-travel experiments.

---

## 2.5 Operational Metadata Store

Technology:

PostgreSQL

Extensions:

- pgvector
- AGE or AgensGraph if needed
- pg_trgm
- full-text search
- TimescaleDB optional
- audit/event tables

Purpose:

- users
- tenants
- projects
- jobs
- runs
- tool registry
- tool calls
- API keys
- permissions
- event sourcing
- lightweight vectors
- queue metadata

Why:

Postgres is the boring, stable backbone.
Even if every fancy layer changes, Postgres remains your source for operational state.

Use Postgres for:

- app state
- transactionally critical state
- API-level metadata
- runtime event log
- job queue metadata
- structured audit tables
- references to external stores

---

## 2.6 Analytical / Evaluation Layer

Technology:

DuckDB

Optional:

- ClickHouse for server-scale analytics
- Parquet
- Iceberg
- Delta Lake
- Lance format

Purpose:

- offline analytics
- retrieval evaluation
- benchmark runs
- feature extraction
- batch joins
- quality dashboards
- local notebooks

Use DuckDB for:

- "which retriever performed better?"
- "what facts were extracted with low confidence?"
- "what embeddings are stale?"
- "what tool produced the most failures?"
- "how did memory quality evolve?"

Use ClickHouse for:

- high-volume traces
- observability
- token/cost/latency analytics
- production event streams

---

## 2.7 Multimodal Pipeline Layer

Technology:

Pixeltable

Alternative / supporting:

- LanceDB
- DuckDB
- dbt
- custom Python ETL

Purpose:

- first-class image/video/audio/doc columns
- computed columns
- incremental transformations
- model output lineage
- embeddings
- captions
- transcripts
- object detection
- scene extraction
- table extraction
- document chunking

Use Pixeltable for:

video → frames → captions → embeddings → vector index
audio → transcript → speaker graph → embeddings
pdf → text/tables/images → chunks → entities → facts
image → objects → scene graph → embeddings

Why:

This is exactly the layer that prevents multimodal ETL from becoming random scripts.

---

## 2.8 Runtime Trace / Observability Layer

Technology options:

Option A:
Postgres event tables

Option B:
ClickHouse

Option C:
OpenTelemetry + SigNoz / Grafana stack

Option D:
Langfuse for LLM traces

Purpose:

- agent tick trace
- model call
- tool call
- tool result
- state diff
- memory write
- retrieval candidates
- reranker scores
- user feedback
- errors
- costs
- latency

Use trace layer for:

- replay
- debugging
- safety audit
- regression testing
- cost control
- observability

Recommended for your context:

Postgres for canonical runtime events.
ClickHouse for high-volume trace analytics.
Langfuse for LLM span inspection.
SigNoz/Grafana for infra + app metrics.

---

# 3. Logical Architecture

## 3.1 High-Level Flow

User / agent input
→ runtime controller
→ working memory
→ retrieval planner
→ vector search
→ graph expansion
→ hypergraph validation
→ provenance filtering
→ context composer
→ model call
→ tool execution
→ event trace
→ memory write
→ versioned state update

---

## 3.2 Data Flow

1. Raw data enters Pixeltable / object storage.
2. Pixeltable computes transcripts, chunks, captions, embeddings.
3. Embeddings go to LanceDB/Qdrant.
4. Extracted entities/relations go to Kuzu/Neo4j.
5. Canonical facts and n-ary relations go to TypeDB.
6. Runtime events go to Postgres/ClickHouse.
7. Versioned high-level state goes to TerminusDB.
8. Analytics/evals run through DuckDB.
9. Agent retrieves context through orchestrated retrieval planner.

---

# 4. Memory Model

## 4.1 Working Memory

Storage:

Postgres / SQLite / SurrealDB / CozoDB

Contains:

- current task
- active goals
- open loops
- current conversation state
- scratch state
- temporary facts

Properties:

- mutable
- short-lived
- frequently updated

---

## 4.2 Episodic Memory

Storage:

Postgres event tables
ClickHouse for volume
TerminusDB for selected versioned episodes

Contains:

- conversations
- agent ticks
- tool calls
- observations
- user feedback
- decisions
- errors

Properties:

- append-only
- replayable
- timestamped
- source-linked

---

## 4.3 Semantic Memory

Storage:

TypeDB
Kuzu/Neo4j
RDF store if semantic-web style is needed

Contains:

- entities
- facts
- relations
- domain ontology
- validated knowledge
- inferred knowledge

Properties:

- stable
- typed
- provenance-aware
- queryable by graph patterns

---

## 4.4 Vector Memory

Storage:

LanceDB / Qdrant / pgvector

Contains:

- chunk embeddings
- entity embeddings
- image embeddings
- audio embeddings
- video embeddings
- summary embeddings
- memory embeddings

Properties:

- approximate nearest neighbor
- multi-vector
- model-versioned
- hybrid-filtered

---

## 4.5 Procedural Memory

Storage:

TypeDB / Postgres / Kuzu

Contains:

- workflows
- skills
- tool usage policies
- playbooks
- capability definitions
- preconditions
- postconditions

Properties:

- versioned
- constrained
- graph-linked to tools and permissions

---

# 5. Core Schemas

## 5.1 Entity

Fields:

- entity_id
- type
- canonical_name
- aliases
- source_refs
- confidence
- created_at
- updated_at
- valid_from
- valid_to
- embedding_refs
- graph_refs

---

## 5.2 Fact

Fields:

- fact_id
- subject
- predicate
- object
- relation_type
- participants
- roles
- source_id
- source_span
- extraction_method
- extractor_model
- confidence
- human_validated
- valid_from
- valid_to
- contradicts
- supersedes
- layer
- version

---

## 5.3 Chunk

Fields:

- chunk_id
- document_id
- source_uri
- text
- start_offset
- end_offset
- page
- section
- media_type
- embedding_ids
- extracted_entities
- extracted_facts
- confidence
- lineage

---

## 5.4 Vector Record

Fields:

- vector_id
- owner_type
- owner_id
- field_name
- model_name
- model_version
- dimension
- distance_metric
- embedding
- created_at
- source_hash

---

## 5.5 Agent State

Fields:

- agent_id
- persona_id
- state_id
- parent_state_id
- branch
- active_goals
- working_memory_ref
- semantic_memory_ref
- vector_memory_ref
- tool_registry_ref
- constraints_ref
- created_at
- commit_hash

---

## 5.6 Runtime Event

Fields:

- event_id
- run_id
- agent_id
- tick_id
- event_type
- input_state_id
- output_state_id
- model_call_id
- tool_call_id
- retrieval_call_id
- error
- timestamp
- trace_id
- span_id

---

# 6. Retrieval Planner

## 6.1 Retrieval Stages

Stage 1:
Query understanding

Stage 2:
Vector recall

Stage 3:
Full-text recall

Stage 4:
Entity linking

Stage 5:
Graph expansion

Stage 6:
Hypergraph validation

Stage 7:
Provenance scoring

Stage 8:
Contradiction check

Stage 9:
Reranking

Stage 10:
Context packaging

---

## 6.2 Retrieval Query Example

Input:

"Почему компания X стала high-risk?"

Planner:

1. Find entity Company X.
2. Fetch nearest chunks mentioning X.
3. Traverse ownership graph.
4. Check TypeDB risk rules.
5. Pull facts with confidence > threshold.
6. Include contradictory facts.
7. Separate raw / inferred / human-approved.
8. Return answer with provenance.

---

# 7. Layering Model

Recommended layers:

- raw
- parsed
- chunked
- embedded
- extracted_entities
- extracted_facts
- normalized
- entity_resolved
- inferred
- human_validated
- deprecated
- persona_private
- project_private
- public
- audit

Each fact must have:

- layer
- source
- confidence
- validity
- version
- extraction lineage

---

# 8. Docker Compose Reference Stack

This is a conceptual dev stack.

Services:

- postgres
- qdrant
- neo4j
- typedb
- terminusdb
- clickhouse
- minio
- grafana
- langfuse
- signoz optional
- custom-api
- worker

Compose skeleton:

version: "3.9"

services:

  postgres:
    image: postgres:16
    container_name: agi-postgres
    environment:
      POSTGRES_DB: agi
      POSTGRES_USER: agi
      POSTGRES_PASSWORD: agi
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  qdrant:
    image: qdrant/qdrant:latest
    container_name: agi-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

  neo4j:
    image: neo4j:5
    container_name: agi-neo4j
    environment:
      NEO4J_AUTH: neo4j/agi-password
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

  typedb:
    image: typedb/typedb:latest
    container_name: agi-typedb
    ports:
      - "1729:1729"
    volumes:
      - typedb_data:/opt/typedb-all-linux-x86_64/server/data

  terminusdb:
    image: terminusdb/terminusdb-server:latest
    container_name: agi-terminusdb
    environment:
      TERMINUSDB_ADMIN_PASS: agi-password
    ports:
      - "6363:6363"
    volumes:
      - terminusdb_data:/app/terminusdb/storage

  clickhouse:
    image: clickhouse/clickhouse-server:latest
    container_name: agi-clickhouse
    ports:
      - "8123:8123"
      - "9000:9000"
    volumes:
      - clickhouse_data:/var/lib/clickhouse

  minio:
    image: minio/minio:latest
    container_name: agi-minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: agi
      MINIO_ROOT_PASSWORD: agi-password
    ports:
      - "9002:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

  grafana:
    image: grafana/grafana:latest
    container_name: agi-grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana

volumes:
  postgres_data:
  qdrant_data:
  neo4j_data:
  neo4j_logs:
  typedb_data:
  terminusdb_data:
  clickhouse_data:
  minio_data:
  grafana_data:

---

# 9. Lightweight Local-First Variant

Use when:

- laptop-first
- no heavy services
- experiments
- embedded runtime
- agent desktop app

Stack:

- SQLite + sqlite-vec
- DuckDB
- KuzuDB
- LanceDB
- CozoDB
- local files / object directory

Responsibilities:

SQLite:
- app state
- configs
- event log
- small vectors if needed

DuckDB:
- analytics
- evals
- Parquet/Lance reads

KuzuDB:
- local property graph
- GraphRAG
- Cypher queries

LanceDB:
- multimodal embeddings
- vector search
- local object/vector lake

CozoDB:
- Datalog memory
- rules
- time-aware facts
- experimental reasoning

Recommended for:

- local agent memory
- desktop assistant
- research prototypes
- offline semantic notebook

---

# 10. Pragmatic All-in-One Variant

Use when:

- you want fewer moving parts
- JVM is acceptable
- native hypergraph is not mandatory
- property graph is enough
- embedded/server duality matters

Stack:

ArcadeDB

Optional additions:

- DuckDB for analytics
- MinIO for raw media
- Langfuse for traces
- Postgres only if operational app state must be boring

Covers:

- graph
- document
- key/value
- full-text
- vector
- time-series
- geospatial
- SQL
- Cypher
- Gremlin
- GraphQL
- MongoQL
- Redis commands
- embedded JVM
- Docker server

Tradeoffs:

- no native hypergraph
- no git-for-data versioning
- advanced provenance must be modeled

---

# 11. Semantic Enterprise Variant

Use when:

- provenance is critical
- ontology matters
- named graphs matter
- enterprise access control matters
- reasoning matters

Stack:

- Stardog or AllegroGraph or GraphDB
- Qdrant or LanceDB
- PostgreSQL
- LakeFS
- ClickHouse

Responsibilities:

RDF store:
- ontology
- named graphs
- source graphs
- trust layers
- reasoning

Vector layer:
- embeddings
- semantic retrieval
- hybrid search

Postgres:
- app state
- jobs
- users
- operational metadata

LakeFS:
- dataset versioning
- raw artifact history

ClickHouse:
- traces and analytics

Tradeoffs:

- SPARQL complexity
- less developer-friendly than Cypher
- not embedded-first
- vector integration varies by vendor

---

# 12. Hypergraph-First Variant

Use when:

- domain facts are complex
- relation roles matter
- n-ary relations are natural
- you want reasoning and constraints
- you model reality, not only retrieval

Stack:

- TypeDB
- LanceDB or Qdrant
- PostgreSQL
- DuckDB
- TerminusDB optional

Responsibilities:

TypeDB:
- canonical semantic memory
- n-ary facts
- roles
- rules
- constraints

Vector DB:
- multimodal recall

Postgres:
- operational events

DuckDB:
- analytics/evals

TerminusDB:
- versioned high-level state

Tradeoffs:

- TypeQL learning curve
- not vector-first
- not document/blob-first
- requires orchestration

---

# 13. GraphRAG-First Variant

Use when:

- retrieval quality matters
- graph context is central
- property graph is enough
- Cypher is useful
- embeddings are not enough

Stack:

- KuzuDB for embedded
or
- Neo4j for server production

Plus:

- LanceDB or Qdrant
- Postgres
- DuckDB

Flow:

1. Vector query finds chunks.
2. Chunk links to entities.
3. Graph expands entities by k hops.
4. Graph algorithms rank context.
5. Provenance layer filters claims.
6. Reranker selects final context.

Recommended:

Local:
KuzuDB + LanceDB + DuckDB + SQLite

Server:
Neo4j + Qdrant + Postgres + ClickHouse

---

# 14. Production Data Contracts

## 14.1 Every Fact Must Have

- fact_id
- participants
- relation type
- source
- source span
- extraction method
- extractor model
- confidence
- layer
- valid_from
- valid_to
- created_at
- updated_at
- supersedes
- contradicts
- human_validation_status

---

## 14.2 Every Embedding Must Have

- vector_id
- owner_id
- owner_type
- field_name
- model_name
- model_version
- dimension
- distance metric
- source hash
- created_at
- invalidated_at

---

## 14.3 Every Tool Call Must Have

- tool_call_id
- run_id
- agent_id
- tool_name
- input
- output
- error
- started_at
- finished_at
- permissions_checked
- policy_decision
- state_before
- state_after

---

## 14.4 Every Agent State Must Have

- state_id
- parent_state_id
- branch
- persona_id
- working_memory_ref
- semantic_memory_ref
- vector_memory_ref
- tool_registry_ref
- constraints_ref
- commit_ref
- created_at

---

# 15. Safety / Guardrails as Data

Represent safety as structured graph, not only prompt.

Entities:

- Tool
- Capability
- Permission
- Policy
- RiskClass
- UserRole
- AgentRole
- Environment
- StateTransition

Relations:

- Tool REQUIRES Permission
- Capability ENABLES Tool
- Policy DENIES Capability
- UserRole GRANTS Permission
- RiskClass RESTRICTS Action
- StateTransition REQUIRES Validation

This can live in:

- TypeDB
- Kuzu/Neo4j
- PostgreSQL
- ArcadeDB

---

# 16. Retrieval Quality / Evaluation Layer

Store evals as first-class data.

Tables:

- retrieval_run
- query
- candidate_chunk
- candidate_entity
- graph_expansion
- reranker_score
- human_judgment
- final_context
- answer_quality
- hallucination_flag

Use:

- DuckDB for local analysis
- ClickHouse for production analytics
- Postgres for canonical eval metadata

Metrics:

- recall@k
- precision@k
- MRR
- nDCG
- context faithfulness
- source coverage
- contradiction detection rate
- stale fact rate
- latency
- cost

---

# 17. Migration Strategy

## Phase 1: Local Research Stack

- KuzuDB
- LanceDB
- DuckDB
- SQLite
- CozoDB optional

Goal:

Validate graph + vector + memory concepts.

---

## Phase 2: Docker Compose Stack

- Postgres
- Qdrant
- Neo4j
- TypeDB
- TerminusDB
- ClickHouse
- MinIO

Goal:

Validate production-shaped architecture.

---

## Phase 3: Simplification Decision

After experiments, choose one of:

A. All-in-one:
ArcadeDB

B. GraphRAG:
Neo4j/Kuzu + Qdrant/Lance

C. Hypergraph:
TypeDB + vector layer

D. Semantic enterprise:
RDF store + vector layer

---

## Phase 4: Production Hardening

Add:

- backups
- migrations
- schema registry
- observability
- access control
- data retention
- audit
- eval dashboards
- cost monitoring
- deployment automation

---

# 18. Recommended Final Architecture for Your Case

Given your goals:

- AGI/context memory
- multimodal DB
- graph/hypergraph
- vectors
- runtime state
- lineage
- embedded and docker-compose interest
- production-grade thinking

Recommended architecture:

## Research / Local

KuzuDB
+ LanceDB
+ DuckDB
+ SQLite
+ CozoDB

Why:

- all embeddable/local
- enough to validate core ideas
- no heavy infra
- strong GraphRAG experiments

## Server / Docker Compose

PostgreSQL
+ Qdrant
+ Neo4j
+ TypeDB
+ TerminusDB
+ ClickHouse
+ MinIO

Why:

- Postgres for boring operational truth
- Qdrant for production vector search
- Neo4j for graph traversal/GDS
- TypeDB for true hypergraph semantics
- TerminusDB for versioned state/persona
- ClickHouse for traces/evals
- MinIO for raw multimodal artifacts

## Optional All-in-One Experiment

ArcadeDB

Why:

- closest all-in-one to your original desire
- embedded/server
- graph/document/vector/time-series
- SQL/Cypher/Gremlin/MongoQL/Redis

Use it as:

- alternative simplification path
- comparison baseline
- possible production simplifier if hypergraph/versioning can be modeled

---

# 19. What Not To Do

Do not:

- store all memory only in vector DB
- treat embeddings as source of truth
- ignore provenance
- overwrite facts without contradiction tracking
- mix raw and inferred facts without layers
- use graph DB as event log for high-volume traces
- use RDF store as operational app DB
- use TypeDB for raw media/blob storage
- rely only on prompts for safety constraints
- skip eval/observability layer

---

# 20. Final Answer

The best architecture is not one database.

It is a memory substrate composed of:

- hypergraph for meaning
- property graph for traversal
- vector store for recall
- versioned graph for state
- relational DB for operations
- analytical engine for evaluation
- object store for raw multimodal artifacts
- trace store for observability

Most practical high-coverage stack:

TypeDB
+ Neo4j or KuzuDB
+ Qdrant or LanceDB
+ TerminusDB
+ PostgreSQL
+ DuckDB
+ ClickHouse
+ Pixeltable
+ MinIO

Most pragmatic all-in-one candidate:

ArcadeDB

Most elegant local-first research stack:

KuzuDB
+ LanceDB
+ DuckDB
+ SQLite
+ CozoDB

---