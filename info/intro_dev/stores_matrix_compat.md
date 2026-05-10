# Matrix 120+ Features x 25+ Database / Storage Systems
## Multimodal Context / Memory DB Landscape
## April 2026

---

# 0. Purpose

This document is a feature matrix for designing a multimodal context / memory database stack.

Target operation:

find entities
→ traverse relations
→ respect layer / source / version
→ filter by metadata
→ run vector similarity
→ combine graph constraints
→ return explainable context with provenance

The matrix focuses on functions, not hype.

---

# 1. Legend

Symbols:

✔ = native / first-class / strong
◐ = partial / available through extension / workable but not ideal
△ = possible by modeling pattern or external glue
✖ = absent / not a good fit
E = enterprise/commercial feature
P = plugin/extension
L = library/embedded-local mode
S = server/service mode

---

# 2. System Codes

AR  = ArangoDB
AC  = ArcadeDB
SR  = SurrealDB
N4  = Neo4j
KZ  = KuzuDB
MG  = Memgraph
JG  = JanusGraph
TD  = TypeDB
TM  = TerminusDB
CZ  = CozoDB
SD  = Stardog
GD  = GraphDB
AG  = AllegroGraph
PG  = PostgreSQL + pgvector + AGE/AgensGraph
WV  = Weaviate
QD  = Qdrant
MV  = Milvus
LC  = LanceDB / Lance
PX  = Pixeltable
DK  = DuckDB
SQ  = SQLite + sqlite-vec / Vec1
RS  = Redis Stack / RedisGraph lineage / vector search
ES  = Elasticsearch
OS  = OpenSearch
CH  = ClickHouse
DL  = Dolt
LF  = LakeFS
JN  = Apache Jena / Fuseki
VT  = Virtuoso
HG  = HyperGraphDB

---

# 3. High-Level System Positioning

| Code | System | Best Role |
|---|---|---|
| AR | ArangoDB | Multi-model server DB: document + graph + vector/search via AQL |
| AC | ArcadeDB | All-in-one multi-model embedded/server JVM DB |
| SR | SurrealDB | Modern context-style document/graph/vector DB |
| N4 | Neo4j | Mature property graph + Cypher + GDS + vector |
| KZ | KuzuDB | Embedded graph-first DB for GraphRAG |
| MG | Memgraph | In-memory/streaming property graph |
| JG | JanusGraph | Distributed Gremlin graph over Cassandra/HBase/etc |
| TD | TypeDB | Typed hypergraph / n-ary relations / reasoning |
| TM | TerminusDB | Git-for-data / versioned document graph |
| CZ | CozoDB | Embedded Datalog relational-graph-vector memory |
| SD | Stardog | Enterprise RDF knowledge graph / reasoning / virtualization |
| GD | GraphDB | RDF / OWL / RDF-star / semantic graph |
| AG | AllegroGraph | RDF + vectors + triple attributes / neuro-symbolic |
| PG | PostgreSQL + pgvector + AGE | Boring production foundation with SQL + vectors + graph extension |
| WV | Weaviate | Vector-native object store with hybrid search |
| QD | Qdrant | Strong vector DB with payload filtering |
| MV | Milvus | Large-scale vector DB |
| LC | LanceDB / Lance | Embedded multimodal vector lakehouse |
| PX | Pixeltable | Multimodal AI data infrastructure / computed columns |
| DK | DuckDB | Embedded analytical SQL / lakehouse local engine |
| SQ | SQLite + sqlite-vec | Maximum local-first embedded store |
| RS | Redis Stack | Cache + vector + full-text + real-time workloads |
| ES | Elasticsearch | Full-text/search analytics + vector search |
| OS | OpenSearch | Open search/vector engine |
| CH | ClickHouse | Columnar analytics / logs / observability |
| DL | Dolt | Git-for-SQL |
| LF | LakeFS | Git-like versioning over object storage |
| JN | Apache Jena | RDF/SPARQL embedded/server toolkit |
| VT | Virtuoso | RDF/SQL hybrid graph server |
| HG | HyperGraphDB | Old-school embedded hypergraph |

---

# 4. Matrix A: Query Languages / Access Interfaces

