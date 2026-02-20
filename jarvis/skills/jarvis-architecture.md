# JARVIS Architecture

## Directory Structure
```
backend/jarvis/
├── core/           # Main loop, planner, executor, state, listeners
├── llm/            # LLM router, provider implementations
├── memory/         # Vector (ChromaDB), working memory, blob storage
├── tools/          # All tool implementations + registry
├── agents/         # Coding agent, browser agent
├── api/            # FastAPI routes, WebSocket, auth
├── budget/         # Budget tracking, cost estimation
├── safety/         # Validator, prompt builder, immutable rules
├── observability/  # Logging, metrics
├── config.py       # Settings (pydantic, env vars)
├── models.py       # SQLAlchemy ORM models
├── database.py     # DB engine + session factory
└── main.py         # FastAPI app + lifespan startup

frontend/src/
├── components/     # React components (Dashboard, ChatPanel, etc.)
├── api/client.ts   # REST API client wrapper
├── hooks/          # useWebSocket hook
├── types/index.ts  # TypeScript type definitions
└── App.tsx         # Main app with sidebar + tab routing
```

## Core Loop Lifecycle
1. `main.py` lifespan: init DB → init subsystems → start core loop → start listeners
2. `CoreLoop.run()`: infinite loop of iterations
3. Each iteration: load state → plan (LLM) → execute actions → store results → update goals → sleep
4. Chat messages: enqueued via `enqueue_chat()` → processed in next iteration → reply delivered

## Data Flow
```
Creator (Web/Telegram/Email) → enqueue_chat() → CoreLoop
                                                    ↓
                                              Planner (tier-1 LLM)
                                                    ↓
                                              Executor → Tools
                                                    ↓
                                              Results → Vector Memory + Working Memory
                                                    ↓
                                              Reply → Creator (same channel)
```

## Persistence Model
- **Live code**: `/app/` (ephemeral, in-container)
- **Persistent backup**: `/data/code/backend/` (survives restarts)
- **Dual-write**: All code changes go to both live + backup
- **Database**: `/data/jarvis.db` (SQLite via aiosqlite)
- **Vector memory**: `/data/chroma/` (ChromaDB)
- **Blob storage**: `/data/blob/YYYY-MM-DD.jsonl` (append-only audit trail)
- **Skills**: `/data/skills/*.md` (markdown files)

## Key Integration Points
- Tools register in `tools/registry.py` via `_register_defaults()`
- Planner receives tool names via `tool_names` list
- Executor calls `registry.execute(tool_name, parameters)`
- Config flows from env vars → `config.py` Settings class
- WebSocket broadcasts from core loop via `ws_manager.broadcast()`
- Listeners (email, telegram) call `core_loop.enqueue_chat()`

## LLM Tier System
- level1: Opus, GPT-5.2, Grok (best reasoning)
- level2: Sonnet, GPT-4o (moderate)
- level3: Mistral Small, GPT-4o-mini (simple)
- coding_level1/2/3: Devstral models (FREE, optimized for code)
- Router tries providers in order with budget-aware fallback
