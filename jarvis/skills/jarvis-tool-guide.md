# JARVIS Tool Usage Guide

## coding_agent — Code Work (FREE with Devstral)
```json
{"tool": "coding_agent", "parameters": {
  "task": "Add a /api/metrics endpoint that returns system stats",
  "system_prompt": "Follow existing code patterns. Use async/await.",
  "tier": "coding_level1",
  "skills": ["jarvis-coding-conventions"]
}}
```
- 50 turns, continuable via `continuation_context`
- Tiers: coding_level1 (best, free), coding_level2 (fast, free), coding_level3 (lightest, free)
- Use `plan_only: true` to get a plan first, then `approved_plan` to execute

## code_architect — Plan Changes (Tier-1 Intelligence)
```json
{"tool": "code_architect", "parameters": {
  "intent": "Add bidirectional Telegram voice messaging",
  "scope": "self_modify"
}}
```
- Uses tier-1 model for deep architectural analysis
- Auto-loads architecture + conventions skills
- Returns structured integration plan for coding_agent

## self_modify — Git Operations
- `action=diff` — see uncommitted changes
- `action=commit message='...'` — commit with auto version bump
- `action=push` — push to GitHub
- `action=pull` — pull and sync to live
- `action=redeploy message='...'` — commit + validate + restart
- `action=revert` — undo last commit
- `action=log` — view git history

## self_analysis — Diagnostics & Functional Tests
- `check=all` — config checks (providers, email, tools, budget)
- `check=functional` — end-to-end tests (email round-trip, LLM ping, vector write+search)
- `check=functional_email` / `functional_telegram` / `functional_llm` / `functional_memory`

## memory_config — Tune Memory
- `action=view` — see current settings
- `action=update` with: retrieval_count (1-100), relevance_threshold (0-1), decay_factor (0.5-1)

## http_request — Any API
```json
{"tool": "http_request", "parameters": {
  "method": "POST",
  "url": "https://api.example.com/data",
  "headers": {"Authorization": "Bearer ..."},
  "body": {"key": "value"}
}}
```

## env_manager — Environment Variables
- `action=list` — see all vars
- `action=get key=VAR_NAME` — read one
- `action=set key=VAR_NAME value=...` — add/update
- `action=delete key=VAR_NAME` — remove

## send_email
```json
{"tool": "send_email", "parameters": {
  "to_email": "user@example.com",
  "subject": "Update from JARVIS",
  "body": "Here's what I've been working on..."
}}
```

## send_telegram
```json
{"tool": "send_telegram", "parameters": {
  "message": "Status update from JARVIS",
  "parse_mode": "Markdown"
}}
```

## web_search + web_browse
```json
{"tool": "web_search", "parameters": {"query": "python aiohttp tutorial"}}
{"tool": "web_browse", "parameters": {"url": "https://docs.python.org/3/"}}
```

## skills — Knowledge Base
- `action=list` — list available skills
- `action=read name=skill-name` — load skill content
- `action=write name=new-skill content=...` — create/update skill

## Recommended Self-Modification Workflow
1. `code_architect` (tier-1 planning) → detailed integration plan
2. Review plan in iteration context
3. `coding_agent` with `approved_plan` (free Devstral) → implement
4. `self_modify action=diff` → verify changes
5. `self_modify action=commit message='...'` → version it
6. `self_modify action=push` → backup to GitHub