| ID | Feature | AR | AC | SR | N4 | KZ | MG | JG | TD | TM | CZ | SD | GD | AG | PG | WV | QD | MV | LC | PX | DK | SQ | RS | ES | OS | CH | JN | VT | HG |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Q01 | Unified multi-model query | ✔ | ✔ | ✔ | △ | ◐ | △ | △ | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ✖ | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ✖ |
| Q02 | SQL-like query | ✖ | ✔ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✖ | ✖ | ✖ | ✔ | ◐ | ✔ | ✔ | ✖ | ◐ | ◐ | ✔ | ✖ | ✔ | ✖ |
| Q03 | AQL-like graph+doc query | ✔ | ◐ | ◐ | △ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | △ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| Q04 | Cypher / OpenCypher | ✖ | ✔ | ✖ | ✔ | ✔ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| Q05 | GQL standard alignment | ✖ | ◐ | ✖ | ◐ | ◐ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| Q06 | Gremlin / TinkerPop | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ |
| Q07 | SPARQL | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✔ | ✔ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✖ |
| Q08 | Datalog-like query | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ◐ | ✔ | ◐ | ◐ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ |
| Q09 | TypeQL-like typed query | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| Q10 | GraphQL API | ◐ | ✔ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ◐ | ◐ | ◐ | ◐ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| Q11 | Mongo-like query/protocol | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| Q12 | Redis protocol/API | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| Q13 | PostgreSQL wire compatibility | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ |
| Q14 | HTTP/REST API | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ◐ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ◐ | ◐ | ✖ | ✖ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✖ |
| Q15 | Native SDKs | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ |
| Q16 | Python-first ergonomics | ◐ | ◐ | ◐ | ✔ | ✔ | ◐ | ◐ | ✔ | ◐ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✖ |
| Q17 | JVM embedded API | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✔ | ✖ | ✖ | ✖ | ✔ | ✔ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✔ |
| Q18 | WASM/browser potential | ✖ | ✖ | ◐ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✔ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |

---

# 5. Matrix B: Graph Model Features

| ID | Feature | AR | AC | SR | N4 | KZ | MG | JG | TD | TM | CZ | SD | GD | AG | PG | WV | QD | MV | LC | PX | DK | SQ | RS | ES | OS | CH | JN | VT | HG |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| G01 | Native property graph | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✖ | ◐ | ◐ | ✖ | ✖ | ✖ | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| G02 | RDF triple model | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✔ | ✔ | ✔ | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✖ |
| G03 | RDF quad / named graph | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✔ | ✔ | ✔ | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✖ |
| G04 | Native hypergraph | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ |
| G05 | N-ary relations | △ | △ | △ | △ | △ | △ | △ | ✔ | ◐ | ✔ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ✔ |
| G06 | Relation-as-node pattern | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ |
| G07 | Physical edges / pointer-like traversal | ◐ | ✔ | ◐ | ✔ | ✔ | ✔ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| G08 | Edge properties | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | ◐ | ✔ | RDF | RDF | RDF | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | RDF | RDF | ✔ |
| G09 | Multi-graph support | ◐ | △ | △ | E | △ | △ | ◐ | △ | ✔ | △ | ✔ | ✔ | ✔ | △ | ✖ | ✖ | ✖ | ✖ | ✖ | △ | △ | △ | ✖ | ✖ | △ | ✔ | ✔ | △ |
| G10 | Composite graph query | ◐ | △ | △ | E | ✖ | △ | ◐ | △ | ◐ | △ | ✔ | ✔ | ✔ | △ | ✖ | ✖ | ✖ | ✖ | ✖ | △ | △ | △ | ✖ | ✖ | △ | ✔ | ✔ | ✖ |
| G11 | Cross-graph identity / shared IDs | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| G12 | Ontology graph | ◐ | △ | △ | ◐ | △ | △ | △ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ◐ |
| G13 | Schema graph | ◐ | ◐ | ◐ | ◐ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✖ | ✖ | ✖ | ✖ | ◐ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ◐ |
| G14 | Graph algorithms package | ◐ | △ | ✖ | ✔ | ✔ | ✔ | △ | ✖ | ✖ | ◐ | ◐ | ◐ | ◐ | P | ✖ | ✖ | ✖ | ✖ | ✖ | P | P | ✖ | P | P | P | ◐ | ◐ | ✖ |
| G15 | Shortest path | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ◐ | △ | △ | ◐ | ◐ | ◐ | ◐ | P | ✖ | ✖ | ✖ | ✖ | ✖ | P | P | ◐ | P | P | P | ◐ | ◐ | ◐ |
| G16 | K-hop expansion | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | P | ✖ | ✖ | ✖ | ✖ | ✖ | P | P | ◐ | P | P | P | ✔ | ✔ | ✔ |
| G17 | PageRank / centrality | ◐ | △ | ✖ | ✔ | ✔ | ✔ | △ | ✖ | ✖ | ◐ | ◐ | ◐ | ◐ | P | ✖ | ✖ | ✖ | ✖ | ✖ | P | P | ✖ | P | P | P | ◐ | ◐ | ✖ |
| G18 | Community detection | ◐ | △ | ✖ | ✔ | ◐ | ✔ | △ | ✖ | ✖ | ◐ | ◐ | ◐ | ◐ | P | ✖ | ✖ | ✖ | ✖ | ✖ | P | P | ✖ | P | P | P | ◐ | ◐ | ✖ |
| G19 | Graph topology similarity | △ | △ | ✖ | ✔ | ◐ | ◐ | △ | ✖ | ✖ | ◐ | ◐ | ◐ | ◐ | P | ✖ | ✖ | ✖ | ✖ | ✖ | P | P | ✖ | P | P | P | ◐ | ◐ | ✖ |
| G20 | Code/dependency graph fit | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ◐ | ◐ | ◐ | ✔ | ✖ | ✖ | ✖ | △ | △ | △ | △ | △ | △ | △ | △ | ◐ | ◐ | △ |

