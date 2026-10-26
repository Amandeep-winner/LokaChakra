# AGENT_MASTER_SPEC.md — LOKACHAKRA: Personal Relationship & Intelligence Graph

> **AGENT PROMPT DIRECTIVE:**
> "Read `AGENT_MASTER_SPEC.md` completely. Execute Phase 1 through Phase 7 sequentially. Run the verification command at the end of each phase before moving to the next. Do not skip any constraints, do not invent alternative libraries, and never leave placeholder `TODO` or `pass` statements."

---

## 0. AGENT EXECUTION DIRECTIVES (READ FIRST)

You are an autonomous Principal Systems Architect and Senior Full-Stack Engineer building **Lokachakra**, an event-driven, Bi-Temporal Personal Intelligence System.

1. **Zero-Placeholder Policy:** Never write `# TODO`, `pass`, `...`, or mock return values in production files. Every function, class, route, and database query must be fully implemented with complete error handling and Python type annotations.
2. **Cross-Architecture Parity (Local Dev $\rightarrow$ Oracle Cloud ARM64):** The developer builds locally (`x86_64` or Apple Silicon `arm64`) and deploys to **Oracle Cloud Always Free Ampere A1 (`linux/arm64`, 4 OCPU, 24 GB RAM)**. Every Docker base image and Python wheel MUST natively support both `linux/amd64` and `linux/arm64`.
3. **Package Managers:**
   - **Backend:** Use `uv` (Astral) with `pyproject.toml` and `Python 3.12+`.
   - **Frontend:** Use `pnpm` with Next.js 15 (App Router, TypeScript, TailwindCSS).
4. **Sequential Verification Loop:** After completing each phase, execute the phase's verification command. Fix any import, schema, or runtime errors before advancing to the next phase.

---

## 1. ARCHITECTURAL INVARIANTS & HARD CONSTRAINTS

| Rule ID | Constraint Name | Strict Implementation Requirement |
| :--- | :--- | :--- |
| **INV-01** | **Staging-First Graph Isolation (Zero Hallucination)** | LLM extractors and OSINT web agents MUST NEVER write directly to verified `:Person` or `:Organization` nodes in Neo4j with `verified=True` unless deterministic confidence $\ge 0.95$. All probabilistic matches ($0.65 \le S < 0.95$) and OSINT discoveries MUST be written to PostgreSQL staging tables (`candidate_merges`, `candidate_edges`) and paused via LangGraph `interrupt()` until approved via Telegram. |
| **INV-02** | **End-to-End Idempotency** | Every ingested episode MUST generate a deterministic hash: `episode_hash = sha256(f"{source}:{raw_text.strip()}:{captured_date_iso}".encode()).hexdigest()`. If `episode_hash` already exists in PostgreSQL `ingestion_episodes` with `status='COMPLETED'`, ignore it gracefully and return the existing `episode_id`. |
| **INV-03** | **Mandatory Bi-Temporal Provenance** | Every relationship edge in Neo4j MUST carry six mandatory properties: `valid_from` (ISO-8601 string), `valid_to` (ISO-8601 string or `null`), `confidence_score` (`float` `0.0`–`1.0`), `source_episode_id` (`UUID` string), `evidence_snippet` (`str`), and `verified` (`bool`). Never overwrite historical edges when someone changes jobs—close `valid_to` on the old edge and create a new edge. |
| **INV-04** | **PII Scrubbing Before External OSINT** | Before sending any query string to SearXNG or Tavily, run `scrub_pii(query)` to strip regex matches for 10-digit phone numbers, email addresses, government IDs, bank details, and raw voice transcripts. Only pass `full_name`, `organization`, `role`, `location_city`, and public handles. |
| **INV-05** | **Loopback-Only Database Binding** | In `docker-compose.yml`, bind Neo4j (`7474`, `7687`), PostgreSQL (`5432`), Redis (`6379`), and SearXNG (`8080`) strictly to `127.0.0.1` (e.g., `"127.0.0.1:5432:5432"`). Never expose database ports to `0.0.0.0` on Oracle Cloud; remote access occurs strictly over Tailscale VPN (`tailscale0`). |

---

## 2. PINNED TECHNOLOGY STACK & VERSIONS

### 2.1 Backend Dependencies (`pyproject.toml`)
```toml
[project]
name = "lokachakra"
version = "1.0.0"
description = "Bi-Temporal Personal Relationship & OSINT Intelligence Graph"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "python-multipart>=0.0.17",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.6.0",
    "graphiti-core>=0.31.2",
    "neo4j>=5.26.0",
    "instructor>=1.7.0",
    "openai>=1.55.0",
    "groq>=0.13.0",
    "faster-whisper>=1.1.0",
    "splink>=4.0.6",
    "duckdb>=1.1.0",
    "rapidfuzz>=3.10.0",
    "fastembed>=0.4.2",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30.0",
    "pgvector>=0.3.6",
    "alembic>=1.14.0",
    "taskiq>=0.11.9",
    "taskiq-redis>=1.0.2",
    "redis>=5.2.0",
    "langgraph>=0.2.50",
    "langgraph-checkpoint-postgres>=2.0.6",
    "psycopg[binary,pool]>=3.2.3",
    "aiogram>=3.15.0",
    "httpx>=0.28.0",
    "playwright>=1.49.0",
    "apscheduler>=3.10.4",
    "structlog>=24.4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.3",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=6.0.0",
    "testcontainers>=4.8.2",
]
```

### 2.2 Infrastructure Containers (Multi-Arch `linux/amd64` & `linux/arm64`)
- **Graph DB:** `neo4j:5.26-community` (Plugins: `apoc`, `graph-data-science`)
- **Relational & Vector DB:** `pgvector/pgvector:pg16`
- **Event Broker & Queue:** `redis:7.4-alpine`
- **Self-Hosted Metasearch Engine:** `searxng/searxng:latest`

