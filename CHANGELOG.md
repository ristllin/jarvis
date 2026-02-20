# Changelog

All notable changes from JARVIS self-modifications.
## [0.2.1] - 2026-02-20

**Commit:** Add unified_messaging tool (Telegram+email fallback) w/ tests & registry

### Files changed
## [0.2.2] - 2026-02-20

**Commit:** Deploy unified messaging tool

### Files changed
  - .env.example
  - .gitignore
  - CHANGELOG.md
  - README.md
  - backend/jarvis/agents/coding.py
  - backend/jarvis/api/routes.py
  - backend/jarvis/api/schemas.py
  - backend/jarvis/api/websocket.py
  - backend/jarvis/budget/models.py
  - backend/jarvis/budget/tracker.py
  - backend/jarvis/config.py
  - backend/jarvis/core/executor.py
  - backend/jarvis/core/loop.py
  - backend/jarvis/core/planner.py
  - backend/jarvis/core/state.py
  - backend/jarvis/core/watchdog.py
  - backend/jarvis/database.py
  - backend/jarvis/llm/base.py
  - backend/jarvis/llm/providers/anthropic.py
  - backend/jarvis/llm/providers/mistral.py
  - backend/jarvis/llm/providers/ollama.py
  - backend/jarvis/llm/providers/openai.py
  - backend/jarvis/llm/router.py
  - backend/jarvis/main.py
  - backend/jarvis/memory/blob.py
  - backend/jarvis/memory/models.py
  - backend/jarvis/memory/vector.py
  - backend/jarvis/memory/working.py
  - backend/jarvis/models.py
  - backend/jarvis/observability/logger.py
  - backend/jarvis/observability/metrics.py
  - backend/jarvis/safety/prompt_builder.py
  - backend/jarvis/safety/rules.py
  - backend/jarvis/safety/validator.py
  - backend/jarvis/tools/base.py
  - backend/jarvis/tools/budget_query.py
  - backend/jarvis/tools/code_exec.py
  - backend/jarvis/tools/coding_agent.py
  - backend/jarvis/tools/file_ops.py
  - backend/jarvis/tools/git_ops.py
  - backend/jarvis/tools/llm_config.py
  - backend/jarvis/tools/memory_ops.py
  - backend/jarvis/tools/news_monitor.py
  - backend/jarvis/tools/registry.py
  - backend/jarvis/tools/resource_manager.py
  - backend/jarvis/tools/self_modify.py
  - backend/jarvis/tools/web_browse.py
  - backend/jarvis/tools/web_search.py
  - backend/requirements.txt
  - backend/tests/conftest.py
  - ... and 56 more