---

# 6. Matrix C: Vector / Retrieval Features

| ID | Feature | AR | AC | SR | N4 | KZ | MG | JG | TD | TM | CZ | SD | GD | AG | PG | WV | QD | MV | LC | PX | DK | SQ | RS | ES | OS | CH | JN | VT | HG |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V01 | Dense vector storage | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✖ | △ | ✖ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | ✖ |
| V02 | ANN vector index | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✖ | ✖ | ✖ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | P | P | ✔ | ✔ | ✔ | ✔ | ✖ | ✖ | ✖ |
| V03 | HNSW | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✖ | ✖ | ✖ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | P | P | ✔ | ✔ | ✔ | ◐ | ✖ | ✖ | ✖ |
| V04 | DiskANN / Vamana | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | △ | ✖ | ✖ | ◐ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| V05 | IVF / IVF-like | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ◐ | ◐ | ✖ | ✔ | ◐ | ✖ | ✖ | ✔ | ✖ | ◐ | ◐ | ◐ | ✖ | ✖ | ✖ |
| V06 | PQ / OPQ compression | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | △ | ◐ | ◐ | ✔ | ◐ | ✖ | ✖ | ✔ | ✖ | ◐ | ◐ | ◐ | ✖ | ✖ | ✖ |
| V07 | Multi-vector per entity | ◐ | ✔ | ✔ | ◐ | ◐ | ◐ | ✖ | △ | ✖ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | △ | △ | ✖ |
| V08 | Multiple vector indexes per type | ◐ | ✔ | ✔ | ◐ | ◐ | ◐ | ✖ | △ | ✖ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | △ | △ | ✖ |
| V09 | Hybrid BM25 + vector | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✖ | ✖ | ✖ | ◐ | ✔ | ✔ | ✔ | ◐ | ✔ | ◐ | ◐ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✖ |
| V10 | Vector + graph traversal | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✖ | △ | ✖ | ◐ | ◐ | ◐ | ✔ | P | ✖ | ✖ | ✖ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ✖ |
| V11 | Vector + document filter | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✖ | △ | ✖ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | ✖ |
| V12 | Vector + payload filter | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✖ | △ | ✖ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | ✖ |
| V13 | Vector model version metadata | △ | △ | △ | △ | △ | △ | ✖ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | △ | △ | △ | △ |
| V14 | Native reranking | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ◐ | ◐ | ✖ | ◐ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ◐ | ◐ | ✖ | ✖ | ✖ | ✖ |
| V15 | ColBERT/token-level retrieval fit | △ | △ | △ | △ | △ | ✖ | ✖ | ✖ | ✖ | △ | △ | △ | △ | △ | ◐ | ◐ | ◐ | ◐ | ◐ | △ | △ | △ | ◐ | ◐ | △ | ✖ | ✖ | ✖ |
| V16 | Multimodal vector objects | ◐ | ✔ | ✔ | △ | △ | △ | ✖ | △ | △ | △ | ◐ | ◐ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | ◐ | ◐ | ◐ | ◐ | △ | △ | ✖ |
| V17 | Image embedding workload | ◐ | ✔ | ✔ | △ | △ | △ | ✖ | △ | △ | △ | ◐ | ◐ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | ◐ | ◐ | ◐ | ◐ | △ | △ | ✖ |
| V18 | Audio embedding workload | ◐ | ✔ | ✔ | △ | △ | △ | ✖ | △ | △ | △ | ◐ | ◐ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | ◐ | ◐ | ◐ | ◐ | △ | △ | ✖ |
| V19 | Video embedding workload | △ | ✔ | ◐ | △ | △ | △ | ✖ | △ | △ | △ | ◐ | ◐ | ◐ | △ | ◐ | ◐ | ◐ | ✔ | ✔ | △ | △ | △ | ◐ | ◐ | ◐ | △ | △ | ✖ |
| V20 | Vector search embedded/local | ✖ | ✔ | ✔ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | L | L | ✔ | L | P | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |

