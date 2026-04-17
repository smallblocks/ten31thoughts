# Ten31 Thoughts

**Macro Intelligence Service** — Your thesis vs. the world.

A self-hosted StartOS service that ingests your published macro framework (Ten31 Timestamp) and external macro voices (MacroVoices, Real Vision, etc.), extracts notes, finds connections between content and your thinking, and surfaces insights through a RAG-powered chat interface.

## How It Works (v3 Architecture)

1. **Add RSS feeds** — Classify as "our thesis" or "external interview"
2. **Automatic ingestion** — Polls feeds daily, extracts and indexes content
3. **Note extraction** — Pulls key insights from content into personal notes
4. **Connection pass** — Finds connections between new content and existing notes using classical principles
5. **Unconnected signals** — Surfaces content that doesn't match existing notes (potential new threads)
6. **Digest + Chat** — Daily digest of connections + RAG-powered chat

## Architecture

Single-container design for StartOS compatibility:

```
┌─────────────────────────────────────────────┐
│  Ten31 Thoughts (single Docker container)   │
│                                             │
│  FastAPI ─── React UI ─── APScheduler       │
│     │            │            │              │
│     │     ┌──────┘      ┌────┘              │
│     ▼     ▼             ▼                   │
│  REST API + Chat    Background Jobs         │
│     │                 • Feed polling         │
│     │                 • Content analysis     │
│     ▼                                       │
│  SQLite ──── ChromaDB (embedded)            │
│  (structured)  (vector embeddings)          │
│                                             │
│  LiteLLM Router ──→ Claude / OpenAI / Ollama│
└─────────────────────────────────────────────┘
```

## Quick Start (StartOS)

1. Install the `ten31-thoughts.s9pk` package via StartOS UI
2. Configure your LLM API key in service settings
3. Open the web interface from your StartOS dashboard
4. The system auto-seeds Ten31 Timestamp + MacroVoices feeds

## Quick Start (Development)

```bash
cp .env.example .env
# Edit .env with your API key(s)

pip install -r requirements.txt
python scripts/seed_feeds.py
uvicorn src.app:app --port 8431

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

## Building the s9pk

```bash
# Install start-sdk
git clone -b latest --recursive https://github.com/Start9Labs/start-os.git
cd start-os/core && ./install-sdk.sh && start-sdk init

# Build
cd ten31-thoughts
make
# Produces ten31-thoughts.s9pk
```

## API Endpoints

| Route | Description |
|-------|-------------|
| `POST /api/chat/` | Send message to intelligence assistant |
| `POST /api/feeds/` | Add RSS feed |
| `GET /api/feeds/` | List feeds |
| `POST /api/feeds/poll` | Trigger manual poll |
| `GET /api/episodes/` | List analyzed episodes |
| `GET /api/analysis/thesis-elements` | Query thesis elements |
| `GET /api/principles/` | Browse classical reference library |
| `GET /api/principles/domains` | List classical domains |
| `GET /api/health` | Health check |
| `GET /api/status` | System status with stats |

## Project Structure

```
ten31-thoughts/
├── Dockerfile              # Single container for StartOS
├── Makefile                # Build s9pk package
├── manifest.yaml           # StartOS service manifest
├── INSTRUCTIONS.md         # StartOS service instructions
├── LICENSE
├── requirements.txt
├── scripts/seed_feeds.py
├── frontend/               # React + Vite + Tailwind
│   └── src/components/
│       ├── Chat.jsx        # RAG chat interface
│       ├── Briefings.jsx   # Briefing viewer
│       ├── Feeds.jsx       # Feed management
│       └── Status.jsx      # System health dashboard
└── src/
    ├── app.py              # FastAPI + APScheduler entry
    ├── feeds/
    │   ├── parser.py       # RSS/Atom parsing
    │   ├── extractor.py    # Content extraction
    │   └── manager.py      # Feed CRUD + polling
    ├── analysis/
    │   ├── classical_reference.py  # Classical principles library
    │   ├── connection_pass.py      # Content-to-note connections
    │   ├── note_extractor.py       # Note extraction from content
    │   └── prompts/templates.py    # Prompt templates
    ├── synthesis/
    │   ├── digest.py       # Daily digest generation
    │   └── briefing.py     # Legacy briefing reader
    ├── llm/router.py       # LiteLLM multi-provider
    ├── db/
    │   ├── models.py       # SQLAlchemy models
    │   ├── session.py      # Centralized DB session
    │   └── vector.py       # ChromaDB vector store
    ├── api/
    │   ├── feeds.py        # Feed endpoints
    │   ├── analysis.py     # Analysis endpoints
    │   ├── episodes.py     # Episode listing
    │   ├── principles.py   # Classical library endpoints
    │   ├── chat.py         # Chat endpoint
    │   ├── search.py       # Search endpoint
    │   └── upload.py       # Upload endpoint
    └── worker/
        └── scheduler.py    # APScheduler background jobs
```

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Feed Manager | Done | RSS ingestion, DB schema, feed CRUD |
| 2. v3 Schema | Done | Notes, connections, signals, spaced repetition |
| 3. Content Analysis | Done | Connection pass, note extraction |
| 4. Digest | Done | Daily digest of connections and signals |
| 5. Chat + UI | Done | RAG chat, React frontend |
| 6. StartOS | Done | Single Dockerfile, manifest, s9pk packaging |