---

## 3. TARGET REPOSITORY STRUCTURE

Create this exact directory tree:

```text
lokachakra/
├── docker-compose.yml              # Local Dev stack (RAM capped to ~6GB total)
├── docker-compose.oracle.yml       # Oracle Cloud ARM64 override (24GB RAM tuning)
├── Dockerfile.backend              # Python 3.12-slim + uv + Playwright Chromium
├── pyproject.toml                  # Python dependencies & pytest config
├── .env.example                    # Complete template of required environment variables
├── scripts/
│   ├── init_postgres.sql           # pgvector extension & relational staging tables
│   ├── init_neo4j.cypher           # Uniqueness constraints, indexes, & SELF_USER seed
│   └── oracle_arm64_setup.sh       # UFW firewall, Docker, Tailscale, & backup cron
├── config/
│   └── searxng/
│       └── settings.yml            # Enables JSON output format for SearXNG API
├── src/
│   ├── __init__.py
│   ├── config.py                   # Pydantic BaseSettings loading .env
│   ├── contracts/
│   │   ├── __init__.py
│   │   └── schema.py               # Master Pydantic schemas shared by all modules
│   ├── db/
│   │   ├── __init__.py
│   │   ├── postgres.py             # Async SQLAlchemy engine, ORM models, & session maker
│   │   ├── neo4j_client.py         # Async Neo4j Bolt driver & Graphiti client wrapper
│   │   └── redis_broker.py         # Taskiq Redis Stream broker & Dead-Letter Queue
│   ├── ingestion/                  # MODULE A: Voice, Text & CSV Importers
│   │   ├── __init__.py
│   │   ├── transcriber.py          # Groq Whisper API + faster-whisper local fallback
│   │   ├── extractor.py            # Instructor LLM triplet & temporal clue extractor
│   │   ├── social_parsers.py       # LinkedIn Connections.csv & WhatsApp .txt parser
│   │   └── tasks.py                # Taskiq background workers for ingestion pipeline
│   ├── entity_resolution/          # MODULE C: Deduplication Engine
│   │   ├── __init__.py
│   │   ├── embedder.py             # FastEmbed BAAI/bge-small-en-v1.5 384-d generator
│   │   └── resolver.py             # 3-Tier Deterministic + Splink/RapidFuzz + Vector matcher
│   ├── graph_core/                 # MODULE B: Temporal Graph & Provenance
│   │   ├── __init__.py
│   │   ├── graphiti_service.py     # Episodic ingestion & bi-temporal edge invalidation
│   │   └── cypher_queries.py       # Node upsert, temporal edge close, open-triangle search
│   ├── agents/                     # MODULE D: Autonomous OSINT & Recon
│   │   ├── __init__.py
│   │   ├── pii_scrubber.py         # Regex sanitizer for outbound search queries
│   │   ├── search_tools.py         # SearXNG JSON client + Tavily fallback + Playwright
│   │   └── osint_graph.py          # LangGraph state machine with PostgresSaver & interrupt()
│   ├── hitl_bot/                   # MODULE E: Telegram Bot & Verification Bus
│   │   ├── __init__.py
│   │   ├── bot.py                  # Aiogram 3.x voice handler + inline button callbacks
│   │   └── notifier.py             # Formats HITLEvidenceCard into Telegram inline keyboard
│   ├── pathfinder/                 # MODULE F (Backend): Analytics & Decay
│   │   ├── __init__.py
│   │   ├── routing.py              # Weighted Dijkstra shortest path & centrality scoring
│   │   └── decay_cron.py           # Nightly exponential trust decay & Sunday nudge digest
│   └── api/
│       ├── __init__.py
│       ├── main.py                 # FastAPI app + lifespan hooks (DB init + scheduler)
│       └── routes/
│           ├── __init__.py
│           ├── ingest.py           # POST /api/v1/ingest/voice, /text, /csv
│           ├── graph.py            # GET /api/v1/graph/map, /path, /person/{uid}
│           └── hitl.py             # POST /api/v1/hitl/resolve, GET /api/v1/hitl/pending
├── frontend/                       # MODULE F (UI): Next.js 15 + Cytoscape.js
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   └── src/
│       ├── app/
│       │   ├── layout.tsx
│       │   └── page.tsx            # Command Center: Search Bar + Canvas + Dossier Drawer
│       ├── components/
│       │   ├── NetworkCanvas.tsx   # Cytoscape.js graph with tier colors & path glow
│       │   ├── DossierDrawer.tsx   # Provenance timeline, audio logs, & outreach copy
│       │   └── HitlQueueModal.tsx  # Web fallback UI for approving pending HITL cards
│       └── lib/
│           └── api.ts              # Typed fetch client for FastAPI backend
└── tests/
    ├── conftest.py
    ├── test_extractor.py
    ├── test_resolver.py
    ├── test_osint_hitl.py
    └── test_pathfinder.py
```

---

## 4. ENVIRONMENT CONFIGURATION & MASTER DATA CONTRACT