---

# 7. Matrix D: Documents / Multimodal / Pipelines

| ID | Feature | AR | AC | SR | N4 | KZ | MG | JG | TD | TM | CZ | SD | GD | AG | PG | WV | QD | MV | LC | PX | DK | SQ | RS | ES | OS | CH | JN | VT | HG |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M01 | Document model | ✔ | ✔ | ✔ | △ | ✖ | △ | ✖ | △ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ◐ | ✔ | ✔ | ✔ | RDF | RDF | △ |
| M02 | JSON native | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ◐ | ◐ | ✔ | ◐ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | △ |
| M03 | Schema-free documents | ✔ | ✔ | ✔ | △ | ✖ | △ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | RDF | RDF | △ |
| M04 | Schema-enforced documents | ◐ | ✔ | ✔ | ◐ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ◐ |
| M05 | First-class image type | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ◐ | ✖ | ✖ | ◐ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| M06 | First-class audio type | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ◐ | ✖ | ✖ | ◐ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| M07 | First-class video type | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ◐ | ✖ | ✖ | ◐ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ |
| M08 | First-class document/PDF type | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ◐ | ◐ | ✖ | ◐ | ✖ | ✖ | ◐ | ✔ | ✖ | ✖ | ✖ | ◐ | ◐ | ✖ | ✖ | ✖ | ✖ |
| M09 | Blob/object references | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| M10 | Object-store friendly | ◐ | ◐ | ◐ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ◐ | ◐ | ◐ | ◐ | ◐ | ✔ | ◐ | ✔ | △ | △ | △ | △ | ✔ | △ | △ | ✖ |
| M11 | Lakehouse/table format fit | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | △ | △ | △ | △ | ✔ | △ | △ | ✖ |
| M12 | Computed columns | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ✔ | ◐ | ◐ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ |
| M13 | Declarative AI transforms | △ | △ | ◐ | △ | △ | △ | ✖ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | △ | △ | △ | ✖ |
| M14 | Incremental recompute | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ◐ | ✖ | ✖ | ✖ | △ | ✖ | ✖ | ✖ | ◐ | ✔ | ◐ | △ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ |
| M15 | Pipeline lineage | △ | △ | △ | △ | △ | △ | △ | △ | ✔ | ◐ | △ | △ | △ | △ | △ | △ | △ | ◐ | ✔ | △ | △ | △ | △ | △ | ◐ | △ | △ | ✖ |
| M16 | Media-derived entity graph fit | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ◐ | ✔ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ◐ |
| M17 | Chunk store fit | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ |
| M18 | Chunk-to-source span links | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | △ |
| M19 | Table/entity hybrid modeling | ✔ | ✔ | ✔ | △ | ◐ | △ | △ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ◐ | ◐ | △ |
| M20 | Multimodal eval datasets | △ | △ | △ | △ | △ | △ | ✖ | △ | △ | △ | △ | △ | △ | ✔ | △ | △ | △ | ✔ | ✔ | ✔ | ◐ | △ | △ | △ | ✔ | △ | △ | ✖ |

