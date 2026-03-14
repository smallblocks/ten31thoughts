# Ten31 Thoughts

**Macro Intelligence Service** — Your thesis vs. the world.

A self-hosted StartOS service that coordinates your published macro framework (Ten31 Timestamp) with external macro voices (MacroVoices, Real Vision, etc.) to surface the top mental models for navigating the current macro landscape.

## How It Works

1. **Add RSS feeds** — Classify as "our thesis" or "external interview"
2. **Automatic ingestion** — Polls feeds every 15 minutes
3. **Multi-pass LLM analysis** — 3 passes for your content, 4 passes for external
4. **Convergence engine** — Maps agree/diverge, validates predictions, detects blind spots
5. **Weekly briefing + chat** — Structured briefing doc + RAG-powered chat

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
│     │                 • LLM analysis         │
│     │                 • Weekly synthesis     │
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
| `GET /api/chat/briefings/latest` | Latest weekly briefing |
| `POST /api/feeds/` | Add RSS feed |
| `GET /api/feeds/` | List feeds |
| `POST /api/feeds/poll` | Trigger manual poll |
| `GET /api/analysis/thesis-elements` | Query thesis elements |
| `GET /api/analysis/frameworks` | Query external frameworks |
| `GET /api/analysis/blind-spots` | Query detected blind spots |
| `GET /api/convergence/scorecard` | Prediction accuracy scorecard |
| `GET /api/convergence/narratives` | Narrative evolution arcs |
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
│       ├── Briefings.jsx   # Weekly briefing viewer
│       ├── Feeds.jsx       # Feed management
│       └── Status.jsx      # System health dashboard
└── src/
    ├── app.py              # FastAPI + APScheduler entry
    ├── feeds/
    │   ├── parser.py       # RSS/Atom parsing
    │   ├── extractor.py    # Content extraction
    │   └── manager.py      # Feed CRUD + polling
    ├── analysis/
    │   ├── thesis_passes.py    # 3-pass thesis pipeline
    │   ├── external_passes.py  # 4-pass external pipeline
    │   └── prompts/templates.py
    ├── convergence/
    │   ├── alignment.py    # Agree/diverge mapping
    │   ├── validation.py   # Prediction tracker
    │   ├── blindspots.py   # Mutual blind spot detector
    │   └── narrative.py    # Narrative evolution
    ├── synthesis/
    │   ├── frameworks.py   # Top 5 ranking
    │   └── briefing.py     # Document generator
    ├── llm/router.py       # LiteLLM multi-provider
    ├── db/
    │   ├── models.py       # SQLAlchemy models
    │   ├── session.py      # Centralized DB session
    │   └── vector.py       # ChromaDB vector store
    ├── api/
    │   ├── feeds.py        # Feed endpoints
    │   ├── analysis.py     # Analysis endpoints
    │   ├── convergence.py  # Convergence endpoints
    │   └── chat.py         # Chat + briefing endpoints
    └── worker/
        └── scheduler.py    # APScheduler background jobs
```

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Feed Manager | Done | RSS ingestion, DB schema, feed CRUD |
| 2. Analysis | Done | 7-pass LLM pipeline, vector embeddings |
| 3. Convergence | Done | Alignment, validation, blind spots, narratives |
| 4. Briefing | Done | Top 5 ranking, document generation |
| 5. Chat + UI | Done | RAG chat, React frontend |
| 6. StartOS | Done | Single Dockerfile, manifest, s9pk packaging |