### 4.1 `.env.example`
Generate this exact `.env.example` file:
```ini
# --- Core Application ---
APP_ENV=development
LOG_LEVEL=INFO
SELF_USER_NAME="SELF_USER"

# --- Databases (Bound to 127.0.0.1 in Docker) ---
POSTGRES_USER=lokachakra
POSTGRES_PASSWORD=lokachakra_secure_pg
POSTGRES_DB=lokachakra_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_URI=postgresql+asyncpg://lokachakra:lokachakra_secure_pg@localhost:5432/lokachakra_db
POSTGRES_SYNC_URI=postgresql://lokachakra:lokachakra_secure_pg@localhost:5432/lokachakra_db

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=lokachakra_secure_neo4j

REDIS_URL=redis://localhost:6379/0

# --- LLM & Transcription Providers ---
# Primary fast inference (Groq Whisper + Llama-3.3-70B)
GROQ_API_KEY=gsk_your_groq_key_here
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile

# Optional OpenAI / Gemini OpenAI-compatible fallback
OPENAI_API_KEY=sk_your_openai_key_here
OPENAI_BASE_URL=[https://api.groq.com/openai/v1](https://api.groq.com/openai/v1)

# --- OSINT Web Recon ---
SEARXNG_URL=http://localhost:8080
TAVILY_API_KEY=tvly_optional_fallback_key

# --- Telegram HITL Bot ---
TELEGRAM_BOT_TOKEN=123456789:ABCDEF_your_telegram_bot_token
TELEGRAM_ALLOWED_USER_ID=987654321
```

### 4.2 Master Data Contract (`src/contracts/schema.py`)
Implement this exact file first. Every module MUST import its types from `src.contracts.schema`:

```python
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator
import re


class ReachabilityTier(int, Enum):
    TIER_1_CLOSE = 1        # Direct friend, regular contact
    TIER_2_WARM = 2         # Acquaintance or 2nd-degree via Tier 1
    TIER_3_COLD_TARGET = 3  # Target person / 3rd-degree


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PENDING_HITL = "pending_hitl"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"


class ResolutionAction(str, Enum):
    AUTO_MERGE = "AUTO_MERGE"
    QUEUE_HITL = "QUEUE_HITL"
    CREATE_NEW_NODE = "CREATE_NEW_NODE"


class EntityType(str, Enum):
    PERSON = "Person"
    ORGANIZATION = "Organization"
    LOCATION = "Location"
    SKILL_DOMAIN = "SkillDomain"
    GOAL = "Goal"


class RelationType(str, Enum):
    KNOWS = "KNOWS"
    BATCHMATE_OF = "BATCHMATE_OF"
    ROOMMATE_OF = "ROOMMATE_OF"
    SIBLING_OF = "SIBLING_OF"
    WORKED_WITH = "WORKED_WITH"
    WORKS_AT = "WORKS_AT"
    STUDIED_AT = "STUDIED_AT"
    CO_AUTHORED_WITH = "CO_AUTHORED_WITH"
    LOCATED_IN = "LOCATED_IN"
    HAS_SKILL = "HAS_SKILL"


class ExtractedPerson(BaseModel):
    uid: UUID = Field(default_factory=uuid4)
    full_name: str = Field(..., min_length=2, description="Normalized full or partial name")
    aliases: List[str] = Field(default_factory=list)
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_handle: Optional[str] = None
    x_handle: Optional[str] = None
    current_org: Optional[str] = None
    current_role: Optional[str] = None
    alumni_orgs: List[str] = Field(default_factory=list)
    location_city: Optional[str] = None
    reachability_tier: ReachabilityTier = ReachabilityTier.TIER_2_WARM
    trust_score: float = Field(default=50.0, ge=0.0, le=100.0)
    responsiveness_note: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        digits = re.sub(r"\D", "", v)
        return digits[-10:] if len(digits) >= 10 else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if v else None


class ExtractedOrganization(BaseModel):
    name: str = Field(..., min_length=2)
    org_type: str = Field(default="company", description="company | college | club | fund")
    location_city: Optional[str] = None


class ExtractedEdge(BaseModel):
    source_name: str
    source_type: EntityType
    target_name: str
    target_type: EntityType
    relation_type: RelationType
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_score: float = Field(default=0.8, ge=0.0, le=1.0)
    valid_from: Optional[str] = Field(default=None, description="YYYY-MM or YYYY-MM-DD")
    valid_to: Optional[str] = Field(default=None, description="Null if currently active")
    evidence_snippet: str = Field(..., description="Exact quote or reason from source")


class EpisodeExtractionResult(BaseModel):
    episode_id: UUID = Field(default_factory=uuid4)
    episode_hash: Optional[str] = None
    raw_transcript: str
    source_type: str = Field(default="voice_note", description="voice_note | text_note | csv_import")
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    persons: List[ExtractedPerson] = Field(default_factory=list)
    organizations: List[ExtractedOrganization] = Field(default_factory=list)
    edges: List[ExtractedEdge] = Field(default_factory=list)


class ResolutionResult(BaseModel):
    action: ResolutionAction
    matched_uid: Optional[UUID] = None
    confidence_score: float
    hitl_card: Optional["HITLEvidenceCard"] = None


class HITLEvidenceCard(BaseModel):
    card_id: UUID = Field(default_factory=uuid4)
    langgraph_thread_id: str
    action_type: str = Field(..., description="ENTITY_MERGE | HIDDEN_BRIDGE_DISCOVERY")
    subject_a_uid: Optional[UUID] = None
    subject_a_name: str
    subject_b_uid: Optional[UUID] = None
    subject_b_name: str
    proposed_relation: RelationType
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    evidence_summary: str
    source_urls: List[str] = Field(default_factory=list)
    status: VerificationStatus = VerificationStatus.PENDING_HITL
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PathStep(BaseModel):
    node_uid: str
    node_name: str
    node_type: str
    reachability_tier: Optional[int] = None
    trust_score: Optional[float] = None
    relation_to_next: Optional[str] = None
    edge_confidence: Optional[float] = None


class WarmPathResponse(BaseModel):
    target_query: str
    total_cost: float
    hop_count: int
    steps: List[PathStep]
    recommended_intro_script: str
```

---

## 5. STEP-BY-STEP PHASE IMPLEMENTATION SPECIFICATIONS

---

### PHASE 1: Infrastructure, Docker & Database Schemas