---

# 8. Matrix E: Versioning / State / Time / Provenance

| ID | Feature | AR | AC | SR | N4 | KZ | MG | JG | TD | TM | CZ | SD | GD | AG | PG | WV | QD | MV | LC | PX | DK | SQ | RS | ES | OS | CH | DL | LF | JN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S01 | Full commit history | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✖ | ✖ | ✖ | △ | ✖ | ✖ | ✖ | ◐ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✖ |
| S02 | Branching | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ◐ | ✖ | ✖ | ✖ | △ | ✖ | ✖ | ✖ | △ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✖ |
| S03 | Merge | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | △ | ✖ | ✖ | ✖ | △ | ✖ | ✖ | ✖ | △ | △ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✖ |
| S04 | Diff | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ◐ | ✖ | ✖ | ✖ | △ | ✖ | ✖ | ✖ | △ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✖ |
| S05 | Patch | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | △ | ✖ | ✖ | ✖ | △ | ✖ | ✖ | ✖ | △ | △ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✖ |
| S06 | Rollback | ◐ | ◐ | ◐ | △ | △ | △ | △ | △ | ✔ | ✔ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | △ |
| S07 | Point-in-time query | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✖ | ✖ | ✖ | △ | ✖ | ✖ | ✖ | △ | △ | ✖ | ✖ | ✖ | ✖ | ✖ | △ | ✔ | ✔ | ✖ |
| S08 | Immutable delta layers | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ◐ | ✖ | ✖ | ✖ | △ | ✖ | ✖ | ✖ | △ | △ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✔ | ✔ | ✖ |
| S09 | Event sourcing fit | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| S10 | Runtime trace store | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | △ | △ | ◐ | ◐ | △ | △ | △ | ✔ | △ | △ | △ | ◐ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ |
| S11 | Agent snapshot model | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | △ | △ | △ | ✔ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | △ |
| S12 | Persona branching model | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | △ |
| S13 | Source provenance | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ◐ | ✔ | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ |
| S14 | Statement-level metadata | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ |
| S15 | Confidence per fact | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ |
| S16 | Valid-from / valid-to | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | ✔ |
| S17 | Contradiction tracking | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ |
| S18 | Supersedes/obsolete relation | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ |
| S19 | Audit log | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ◐ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| S20 | Replayable state transitions | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | △ | △ | △ | ✔ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | △ |

---

# 9. Matrix F: Reasoning / Ontology / Constraints

| ID | Feature | AR | AC | SR | N4 | KZ | MG | JG | TD | TM | CZ | SD | GD | AG | PG | WV | QD | MV | LC | PX | DK | SQ | RS | ES | OS | CH | JN | VT | HG |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R01 | Strong schema constraints | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ◐ |
| R02 | Type hierarchy | △ | △ | ◐ | ◐ | ◐ | ◐ | △ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | ✖ | ✖ | ✖ | ✖ | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ◐ |
| R03 | Role constraints | △ | △ | △ | △ | △ | △ | △ | ✔ | △ | ✔ | ◐ | ◐ | ◐ | △ | ✖ | ✖ | ✖ | ✖ | △ | △ | △ | △ | △ | △ | △ | ◐ | ◐ | ◐ |
| R04 | Cardinality constraints | ◐ | ◐ | ◐ | ✔ | ✔ | ◐ | △ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | ✔ | ✔ | ✔ | △ | ◐ | ◐ | ✔ | ✔ | ✔ | ◐ |
| R05 | Inference rules | ◐ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ◐ |
| R06 | Recursive rules | ◐ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ◐ |
| R07 | Explainable inference | △ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | △ |
| R08 | OWL/RDFS reasoning | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✔ | ✔ | ✔ | P | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ | ✖ |
| R09 | Domain ontology fit | ◐ | ◐ | ◐ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | △ | △ | △ | △ | ◐ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ◐ |
| R10 | Policy graph fit | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ◐ |
| R11 | Tool permission graph | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | △ | ◐ | ◐ | ◐ |
| R12 | Constraint layer outside LLM | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ◐ |
| R13 | Materialized inferred layer | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ◐ |
| R14 | Raw vs inferred separation | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | ✔ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ◐ |
| R15 | Belief-state modeling | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | △ | ✔ | ✔ | ◐ |

---

