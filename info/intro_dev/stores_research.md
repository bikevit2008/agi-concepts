# AGI Context / Memory Database Landscape 2026
## Deep Research: Embedded + Docker-Deployable Systems
### Full Feature Matrix + Reference Architecture

---

# 0. Цель документа

Этот документ систематизирует:

- Все ключевые типы графовых моделей
- Hypergraph и n-ary relations
- Vector-native хранилища
- Multimodal data pipelines
- Versioning / git-for-data
- Agent runtime state storage
- Provenance / trust / contradiction tracking
- Embedded БД
- Docker-compose разворачиваемые сервисы
- Полную матрицу фич
- Reference architecture для AGI/context memory

Ключевая целевая операция системы:

найти сущности  
→ пройти связи  
→ учесть слой / источник / версию  
→ отфильтровать по метаданным  
→ выполнить vector similarity  
→ объединить с graph constraints  
→ вернуть объяснимый контекст с provenance  

---

# 1. Глобальная таксономия возможностей

## 1.1 Unified Multi-Model Query

Нужные свойства:

- document query
- graph traversal
- vector similarity
- full-text
- joins
- subqueries
- metadata filters
- ACID transactions
- composable execution plan

Системы:

- ArangoDB
- SurrealDB
- ArcadeDB
- PostgreSQL + AGE + pgvector
- Neo4j (частично через процедуры)

---

## 1.2 Query Languages

### Cypher / GQL

Тип: Declarative graph pattern matching  
Использование:

- Knowledge graph
- Dependency analysis
- Ownership modeling
- GraphRAG

Системы:
Neo4j, KuzuDB, ArcadeDB, Memgraph, AgensGraph

---

### Gremlin

Тип: Traversal DSL  
Использование:

- multi-hop traversal
- repeat / until
- complex path logic

Системы:
JanusGraph, Neptune, ArcadeDB

---

### SPARQL / RDF

Тип: Triple/Quad semantic graph  
Сильные стороны:

- Named graphs
- Provenance separation
- Ontology reasoning
- Federation

Системы:
Stardog, GraphDB, AllegroGraph, Virtuoso, Jena

---

### Datalog / TypeQL / WOQL

Тип: Rule + recursion  
Использование:

- inference
- temporal reasoning
- constraints
- domain modeling

Системы:
TypeDB, CozoDB, TerminusDB

---

# 2. Graph Model Types

## 2.1 Property Graph

Binary edges  
Node properties  

Подходит для:
- GraphRAG
- business entities
- dependency graphs

---

## 2.2 RDF Quad Store

subject – predicate – object – graph

Позволяет:
- Named graph layering
- Source separation
- Trust modeling

---

## 2.3 Native Hypergraph

N-ary relations:

shipment(
  vessel,
  cargo,
  port,
  contract,
  receiver,
  risk,
  date
)

Система:
TypeDB

---

## 2.4 Relation-as-Node Pattern

Workaround hypergraph для property graph.

---

# 3. Vector & Retrieval

## 3.1 ANN Algorithms

- HNSW
- DiskANN
- Vamana
- IVF
- IVFADC
- PQ / OPQ
- Flat

---

## 3.2 Vector-Native Systems

- Qdrant
- Weaviate
- Milvus
- LanceDB
- pgvector
- sqlite-vec
- Neo4j 5+
- SurrealDB
- ArcadeDB
- ArangoDB

---

## 3.3 Multi-Vector Entities

Нужно:

- несколько embeddings на сущность
- model versioning
- hybrid scoring
- chunk-level retrieval
- entity-level retrieval
- reranking

---

## 3.4 Hybrid Retrieval

vector  
+ full-text  
+ metadata filters  
+ graph traversal  
+ recency  
+ trust weighting  

---

# 4. Multimodal Data Infrastructure

## 4.1 First-Class Media Types

image  
video  
audio  
document  

Системы:
Pixeltable, LanceDB, Weaviate

---

## 4.2 Declarative Pipelines

source  
→ extract  
→ transform  
→ embed  
→ index  

Системы:
Pixeltable  
DuckDB + UDF  
dbt + lakehouse  

---

# 5. Versioning / Temporal / Agent State

## 5.1 Git-for-Data

Функции:

- branch
- commit
- diff
- merge
- rollback
- snapshot

Системы:

- TerminusDB
- Dolt
- LakeFS
- CozoDB

---

## 5.2 Time Travel

Query state at time T.

Системы:

- TerminusDB
- CozoDB
- Event sourcing + Postgres

---

## 5.3 Agent Runtime Snapshot

Содержит:

- persona
- memory graph
- vector state
- tool registry
- constraints
- execution trace

Требуется:

- immutable audit
- branch persona
- restore state
- replay

---

# 6. Provenance / Trust / Contradiction

## 6.1 Statement Metadata

- source
- extraction method
- confidence
- validity window
- contradicts
- supersedes

Лучшие системы:

- RDF quad stores
- AllegroGraph
- TypeDB
- Stardog

---

# 7. Embedded Systems (True In-Process)

- KuzuDB
- DuckDB
- SQLite + sqlite-vec
- CozoDB
- LanceDB
- SurrealDB (embedded mode)
- HyperGraphDB

---

# 8. Docker-Deployable Systems

- Neo4j
- ArangoDB
- SurrealDB
- ArcadeDB
- TypeDB
- TerminusDB
- Stardog
- GraphDB
- AllegroGraph
- Memgraph
- JanusGraph
- Weaviate
- Qdrant
- Milvus
- PostgreSQL
- Redis Stack
- ElasticSearch
- OpenSearch

---

# 9. Feature Matrix (Condensed)

Legend:
✔ native  
◐ partial  
✖ no  

Systems:

Neo4j  
Kuzu  
ArcadeDB  
SurrealDB  
TypeDB  
TerminusDB  
CozoDB  
ArangoDB  
PostgreSQL+AGE  
Stardog  
GraphDB  
AllegroGraph  
Weaviate  
Qdrant  
Milvus  
LanceDB  
DuckDB  
SQLite+vec  
Memgraph  
JanusGraph  

Key Feature Groups:

Property Graph  
Hypergraph  
Named Graph  
Vector Index  
Hybrid Retrieval  
Time Travel  
Rule Engine  
ACID  
Embedded  
Docker Deploy  

(Full expanded matrix recommended for separate sheet.)

---

# 10. Reference Architecture (Max Coverage)

Layer 1: Hypergraph Semantic Core  
TypeDB  

Layer 2: Property Graph Traversal  
Neo4j or Kuzu  

Layer 3: Vector Layer  
Qdrant or LanceDB  

Layer 4: Versioned State  
TerminusDB  

Layer 5: Analytics  
DuckDB  

Layer 6: Operational Metadata  
PostgreSQL  

---

# 11. Example Docker Compose Stack

version: "3.9"

services:

  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: agi
    ports:
      - "5432:5432"

  neo4j:
    image: neo4j:5
    ports:
      - "7474:7474"
      - "7687:7687"

  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"

  typedb:
    image: vaticle/typedb
    ports:
      - "1729:1729"

  duckdb:
    image: ghcr.io/duckdb/duckdb

  terminusdb:
    image: terminusdb/terminusdb-server
    ports:
      - "6363:6363"

---

# 12. Strategic Conclusion

Ни одна БД в 2026 не покрывает одновременно:

- native hypergraph
- named graph provenance
- multi-vector hybrid retrieval
- git-for-data
- embedded mode
- graph algorithms
- rule engine
- multimodal pipelines
- docker production maturity

Оптимальный путь:

Composable layered architecture.

---

# End of Document
April 2026