#### 1.1 `docker-compose.yml` (Local Dev Defaults)
Create `docker-compose.yml` with healthchecks and loopback port bindings (`127.0.0.1`):
```yaml
services:
  neo4j:
    image: neo4j:5.26-community
    container_name: lokachakra-neo4j
    restart: unless-stopped
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    environment:
      - NEO4J_AUTH=${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD:-lokachakra_secure_neo4j}
      - NEO4J_PLUGINS=["apoc", "graph-data-science"]
      - NEO4J_dbms_security_procedures_unrestricted=apoc.*,gds.*
      - NEO4J_server_memory_heap_initial__size=512M
      - NEO4J_server_memory_heap_max__size=1G
      - NEO4J_server_memory_pagecache_size=512M
    volumes:
      - neo4j_data:/data
      - ./scripts/init_neo4j.cypher:/var/lib/neo4j/import/init_neo4j.cypher
    healthcheck:
      test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider localhost:7474 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10

  postgres:
    image: pgvector/pgvector:pg16
    container_name: lokachakra-postgres
    restart: unless-stopped
    ports:
      - "127.0.0.1:5432:5432"
    environment:
      - POSTGRES_USER=${POSTGRES_USER:-lokachakra}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-lokachakra_secure_pg}
      - POSTGRES_DB=${POSTGRES_DB:-lokachakra_db}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init_postgres.sql:/docker-entrypoint-initdb.d/01_init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-lokachakra} -d ${POSTGRES_DB:-lokachakra_db}"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7.4-alpine
    container_name: lokachakra-redis
    restart: unless-stopped
    command: redis-server --appendonly yes
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  searxng:
    image: searxng/searxng:latest
    container_name: lokachakra-searxng
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./config/searxng:/etc/searxng:rw
    environment:
      - SEARXNG_BASE_URL=http://localhost:8080/

volumes:
  neo4j_data:
  postgres_data:
  redis_data:
```

#### 1.2 `docker-compose.oracle.yml` (Oracle Cloud 24GB ARM64 Override)
```yaml
services:
  neo4j:
    environment:
      - NEO4J_server_memory_heap_initial__size=4G
      - NEO4J_server_memory_heap_max__size=6G
      - NEO4J_server_memory_pagecache_size=4G
```