# 10. Matrix G: Deployment / Operations / Durability

| ID | Feature | AR | AC | SR | N4 | KZ | MG | JG | TD | TM | CZ | SD | GD | AG | PG | WV | QD | MV | LC | PX | DK | SQ | RS | ES | OS | CH | DL | LF | JN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| O01 | True embedded in-process | ✖ | ✔ | ✔ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | L | L | ✔ | L | ✔ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | L |
| O02 | Server mode | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✖ | ✖ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| O03 | Docker image | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| O04 | Docker Compose friendly | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| O05 | Kubernetes friendly | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| O06 | ACID transactions | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ◐ | ✔ |
| O07 | WAL / crash recovery | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ |
| O08 | Backup / restore maturity | ✔ | ✔ | ◐ | ✔ | ◐ | ✔ | ✔ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| O09 | HA / replication | ✔ | ✔ | ◐ | ✔ | ✖ | ✔ | ✔ | ✔ | ◐ | ✖ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ✖ | ✖ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ✔ |
| O10 | Horizontal scale | ✔ | ◐ | ◐ | ✔ | ✖ | ◐ | ✔ | ◐ | ◐ | ✖ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ✖ | ✖ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ |
| O11 | Single-file local mode | ✖ | ◐ | ✔ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ◐ | ◐ | ◐ | ✔ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ |
| O12 | Object-storage backend | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ◐ | ◐ | ✔ | ✔ | ◐ | ✔ | ✖ | ✖ | ◐ | ◐ | ✔ | ✖ | ✔ | ✖ |
| O13 | Low-memory local agent fit | ✖ | ◐ | ◐ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ◐ | ✔ | ◐ | ✔ | ✔ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ◐ |
| O14 | Edge/mobile potential | ✖ | ◐ | ◐ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ◐ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ | ◐ | ◐ | ◐ | ✔ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | ◐ |
| O15 | Enterprise ops maturity | ✔ | ◐ | ◐ | ✔ | ◐ | ◐ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ✔ |
| O16 | License permissiveness | ◐ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | E | ◐ | E | ✔ | ◐ | ✔ | ◐ | ✔ | ✔ | ✔ | Public | ◐ | ◐ | ✔ | ◐ | ✔ | ✔ | ✔ |
| O17 | Observability hooks | ✔ | ✔ | ◐ | ✔ | ◐ | ✔ | ◐ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ |
| O18 | Admin UI | ✔ | ✔ | ◐ | ✔ | ✖ | ✔ | ◐ | ◐ | ✔ | ✖ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ✖ | ✖ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ |
| O19 | Cloud/self-host duality | ✔ | ◐ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ✔ |
| O20 | Good docker-compose candidate | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ | ◐ | ◐ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |

---

# 11. Matrix H: Agent / AGI Runtime Specific Features

| ID | Feature | Best Native / Strong | Workable | Weak |
|---|---|---|---|---|
| A01 | Semantic memory graph | TD, SD, GD, AG, N4, KZ, AC | AR, SR, CZ, PG | WV, QD, MV |
| A02 | Episodic memory log | PG, CH, DK, TM, CZ | AR, AC, SR, N4 | Pure vector DBs alone |
| A03 | Working memory state | SQ, PG, SR, CZ, TM | AC, AR, N4 | RDF-only stack |
| A04 | Procedural memory / skills | TD, N4, PG, TM | AC, SR, CZ | Vector-only |
| A05 | Capability graph | TD, N4, KZ, AC, SD | AR, SR, PG | Vector-only |
| A06 | Tool permission graph | TD, N4, KZ, PG | AC, SR, SD | Vector-only |
| A07 | Runtime trace graph | N4, KZ, AC, TM | PG, CH, AR | Pure vector-only |
| A08 | Full state snapshot | TM, CZ, DL, LF | PG event sourcing, SQ snapshots | Pure search engines |
| A09 | Persona branching | TM, DL, LF, CZ | PG event sourcing | Vector DB only |
| A10 | Belief graph with confidence | TD, AG, SD, GD, TM, CZ | N4, KZ, AC | WV/QD/MV alone |
| A11 | Contradiction graph | TD, RDF stores, TM, CZ | N4, KZ, AC | Vector-only |
| A12 | Human validation layer | TM, RDF named graphs, PG | AC, AR, SR | Vector-only |
| A13 | Raw/inferred/validated layers | RDF named graphs, TM, TD | N4, KZ, AC, AR | Vector-only |
| A14 | Agent replay | PG+event sourcing, TM, CZ, CH | AC, AR, SR | RDF-only without events |
| A15 | Tool-call lineage | PX, PG, TM, CH | AC, AR, SR | Vector-only |
| A16 | Model/prompt lineage | PX, PG, TM | AC, AR, SR, LC | Graph-only without app model |
| A17 | Multimodal perception memory | PX, LC, WV, QD | AC, SR, AR | TD alone |
| A18 | GraphRAG retrieval | KZ, N4, AC, AR, AG | SR, PG+AGE | QD/MV alone |
| A19 | Hypergraph AGI memory | TD | CZ, RDF with reification | Property graph only |
| A20 | Local-first agent memory | SQ, KZ, DK, LC, CZ, SR | AC JVM embedded | Heavy server stacks |

