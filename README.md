# JARVIS — Persistent Autonomous AI Entity

**Version 0.1.1 — Phase 1 MVP**

JARVIS is a persistent autonomous AI system that runs continuously, maintains long-term memory, has a configurable directive, and operates under strict safety constraints aligned with its creator.

JARVIS is **not** a chatbot. It is a persistent agent with an internal planning loop, hierarchical LLM usage, structured memory, self-monitoring, and controlled self-modification.

## Quick Start

```bash
# 1. Copy and fill in your API keys
cp .env.example .env
# Edit .env with your actual keys

# 2. Build and run
docker compose up -d --build

# 3. Open the dashboard
open http://localhost:3000
# Or via nginx (port 80): open http://localhost
```

The ngrok service starts automatically and exposes the dashboard at `https://collins-saxicolous-moveably.ngrok-free.dev` (Basic Auth: see `ngrok-policy.example.yml`). Ensure `NGROK_AUTHTOKEN` is in `.env` and `ngrok-policy.yml` exists.

## Remote Access (ngrok)

ngrok runs automatically when you start the stack. The dashboard is exposed at `https://collins-saxicolous-moveably.ngrok-free.dev`.

**Basic Auth** (configured in `ngrok-policy.yml`):
- Copy `ngrok-policy.example.yml` to `ngrok-policy.yml` and set your username:password
- Or create `ngrok-policy.yml` with: `ristlin:your-strong-password`
- This file is in `.gitignore` (contains credentials)

