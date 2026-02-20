# JARVIS Deployment & Verification

Use this skill when deploying changes, adding tools, or finishing a development session.

## Code Sync Chain (must complete before deploy)

1. **Edit** `backend/jarvis/` (source of truth for Docker)
2. **Reverse sync** to `jarvis/`: `rsync -a --exclude='__pycache__' --exclude='tests' backend/jarvis/ jarvis/`
3. **Rebuild image**: `docker build -t jarvis:latest -f Dockerfile .` (compose has no build config)
4. **Restart**: `docker compose down jarvis && docker compose up -d jarvis`
5. **Git**: `git add -A && git commit -m "..." && git push origin main`

## Data Volume Gotcha

- Host `data/` is bind-mounted to `/data` in container
- Entrypoint restores `data/code/backend/` → `/app/` on boot
- If `data/code/` has stale code, it overwrites the image
- **Fix**: `rsync -a --delete backend/jarvis/ data/code/backend/jarvis/` then restart
- Entrypoint now uses full rsync (no `--ignore-existing`) so image always wins on "image update"

## Post-Deploy Checklist (REQUIRED)

1. **Health**: `curl -sf http://localhost:8000/api/status` — status, iteration, version
2. **Tools**: `curl -sf http://localhost:8000/api/tool-status` — verify new tools (e.g. `code_architect`) are registered
3. **Functional tests**: Run inside container:
   ```bash
   docker compose exec jarvis python -c "
   import asyncio
   from jarvis.tools.self_analysis import SelfAnalysisTool
   r = asyncio.run(SelfAnalysisTool().execute(check='functional'))
   print('Success:', r.success)
   print(r.output[:2000])
   "
   ```
4. **New tool test**: If you added a tool, call it or verify it appears in tool-status

## When Adding a New Tool

1. Create `backend/jarvis/tools/my_tool.py`
2. Add import and `default_tools.append(MyTool(...))` in `registry.py`
3. Sync to `jarvis/`, rebuild, restart
4. Verify: `curl -sf localhost:8000/api/tool-status | grep my_tool`
5. Run `self_analysis check=functional` — some tests may skip (e.g. Telegram if not configured)

## Common Failures

- **Tool missing after deploy**: Data backup overwrote image. Sync `backend/jarvis/` → `data/code/backend/jarvis/`, clear `data/code/.image_hash`, restart.
- **Import error on boot**: Missing dependency in `requirements.txt`. Add it, rebuild with `--no-cache`.
- **Revert flag**: If `data/code/.needs_revert` exists, entrypoint reverts to last commit. Remove it and fix the crash cause.