---

# 12. Top Feature Categories Summary

## 12.1 Strong Single-Engine Candidates

ArcadeDB:
- strongest all-in-one embedded/server multi-model candidate
- graph + document + KV + full-text + vector + time-series + geospatial
- SQL + Cypher + Gremlin + GraphQL + MongoQL + Redis commands
- good if you accept property graph instead of native hypergraph

SurrealDB:
- strong modern context/document/graph/vector engine
- good for agent memory prototypes
- less boring than Postgres, but attractive for unified context models

ArangoDB:
- conceptually strong multi-model reference
- AQL is a good unified query model
- less interesting if true embedded is mandatory

## 12.2 Strong Specialized Candidates

TypeDB:
- best native hypergraph / typed n-ary relations / roles / rules

KuzuDB:
- best embedded property graph / GraphRAG local engine

TerminusDB:
- best git-for-data / branch / commit / layer / time-travel graph-document system

CozoDB:
- best lightweight Datalog relational-graph-vector embedded reasoning memory

LanceDB:
- best embedded multimodal vector lakehouse layer

Pixeltable:
- best multimodal AI data pipeline / computed column / lineage system

PostgreSQL + pgvector + AGE:
- best boring production foundation

RDF stores:
- best named graphs / provenance / semantic interoperability / ontology reasoning

---

# 13. Recommendations by Design Goal

## 13.1 If you want one DB to rule them all

Primary:
- ArcadeDB

Alternative:
- SurrealDB
- ArangoDB

Tradeoff:
- no native hypergraph
- versioning/layering must be modeled

## 13.2 If you want best conceptual AGI memory

Core:
- TypeDB

Add:
- LanceDB for multimodal vectors
- TerminusDB for branch/time-travel state
- PostgreSQL for operational logs
- DuckDB for analytics/evals

## 13.3 If you want strongest GraphRAG local-first

Core:
- KuzuDB

Add:
- LanceDB or Qdrant
- SQLite/Postgres for app state
- DuckDB for evals

## 13.4 If you want enterprise semantic trust

Core:
- Stardog / GraphDB / AllegroGraph

Add:
- Qdrant / LanceDB / pgvector
- Postgres
- LakeFS

## 13.5 If you want production boring but powerful

Core:
- PostgreSQL + pgvector + AGE/AgensGraph

Add:
- Qdrant if vector volume grows
- Neo4j or Kuzu if graph traversal becomes central
- ClickHouse for traces

---

# 14. Final Matrix Conclusion

No single system covers all of these simultaneously:

- native hypergraph
- named graph provenance
- strong property graph traversal
- multi-vector hybrid retrieval
- git-for-data versioning
- declarative multimodal pipelines
- embedded/local-first mode
- Docker/server production mode
- graph algorithms
- rule engine
- statement-level trust/confidence
- operational observability

The highest-coverage architecture is compositional.

Best maximal stack:

TypeDB
+ KuzuDB or Neo4j
+ LanceDB or Qdrant
+ TerminusDB
+ PostgreSQL
+ DuckDB
+ Pixeltable
+ ClickHouse

Best pragmatic all-in-one:

ArcadeDB

Best local GraphRAG:

KuzuDB + LanceDB + DuckDB + SQLite

Best semantic enterprise:

Stardog/AllegroGraph + vector layer + Postgres/LakeFS

---