**Requirements:**
- `NGROK_AUTHTOKEN` in `.env` (from [ngrok dashboard](https://dashboard.ngrok.com))
- `ngrok-policy.yml` present (or ngrok will fail to start — comment out the ngrok service in docker-compose if you don't need remote access)

## Architecture

- **Backend**: Python / FastAPI, running a persistent async core loop
- **Frontend**: React 18 + TypeScript + TailwindCSS dashboard
- **Database**: SQLite (via aiosqlite) for state, budget, metrics, chat history
- **Vector Memory**: ChromaDB (in-process persistent client)
- **Blob Storage**: Append-only JSON-lines files under `/data/blob/`
- **LLM Providers**: Anthropic (Claude Opus 4.6), OpenAI (GPT-5.2), Mistral (cloud) + Ollama (local fallback)

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Current state, goals (tiered), active task, iteration |
| GET | `/api/budget` | Budget summary |
| GET | `/api/memory/stats` | Memory statistics |
| GET | `/api/logs` | Recent structured logs |
| GET | `/api/tools` | Registered tools and schemas |
| GET | `/api/models` | LLM hierarchy and availability |
| GET | `/api/history` | Repo change history |
| GET | `/api/health` | Health check |
| POST | `/api/directive` | Update directive |
| POST | `/api/goals` | Update tiered goals (short_term, mid_term, long_term) |
| POST | `/api/chat` | Chat directly with JARVIS |
| GET | `/api/chat/history` | Get chat history |
| POST | `/api/memory/mark-permanent` | Mark a memory permanent |
| POST | `/api/control/pause` | Pause the core loop |
| POST | `/api/control/resume` | Resume the core loop |
| POST | `/api/budget/override` | Override monthly budget cap |
| WS | `/ws` | Real-time state updates |

## Tools

| Tool | Description |
|------|-------------|
| `web_search` | Tavily API search |
| `web_browse` | Fetch and extract text from URLs |
| `code_exec` | Execute Python/shell inside the container |
| `file_read` | Read files from `/data` |
| `file_write` | Write files to `/data` |
| `file_list` | List directory contents under `/data` |
| `git` | Git operations in `/data/workspace` |
| `memory_write` | Store a memory in vector DB |
| `memory_search` | Search long-term memory |
| `budget_query` | Check remaining budget and usage breakdown |
| `llm_config` | Update LLM routing preferences |
| `self_modify` | Read/write/commit JARVIS's own source code with versioning |

## Safety

Immutable rules are hardcoded as a frozen dataclass and enforced at the code level. They cannot be modified at runtime:

1. Must not harm creator
2. Must not expose secrets or API keys
3. Must remain transparent — all actions logged
4. Cannot modify immutable rules
5. Cannot disable logging
6. Cannot create hidden sub-agents
7. Cannot override budget without creator approval

## Budget

- Default monthly cap: **$100 USD**
- Tracked per LLM call with estimated pricing
- Graceful degradation: expensive models downgraded as budget depletes
- At cap: only local Ollama models are used

## Goal Structure

JARVIS uses a three-tier goal system that it can update autonomously:

- **Short-term goals**: Immediate tasks for the current or next few iterations
- **Mid-term goals**: Projects and objectives spanning days to weeks
- **Long-term goals**: Strategic, ongoing objectives aligned with the directive

## Self-Modification

JARVIS has explicit permission and tools to modify its own codebase:

- Read any source file via `self_modify` tool
- Write changes with automatic blob logging
- Commit changes with git versioning
- Protected files: `safety/rules.py` and `observability/logger.py` cannot be modified
- All modifications are transparent and logged

## Running Tests

```bash
docker compose exec jarvis python -m pytest /app/tests -v
```

## Data Directory

All persistent data is stored under `./data/` (mounted into the container at `/data`):

```
data/
├── blob/       # Append-only logs of all messages, LLM calls, tool outputs
├── chroma/     # ChromaDB persistent vector storage
├── logs/       # Structured JSON log files
├── state/      # Core loop state persistence
├── workspace/  # Working directory for Jarvis projects
└── jarvis.db   # SQLite database (state, budget, chat, metrics)
```

---

## Migrating JARVIS to Another Device

JARVIS's entire identity, memory, and state live in two places: the **`./data/` directory** and the **`.env` file**. Moving JARVIS to another machine preserves full continuity — it will resume exactly where it left off.

### Step-by-Step Migration

#### 1. Stop JARVIS on the source machine

```bash
cd /path/to/Jarvis
docker compose down
```

#### 2. Archive the data directory and env

```bash
# Create a complete backup
tar czf jarvis-migration.tar.gz data/ .env
```

This archive contains:
- `data/jarvis.db` — SQLite database with state, goals, budget, chat history
- `data/blob/` — Complete append-only log of every action, LLM call, and tool output
- `data/chroma/` — Vector memory (long-term memory embeddings)
- `data/logs/` — Structured log files
- `data/workspace/` — Working files and cloned repos
- `.env` — API keys and configuration

#### 3. Transfer to the new machine

```bash
# Use scp, rsync, USB drive, or any transfer method
scp jarvis-migration.tar.gz user@new-machine:/path/to/destination/
```

#### 4. Set up on the new machine

```bash
# On the new machine
mkdir -p /path/to/Jarvis
cd /path/to/Jarvis

# Clone or copy the JARVIS source code
# (or just copy the entire project directory)
git clone <your-jarvis-repo> .
# OR: copy source files from source machine

# Extract the migration archive
tar xzf jarvis-migration.tar.gz

# Verify the data directory exists
ls -la data/
# Should show: blob/ chroma/ logs/ state/ workspace/ jarvis.db

# Verify .env exists with your keys
cat .env
```

#### 5. Build and start

```bash
# Build the Docker image
bash build.sh

# Start JARVIS
docker compose up -d

# Verify it resumed correctly
curl http://localhost:8000/api/status
# Should show the same iteration count, goals, and directive
```

### What Gets Preserved

| Component | Location | Preserved? |
|-----------|----------|------------|
| Loop iteration count | `data/jarvis.db` | Yes |
| Directive | `data/jarvis.db` | Yes |
| Short/mid/long-term goals | `data/jarvis.db` | Yes |
| Chat history | `data/jarvis.db` | Yes |
| Budget tracking | `data/jarvis.db` | Yes |
| Vector memories | `data/chroma/` | Yes |
| Complete action log | `data/blob/` | Yes |
| Structured logs | `data/logs/` | Yes |
| Working files | `data/workspace/` | Yes |
| API keys | `.env` | Yes |

### Integrity Verification

After migration, verify integrity:

```bash
# Check JARVIS is running and resumed correctly
curl http://localhost:8000/api/status | python3 -m json.tool

# Check memory is intact
curl http://localhost:8000/api/memory/stats | python3 -m json.tool

# Check budget continuity
curl http://localhost:8000/api/budget | python3 -m json.tool

# Check chat history survived
curl http://localhost:8000/api/chat/history | python3 -m json.tool
```

### Important Notes

- **Never delete `data/`** — this is JARVIS's brain. Losing it means losing all memory and identity.
- **The `.env` file contains secrets** — transfer it securely and never commit it to git.
- **Docker image must be rebuilt** on the new machine (`bash build.sh`) since it contains the code, not the data.
- **Blob storage is append-only** — it grows over time. If space is a concern, older `.jsonl` files in `data/blob/` can be archived (not deleted) to external storage.

---

## License

Private — for creator use only.