#### 1.3 PostgreSQL Initialization (`scripts/init_postgres.sql`)
Create exact relational staging and vector tables in `scripts/init_postgres.sql`:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS ingestion_episodes (
    episode_id UUID PRIMARY KEY,
    episode_hash VARCHAR(64) UNIQUE NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    raw_transcript TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PROCESSING',
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS person_staging (
    uid UUID PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    aliases JSONB DEFAULT '[]'::jsonb,
    email VARCHAR(255),
    phone VARCHAR(32),
    linkedin_url TEXT,
    github_handle VARCHAR(128),
    x_handle VARCHAR(128),
    current_org VARCHAR(255),
    current_role VARCHAR(255),
    alumni_orgs JSONB DEFAULT '[]'::jsonb,
    location_city VARCHAR(128),
    reachability_tier SMALLINT DEFAULT 2,
    trust_score FLOAT DEFAULT 50.0,
    verified BOOLEAN DEFAULT FALSE,
    embedding vector(384),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_person_staging_email ON person_staging(email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_person_staging_phone ON person_staging(phone) WHERE phone IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_person_staging_linkedin ON person_staging(linkedin_url) WHERE linkedin_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_person_staging_embedding ON person_staging USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS hitl_evidence_cards (
    card_id UUID PRIMARY KEY,
    langgraph_thread_id VARCHAR(128) NOT NULL,
    action_type VARCHAR(64) NOT NULL,
    subject_a_uid UUID,
    subject_a_name VARCHAR(255) NOT NULL,
    subject_b_uid UUID,
    subject_b_name VARCHAR(255) NOT NULL,
    proposed_relation VARCHAR(64) NOT NULL,
    confidence_score FLOAT NOT NULL,
    evidence_summary TEXT NOT NULL,
    source_urls JSONB DEFAULT '[]'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_hitl',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
```

#### 1.4 Neo4j Initialization (`scripts/init_neo4j.cypher`)
```cypher
CREATE CONSTRAINT person_uid_unique IF NOT EXISTS FOR (p:Person) REQUIRE p.uid IS UNIQUE;
CREATE CONSTRAINT org_name_unique IF NOT EXISTS FOR (o:Organization) REQUIRE o.name IS UNIQUE;
CREATE INDEX person_name_idx IF NOT EXISTS FOR (p:Person) ON (p.full_name);
CREATE INDEX person_tier_idx IF NOT EXISTS FOR (p:Person) ON (p.reachability_tier);

MERGE (u:Person {full_name: 'SELF_USER'})
ON CREATE SET
  u.uid = '00000000-0000-0000-0000-000000000001',
  u.reachability_tier = 0,
  u.trust_score = 100.0,
  u.verified = true,
  u.created_at = datetime();
```

#### 1.5 SearXNG Config (`config/searxng/settings.yml`)
```yaml
use_default_settings: true
search:
  safe_search: 0
  formats:
    - html
    - json
server:
  secret_key: "lokachakra_searxng_local_secret"
  limiter: false
```

- **Phase 1 Verification Command:**
  `docker compose up -d && uv run pytest tests/ -k "test_infra" || true` (Verify containers reach `healthy` state).

---

### PHASE 2: Module A — Omnichannel Ingestion (`src/ingestion/`)

#### 2.1 `src/ingestion/transcriber.py`
- Implement `async def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg") -> str`:
  1. **Primary (Groq Cloud Whisper):** If `settings.GROQ_API_KEY` is set, call `AsyncGroq().audio.transcriptions.create()` with:
     - `model="whisper-large-v3-turbo"`
     - `prompt="Indian English names, Bengaluru, Mumbai, Delhi, IIT, NIT, BITS, RVCE, Razorpay, Flipkart, Zomato, Swiggy, Peak XV, Stripe, AI startups"`
     - `response_format="text"`
  2. **Automatic Local Fallback (`faster-whisper`):** Catch any `APIError`, timeout, or missing key and transcribe locally using `WhisperModel("base", device="cpu", compute_type="int8")`.

#### 2.2 `src/ingestion/extractor.py`
- Implement `async def extract_episode(raw_text: str, source_type: str = "voice_note", reference_date: Optional[str] = None) -> EpisodeExtractionResult`:
  - Compute `episode_hash = hashlib.sha256(f"{source_type}:{raw_text.strip()}:{reference_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')}".encode()).hexdigest()`.
  - Configure `instructor.from_openai(AsyncOpenAI(api_key=..., base_url=...))` returning `response_model=EpisodeExtractionResult`.
  - **Mandatory System Prompt:**
    ```text
    You are the Entity & Temporal Relationship Extractor for Lokachakra.
    Today's Reference Date is: {reference_date}.
    RULES:
    1. Always represent the first-person speaker ("I", "me", "my") as a Person with full_name="SELF_USER" and reachability_tier=1.
    2. Direct friends/colleagues mentioned as spoken to by SELF_USER get reachability_tier=1. Friends-of-friends (e.g., "Ankit's roommate Vikram") get reachability_tier=2. Distant targets get reachability_tier=3.
    3. TEMPORAL LOGIC:
       - If the text says someone "used to work at X", "left X", or "ex-X", create a WORKS_AT edge with valid_to="{reference_date}".
       - If the text says someone "currently works at Y" or "just joined Y", create a WORKS_AT edge with valid_from="{reference_date}" and valid_to=null.
    4. Every edge MUST include an exact evidence_snippet quoted from the input text.
    ```

#### 2.3 `src/ingestion/social_parsers.py`
- **`parse_linkedin_csv(csv_content: str) -> List[ExtractedPerson]`:**
  - LinkedIn exports include 3 disclaimer lines before the header `First Name,Last Name,URL,Email Address,Company,Position,Connected On`. Dynamically locate the row starting with `First Name` before passing to `csv.DictReader`.
  - Map each row to `ExtractedPerson(full_name=f"{first} {last}".strip(), linkedin_url=row["URL"], email=row["Email Address"] or None, current_org=row["Company"] or None, current_role=row["Position"] or None, reachability_tier=ReachabilityTier.TIER_2_WARM, trust_score=45.0)`.
- **`parse_whatsapp_txt(chat_txt: str) -> List[str]`:**
  - Group consecutive messages by day into daily summary strings ready for batch extraction.

- **Phase 2 Verification Command:** `uv run pytest tests/test_extractor.py -v`

---

### PHASE 3: Module C — Three-Tier Entity Resolution (`src/entity_resolution/`)

#### 3.1 `src/entity_resolution/embedder.py`
- Use a singleton wrapper around `fastembed.TextEmbedding(model_name="BAAI/bge-small-en-v1.5")`.
- Implement `def build_person_profile_text(p: ExtractedPerson) -> str`:
  ```python
  aliases_str = " ".join(p.aliases)
  alumni_str = " ".join(p.alumni_orgs)
  return f"{p.full_name} {aliases_str} | Org: {p.current_org or ''} {p.current_role or ''} | Alumni: {alumni_str} | City: {p.location_city or ''}".strip()
  ```
- Implement `def embed_person(p: ExtractedPerson) -> List[float]` returning a 384-dimensional float vector.

#### 3.2 `src/entity_resolution/resolver.py`
Implement `async def resolve_person(session: AsyncSession, incoming: ExtractedPerson, episode_id: UUID) -> ResolutionResult`:

1. **Tier 1: Deterministic Exact Match ($S = 1.0$)**
   - Query `person_staging` where `(email = incoming.email AND email IS NOT NULL)` OR `(phone = incoming.phone AND phone IS NOT NULL)` OR `(linkedin_url = incoming.linkedin_url AND linkedin_url IS NOT NULL)`.
   - If found: merge any newly discovered non-null attributes (`current_org`, `alumni_orgs`, `aliases`) into the existing row and return `ResolutionResult(action=ResolutionAction.AUTO_MERGE, matched_uid=existing.uid, confidence_score=1.0)`.

2. **Tier 2: Probabilistic + Vector Hybrid Match**
   - Generate 384-d embedding $v_{\text{in}}$ for `incoming`.
   - Query top 10 candidates from `person_staging` ordered by pgvector cosine distance `embedding <=> :v_in`.
   - For each candidate $c$, compute:
     - **Name Similarity ($N_{\text{sim}}$):** Using `rapidfuzz.distance.JaroWinkler.normalized_similarity(incoming.full_name.lower(), c.full_name.lower())`. Also check if `incoming.full_name` is an initial/prefix match (e.g., `"R. Sharma"` vs `"Rahul Sharma"` $\rightarrow$ boost $N_{\text{sim}}$ to $\ge 0.88$).
     - **Vector Cosine Similarity ($V_{\text{sim}}$):** $1.0 - \text{cosine\_distance}(v_{\text{in}}, v_c)$.
     - **Shared Institutional Context ($I_{\text{shared}} \in \{0.0, 1.0\}$):** Equals $1.0$ if `incoming` and $c$ share at least one normalized organization/college name across `current_org` and `alumni_orgs` (including common Indian abbreviations: `"IITB" == "IIT Bombay"`, `"IITD" == "IIT Delhi"`, `"IITR" == "IIT Roorkee"`, `"RVCE" == "R.V. College of Engineering"`).
   - **Composite Resolution Formula:**
     $$S = 0.45 \cdot N_{\text{sim}} + 0.35 \cdot V_{\text{sim}} + 0.20 \cdot I_{\text{shared}}$$

3. **Decision Thresholds:**
   - **If $S \ge 0.95$:** Auto-merge into candidate $c$ and return `ResolutionAction.AUTO_MERGE`.
   - **If $0.65 \le S < 0.95$:** Insert a `HITLEvidenceCard` into `hitl_evidence_cards` with `action_type="ENTITY_MERGE"`, `subject_a_name=incoming.full_name`, `subject_b_name=c.full_name`, `confidence_score=S`, and return `ResolutionAction.QUEUE_HITL`.
   - **If $S < 0.65$:** Insert `incoming` into `person_staging` as a new record and return `ResolutionAction.CREATE_NEW_NODE`.

- **Phase 3 Verification Command:** `uv run pytest tests/test_resolver.py -v`

---

### PHASE 4: Module B — Bi-Temporal Graph Core (`src/graph_core/`)

#### 4.1 `src/graph_core/cypher_queries.py`
Implement parameterized async Cypher functions:
1. **`upsert_verified_person(tx, person: ExtractedPerson, verified: bool = True)`:**
   Upserts `:Person {uid: str(person.uid)}` with `full_name`, `current_org`, `reachability_tier`, `trust_score`, `verified`, and `last_contacted_date`.
2. **`upsert_temporal_edge(tx, source_uid: str, target_id: str, edge: ExtractedEdge, episode_id: str, verified: bool = True)`:**
   - **Bi-Temporal Job Switch Rule:** If `edge.relation_type == RelationType.WORKS_AT` and `edge.valid_to is None`, first run:
     ```cypher
     MATCH (p:Person {uid: $source_uid})-[old_r:WORKS_AT]->(old_org:Organization)
     WHERE old_org.name <> $target_org_name AND old_r.valid_to IS NULL
     SET old_r.valid_to = $current_date
     ```
   - Then `MERGE` the new relationship with `valid_from`, `valid_to`, `confidence_score`, `source_episode_id`, `evidence_snippet`, and `verified`.

#### 4.2 `src/graph_core/graphiti_service.py`
- Wrap `Graphiti(uri=settings.NEO4J_URI, user=settings.NEO4J_USER, password=settings.NEO4J_PASSWORD)` alongside the explicit Cypher provenance layer so both semantic hybrid search (via Graphiti) and deterministic structural Cypher pathfinding operate on the same Neo4j instance.

---

### PHASE 5: Module D — Autonomous OSINT & Open-Triangle Agent (`src/agents/`)

#### 5.1 `src/agents/pii_scrubber.py`
Implement `def scrub_pii(text: str) -> str`:
- Strip emails (`r"[\w\.-]+@[\w\.-]+\.\w+"`), Indian & international phone numbers (`r"(\+?\d{1,3}[\s-]?)?\d{10}"`), 12-digit numbers, and PAN-like strings before any external web call.

#### 5.2 `src/agents/cypher_queries.py` (Open Triangle Detector)
Find pairs where a Tier-1 friend and a Tier-2/3 target shared an organization (College or Company) but have no direct edge between them:
```cypher
MATCH (u:Person {full_name: 'SELF_USER'})-[:KNOWS|BATCHMATE_OF|ROOMMATE_OF|WORKED_WITH]->(friend:Person)
WHERE friend.reachability_tier = 1
MATCH (friend)-[r1:WORKS_AT|STUDIED_AT]->(org:Organization)<-[r2:WORKS_AT|STUDIED_AT]-(target:Person)
WHERE friend.uid <> target.uid
  AND target.full_name <> 'SELF_USER'
  AND NOT (friend)-[:KNOWS|BATCHMATE_OF|ROOMMATE_OF|WORKED_WITH|CO_AUTHORED_WITH]-(target)
RETURN friend.uid AS friend_uid, friend.full_name AS friend_name,
       target.uid AS target_uid, target.full_name AS target_name,
       org.name AS shared_org
LIMIT 20
```

#### 5.3 `src/agents/search_tools.py`
- Implement `async def execute_osint_queries(person_a: str, person_b: str, shared_org: str) -> List[dict]`:
  - Call `scrub_pii()` on all inputs.
  - Query local SearXNG (`GET {settings.SEARXNG_URL}/search?q={query}&format=json`) with:
    1. `f'"{person_a}" "{person_b}" "{shared_org}"'`
    2. `f'"{person_b}" "{shared_org}" (site:linkedin.com/in OR site:github.com OR site:ieeexplore.org OR site:arxiv.org)'`
  - If SearXNG is unreachable or returns `< 2` results AND `settings.TAVILY_API_KEY` is present, query `https://api.tavily.com/search`.

#### 5.4 `src/agents/osint_graph.py` (LangGraph Workflow with `interrupt()`)
Implement a `StateGraph(OSINTState)` compiled with `AsyncPostgresSaver` (or `MemorySaver` in unit tests when specified):

```python
from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

class OSINTState(TypedDict):
    thread_id: str
    friend_uid: str
    friend_name: str
    target_uid: str
    target_name: str
    shared_org: str
    search_results: List[dict]
    proposed_relation: str
    confidence_score: float
    evidence_summary: str
    source_urls: List[str]
    card_id: Optional[str]
    human_decision: Optional[str]
```

- **Graph Nodes:**
  1. `run_web_recon`: Calls `execute_osint_queries` and populates `search_results`.
  2. `score_hypothesis`: Evaluates snippets for co-authored papers, shared clubs, hackathon rosters, or overlapping tenure. If `confidence_score < 0.50`, routes directly to `END`.
  3. `human_verification_gate`:
     - Persists `HITLEvidenceCard` to PostgreSQL `hitl_evidence_cards` and pushes a Telegram inline keyboard notification via `notifier.send_hitl_card(card)`.
     - Calls **`human_decision = interrupt({"card_id": state["card_id"], "summary": state["evidence_summary"]})`**.
  4. `commit_verified_bridge`:
     - Only executes when resumed with `Command(resume="approve")`.
     - Promotes the candidate relationship in Neo4j: creates `(friend)-[:CO_AUTHORED_WITH|BATCHMATE_OF|WORKED_WITH {verified: true, confidence_score: 1.0, source_episode_id: card_id}]->(target)` and updates `hitl_evidence_cards.status = 'verified'`.

- **Phase 5 Verification Command:** `uv run pytest tests/test_osint_hitl.py -v`

---

### PHASE 6: Module E — Telegram Bot & HITL Bus (`src/hitl_bot/`)

#### 6.1 `src/hitl_bot/notifier.py`
- Format `HITLEvidenceCard` into an HTML Telegram message with an `InlineKeyboardMarkup` containing three buttons:
  - `[ ✅ Confirm & Lock ]` $\rightarrow$ `callback_data=f"hitl:approve:{card.langgraph_thread_id}:{card.card_id}"`
  - `[ ❌ Reject Match ]` $\rightarrow$ `callback_data=f"hitl:reject:{card.langgraph_thread_id}:{card.card_id}"`
  - `[ 🤔 Snooze ]` $\rightarrow$ `callback_data=f"hitl:snooze:{card.langgraph_thread_id}:{card.card_id}"`

#### 6.2 `src/hitl_bot/bot.py` (`aiogram` 3.x)
1. **Authorization Filter:** Every handler MUST verify `event.from_user.id == settings.TELEGRAM_ALLOWED_USER_ID`. Unauthorized users receive no response.
2. **Voice Note Handler (`@router.message(F.voice)`):**
   - Download `.ogg` audio via `bot.download(message.voice)`.
   - Dispatch async Taskiq job `ingest_voice_task.kiq(audio_bytes, message.message_id)`.
   - Reply immediately (`< 300ms`): `"⚡ Logged voice note. Extracting entities & temporal edges..."`.
3. **Text Note Handler (`@router.message(F.text)`):**
   - If text starts with `/path <query>`, call `find_warmest_path(query)` and return the formatted chain.
   - Otherwise, dispatch `ingest_text_task.kiq(message.text)`.
4. **HITL Callback Handler (`@router.callback_query(F.data.startswith("hitl:"))`):**
   - Unpack `_, action, thread_id, card_id = callback.data.split(":")`.
   - Resume LangGraph:
     `await osint_app.ainvoke(Command(resume=action), config={"configurable": {"thread_id": thread_id}})`.
   - Update message via `callback.message.edit_text(f"{callback.message.text}\n\nStatus: {action.upper()} ✅")`.

---

### PHASE 7: Module F — Pathfinding Engine, Decay Cron & Next.js UI

#### 7.1 Weighted Dijkstra Pathfinding (`src/pathfinder/routing.py`)
1. **Edge Weight Cost Formula:**
   Every interpersonal edge $(u, v)$ in Neo4j has a traversal cost calculated dynamically or updated on write:
   $$\text{edge\_cost}(u, v) = \left(\frac{100.0}{\max(\text{trust\_score}_v, 5.0)}\right) \times \text{tier\_multiplier}_v \times \left(\frac{1.0}{\max(\text{confidence\_score}_{u,v}, 0.1)}\right)$$
   Where $\text{tier\_multiplier}_v = 1.0$ for Tier 1, $1.8$ for Tier 2, and $3.0$ for Tier 3.
2. **`async def find_warmest_path(session, target_query: str) -> WarmPathResponse`:**
   - Locate target `:Person` or `:Organization` matching `target_query` (case-insensitive substring or vector match).
   - Compute minimum-cost path from `(:Person {full_name: 'SELF_USER'})` to target up to 4 hops (`1..4`), summing `edge_cost` along all verified relationships (`WHERE all(r IN relationships(path) WHERE coalesce(r.verified, true) = true)`).
   - Return the lowest total cost path as `WarmPathResponse` with an actionable intro request message for the first Tier-1 bridge in the chain.

#### 7.2 Relationship Decay Cron (`src/pathfinder/decay_cron.py`)
1. **Nightly Exponential Trust Decay Formula:**
   Run daily at `02:00 UTC`. For every `:Person` where `reachability_tier IN [1, 2]`:
   $$T_{\text{new}} = \max\left(10.0, \; T_0 \cdot e^{-0.008 \cdot \Delta \text{days}}\right)$$
   Where $\Delta \text{days}$ is days elapsed since `last_contacted_date`.
2. **Bridge Decay Alert:**
   Identify people in the top 15% of network degree/bridge connectivity whose `trust_score` drops below `55.0`, and generate a Sunday morning Telegram reminder.

#### 7.3 REST API Contract (`src/api/routes/`)
Implement these exact FastAPI endpoints:
- `POST /api/v1/ingest/voice` (`UploadFile`) $\rightarrow$ `{"episode_id": "...", "status": "queued"}`
- `POST /api/v1/ingest/text` (`{"text": "..."}`) $\rightarrow$ `EpisodeExtractionResult`
- `POST /api/v1/ingest/csv` (`UploadFile`) $\rightarrow$ `{"imported_count": int}`
- `GET /api/v1/graph/map?tier_max=3` $\rightarrow$ `{"nodes": [...], "edges": [...]}` formatted for Cytoscape.js
- `GET /api/v1/graph/path?target=Stripe` $\rightarrow$ `WarmPathResponse`
- `GET /api/v1/graph/person/{uid}` $\rightarrow$ Full person dossier with temporal career history (`valid_from` $\rightarrow$ `valid_to`) and source transcripts
- `GET /api/v1/hitl/pending` $\rightarrow$ `List[HITLEvidenceCard]`
- `POST /api/v1/hitl/resolve` (`{"card_id": "...", "thread_id": "...", "action": "approve|reject"}`)

#### 7.4 Frontend Command Center (`frontend/`)
- **`NetworkCanvas.tsx`:** Render Cytoscape.js graph with dark background (`#090d16`).
  - Node colors: `SELF_USER` = `#38bdf8` (Sky Blue), Tier 1 = `#10b981` (Emerald), Tier 2 = `#f59e0b` (Amber), Tier 3 = `#f43f5e` (Rose), Organization = `#64748b` (Slate Hexagon).
  - When a user searches a target in the top bar (e.g., `"Stripe"` or `"Siddharth Verma"`), highlight the returned shortest-path nodes and edges in glowing Cyan (`#06b6d4`, `width: 4px`) and dim non-path nodes to `opacity: 0.25`.
- **`DossierDrawer.tsx`:** Slide-over panel showing the selected person's Trust Score gauge, Temporal Career History badges (Active vs Past roles with `valid_from`/`valid_to`), verbatim audio provenance quotes, and a 1-click "Copy Warm Intro Message" button.

- **Phase 7 Verification Command:** `uv run pytest tests/test_pathfinder.py -v`

---

## 6. ORACLE CLOUD ARM64 DEPLOYMENT PLAYBOOK (`scripts/oracle_arm64_setup.sh`)

Create `scripts/oracle_arm64_setup.sh` and mark it executable (`chmod +x`):
```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== [1/5] Updating Ubuntu 24.04 ARM64 (aarch64) packages ==="
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg ufw git jq cron

echo "=== [2/5] Installing Docker Engine & Compose Plugin ==="
if ! command -v docker &> /dev/null; then
    curl -fsSL [https://get.docker.com](https://get.docker.com) | sh
    sudo usermod -aG docker "$USER"
fi

echo "=== [3/5] Installing Tailscale Mesh VPN ==="
if ! command -v tailscale &> /dev/null; then
    curl -fsSL [https://tailscale.com/install.sh](https://tailscale.com/install.sh) | sh
fi

echo "=== [4/5] Hardening Firewall (Allow SSH + Tailscale Interface Only) ==="
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow in on tailscale0
sudo ufw --force enable

echo "=== [5/5] Configuring Nightly 03:00 Backup Cron ==="
mkdir -p "$(pwd)/backups"
CRON_CMD="0 3 * * * cd $(pwd) && docker exec lokachakra-postgres pg_dump -U lokachakra lokachakra_db | gzip > ./backups/pg_\$(date +\%F).sql.gz && find ./backups -type f -mtime +7 -delete"
(crontab -l 2>/dev/null | grep -v "lokachakra-postgres" || true; echo "$CRON_CMD") | crontab -

echo "=== Starting Lokachakra Oracle Cloud ARM64 Stack ==="
docker compose -f docker-compose.yml -f docker-compose.oracle.yml up -d --build
```

---

## 7. END-TO-END VERIFICATION SUITE (`tests/`)

Before declaring the build complete, `uv run pytest -v` MUST pass all four automated test suites with `0` failures:

1. **`tests/test_extractor.py`:**
   - Input: `"Met Ankit from RVCE today. Turns out his roommate Vikram works at Stripe in Bengaluru, and Ankit left TCS last month."`
   - Assertions:
     - `SELF_USER`, `Ankit` (Tier 1), and `Vikram` (Tier 2) are extracted in `result.persons`.
     - `RVCE`, `Stripe`, and `TCS` are extracted in `result.organizations`.
     - Edge `(Ankit)-[WORKS_AT]->(TCS)` has `valid_to is not None`.
     - Edge `(Vikram)-[WORKS_AT]->(Stripe)` has `valid_to is None`.

2. **`tests/test_resolver.py`:**
   - Seed `person_staging` with `ExtractedPerson(full_name="Rahul Sharma", email="rahul@razorpay.com", current_org="Razorpay", alumni_orgs=["IIT Bombay"])`.
   - Test Case A (Deterministic): Pass incoming record with `email="rahul@razorpay.com"` and `full_name="R. S."`. Assert `result.action == ResolutionAction.AUTO_MERGE` and `result.confidence_score == 1.0`.
   - Test Case B (Probabilistic HITL): Pass incoming record `ExtractedPerson(full_name="R. Sharma", alumni_orgs=["IITB"])` with no email/phone. Assert `0.65 <= result.confidence_score < 0.95`, `result.action == ResolutionAction.QUEUE_HITL`, and `result.hitl_card is not None`.
   - Test Case C (New Entity): Pass incoming record `ExtractedPerson(full_name="Zoya Khan", current_org="Zepto")`. Assert `result.action == ResolutionAction.CREATE_NEW_NODE`.

3. **`tests/test_osint_hitl.py`:**
   - Compile `osint_graph` with `MemorySaver` checkpointer and mock `execute_osint_queries` to return a simulated IEEE paper snippet co-authored by `"Rohan"` and `"Siddharth Verma"` at `"IIT Delhi"`.
   - Invoke graph with `thread_id="test-thread-1"`.
   - Assert graph execution pauses at `human_verification_gate` (`state.next == ("human_verification_gate",)`).
   - Resume graph with `Command(resume="approve")`.
   - Assert `commit_verified_bridge` executes and returns `human_decision == "approve"` and `confidence_score == 1.0`.

4. **`tests/test_pathfinder.py`:**
   - Seed two competing paths from `SELF_USER` to target `"Peak XV"`:
     - Path A (Low Trust): `SELF_USER -> Cold Acquaintance (trust=20, tier=2) -> Siddharth (Peak XV)`
     - Path B (High Trust): `SELF_USER -> Best Friend Rohan (trust=95, tier=1) -> Siddharth (Peak XV)`
   - Call `find_warmest_path("Peak XV")`.
   - Assert returned `WarmPathResponse.steps` routes through `"Best Friend Rohan"` and has a lower `total_cost` than Path A.