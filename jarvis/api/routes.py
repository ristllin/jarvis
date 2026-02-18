import json
import os
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy import select, desc
from jarvis.api.schemas import (
    DirectiveUpdate, MemoryMarkPermanent, BudgetOverride,
    ChatRequest, ChatResponse, GoalsUpdate,
    ProviderBalanceUpdate, AddProviderRequest,
    ShortTermMemoryUpdate,
)
from jarvis.api.websocket import ws_manager
from jarvis.observability.logger import get_logger

log = get_logger("api")

router = APIRouter(prefix="/api")


def get_app_state():
    """Get shared app state — set during startup."""
    from jarvis.main import app_state
    return app_state


@router.get("/status")
async def get_status():
    state = get_app_state()
    current = await state["state_manager"].get_state()
    core_loop = state.get("core_loop")
    sleep_info = {}
    if core_loop:
        sleep_info = {
            "current_sleep_seconds": core_loop._current_sleep_seconds,
            "min_sleep_seconds": 10,
            "max_sleep_seconds": 3600,
        }
    return {
        "status": "running" if not current.get("is_paused") else "paused",
        **current,
        **sleep_info,
    }


@router.get("/budget")
async def get_budget():
    state = get_app_state()
    return await state["budget"].get_status()


@router.get("/memory/stats")
async def get_memory_stats():
    state = get_app_state()
    vector_stats = state["vector"].get_stats()
    blob_stats = state["blob"].get_stats()
    return {
        "vector": vector_stats,
        "blob": blob_stats,
    }


@router.get("/memory/vector")
async def browse_vector_memory(query: str = None, limit: int = 50, offset: int = 0):
    """Browse or search vector memories."""
    state = get_app_state()
    vector = state["vector"]
    if query:
        entries = vector.search(query, n_results=limit)
    else:
        entries = vector.get_all(limit=limit, offset=offset)
    total = vector.get_stats()["total_entries"]
    return {"entries": entries, "total": total, "limit": limit, "offset": offset}


@router.delete("/memory/vector/{memory_id}")
async def delete_vector_memory(memory_id: str):
    """Delete a vector memory entry."""
    state = get_app_state()
    state["vector"].delete_memory(memory_id)
    return {"ok": True}


@router.get("/memory/blob")
async def browse_blob(event_type: str = None, limit: int = 50):
    """Browse blob storage entries with optional type filter."""
    state = get_app_state()
    blob = state["blob"]
    entries = blob.read_filtered(event_type=event_type, limit=limit)
    event_types = blob.get_event_types()
    stats = blob.get_stats()
    return {"entries": entries, "event_types": event_types, "stats": stats}


@router.get("/memory/working")
async def get_working_memory():
    """Get current working memory snapshot — what JARVIS is currently using."""
    state = get_app_state()
    planner = state.get("planner")
    if planner and hasattr(planner, "working"):
        snapshot = planner.working.get_working_snapshot()
        return snapshot
    return {"error": "Working memory not available", "injected_memories": [], "config": {}}


@router.put("/memory/config")
async def update_memory_config(body: dict):
    """Update memory retrieval config (retrieval_count, relevance_threshold, etc.)"""
    state = get_app_state()
    planner = state.get("planner")
    if planner and hasattr(planner, "working"):
        allowed_keys = {"retrieval_count", "max_context_tokens", "decay_factor", "relevance_threshold"}
        updates = {k: v for k, v in body.items() if k in allowed_keys}
        if "retrieval_count" in updates:
            updates["retrieval_count"] = max(1, min(100, int(updates["retrieval_count"])))
        planner.working.update_config(**updates)
        return {"ok": True, "config": planner.working.memory_config}
    return {"ok": False, "error": "Planner not available"}


@router.get("/logs")
async def get_logs(limit: int = 50):
    state = get_app_state()
    entries = state["blob"].read_recent(limit=limit)
    return {"logs": entries}


@router.get("/tools")
async def get_tools():
    state = get_app_state()
    return {"tools": state["tools"].get_tool_schemas()}


@router.get("/models")
async def get_models():
    state = get_app_state()
    return {
        "tiers": state["router"].get_tier_info(),
        "available_providers": state["router"].get_available_providers(),
    }


@router.post("/directive")
async def update_directive(body: DirectiveUpdate):
    state = get_app_state()
    await state["state_manager"].update(directive=body.directive)
    log.info("directive_updated", directive=body.directive[:80])
    await ws_manager.broadcast({"type": "directive_updated", "directive": body.directive})
    return {"ok": True}


@router.post("/goals")
async def update_goals(body: GoalsUpdate):
    """Update tiered goals directly."""
    state = get_app_state()
    updates = {}
    if body.short_term is not None:
        updates["short_term_goals"] = body.short_term
        updates["current_goals"] = body.short_term
    if body.mid_term is not None:
        updates["mid_term_goals"] = body.mid_term
    if body.long_term is not None:
        updates["long_term_goals"] = body.long_term
    if updates:
        await state["state_manager"].update(**updates)
    return {"ok": True, "updated": list(updates.keys())}


@router.post("/memory/mark-permanent")
async def mark_memory_permanent(body: MemoryMarkPermanent):
    state = get_app_state()
    state["vector"].mark_permanent(body.memory_id)
    return {"ok": True}


@router.get("/memory/short-term")
async def get_short_term_memories():
    """Get all short-term memories (scratch pad)."""
    state = get_app_state()
    current = await state["state_manager"].get_state()
    return {
        "memories": current.get("short_term_memories", []),
        "count": len(current.get("short_term_memories", [])),
        "max_entries": 50,
        "max_age_hours": 48,
    }


@router.post("/memory/short-term")
async def update_short_term_memories(body: ShortTermMemoryUpdate):
    """Manage short-term memories: add, remove, or replace."""
    state = get_app_state()
    sm = state["state_manager"]
    current = await sm.get_state()
    iteration = current.get("iteration", 0)

    if body.replace is not None:
        await sm.replace_short_term_memories(body.replace, iteration)
        return {"ok": True, "action": "replaced", "count": len(body.replace)}
    actions = []
    if body.remove:
        await sm.remove_short_term_memories(body.remove)
        actions.append(f"removed {len(body.remove)}")
    if body.add:
        await sm.add_short_term_memories(body.add, iteration)
        actions.append(f"added {len(body.add)}")
    return {"ok": True, "actions": actions}


@router.delete("/memory/short-term")
async def clear_short_term_memories():
    """Clear all short-term memories."""
    state = get_app_state()
    await state["state_manager"].clear_short_term_memories()
    return {"ok": True, "action": "cleared"}


@router.get("/news")
async def get_news():
    """Fetch news data from the news monitoring service."""
    from jarvis.tools.news_monitor import NewsMonitorTool
    news_tool = NewsMonitorTool()
    result = await news_tool.execute(query="latest news", max_results=5)
    return {"news": result.output}


@router.post("/control/pause")
async def pause():
    state = get_app_state()
    await state["state_manager"].set_paused(True)
    await ws_manager.broadcast({"type": "state_update", "status": "paused"})
    return {"ok": True, "status": "paused"}


@router.post("/control/resume")
async def resume():
    state = get_app_state()
    await state["state_manager"].set_paused(False)
    # Also wake the loop so it doesn't wait for the current sleep to finish
    core_loop = state.get("core_loop")
    if core_loop:
        core_loop.wake()
    await ws_manager.broadcast({"type": "state_update", "status": "running"})
    return {"ok": True, "status": "running"}


@router.post("/control/wake")
async def wake():
    """Interrupt JARVIS's current sleep and trigger the next iteration immediately."""
    state = get_app_state()
    core_loop = state.get("core_loop")
    if core_loop:
        core_loop.wake()
        return {"ok": True, "message": "JARVIS woken up — next iteration starting"}
    return {"ok": False, "message": "Core loop not available"}


@router.post("/budget/override")
async def override_budget(body: BudgetOverride):
    state = get_app_state()
    from jarvis.models import BudgetConfig
    async with state["session_factory"]() as session:
        config = await session.get(BudgetConfig, 1)
        if config:
            config.monthly_cap_usd = body.new_cap_usd
            await session.commit()
    return {"ok": True, "new_cap": body.new_cap_usd}


# ── Provider balance management ───────────────────────────────────────────

@router.get("/providers")
async def get_providers():
    """Get per-provider balance and spending info."""
    state = get_app_state()
    budget_status = await state["budget"].get_status()
    return {"providers": budget_status.get("providers", [])}


@router.put("/providers/{provider}")
async def update_provider(provider: str, body: ProviderBalanceUpdate):
    """Update a provider's known balance, tier, currency, or notes."""
    state = get_app_state()
    result = await state["budget"].update_provider_balance(
        provider=provider,
        known_balance=body.known_balance,
        tier=body.tier,
        currency=body.currency,
        notes=body.notes,
        reset_spending=body.reset_spending,
    )
    return {"ok": True, **result}


@router.post("/providers")
async def add_provider(body: AddProviderRequest):
    """Add a new provider or update an existing one's API key."""
    state = get_app_state()
    result = await state["budget"].add_provider(
        provider=body.provider,
        api_key=body.api_key,
        known_balance=body.known_balance,
        tier=body.tier,
        currency=body.currency,
        notes=body.notes,
    )
    return {"ok": True, **result}


# ── Chat endpoint ──────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    """Chat with JARVIS — fully agentic.

    The message is injected into the main autonomous loop's next iteration.
    JARVIS sees it in its full context (goals, memories, tools) and can
    take actions alongside replying.  The HTTP request blocks until the
    iteration completes and delivers the reply.
    """
    import asyncio

    state = get_app_state()
    blob = state["blob"]
    core_loop = state.get("core_loop")

    # Record creator message in blob + DB
    blob.store(
        event_type="chat_creator",
        content=body.message,
        metadata={"role": "creator"},
    )
    from jarvis.models import ChatMessage
    async with state["session_factory"]() as session:
        msg = ChatMessage(role="creator", content=body.message)
        session.add(msg)
        await session.commit()

    if not core_loop:
        return ChatResponse(
            reply="Core loop is not running. Please wait for JARVIS to start.",
            agentic=False,
        )

    # Enqueue the message into the main loop — this wakes it immediately
    pending = core_loop.enqueue_chat(body.message)

    # Wait for the loop iteration to complete and deliver the reply
    # Timeout after 120 seconds (iterations with tool use can take a while)
    try:
        await asyncio.wait_for(pending.response_event.wait(), timeout=120.0)
    except asyncio.TimeoutError:
        return ChatResponse(
            reply="I'm still processing your message — the current iteration is taking longer than expected. "
                  "Check the dashboard for my response.",
            agentic=True,
        )

    reply_text = pending.response_text

    # Record JARVIS reply in blob + DB
    blob.store(
        event_type="chat_jarvis",
        content=reply_text,
        metadata={"role": "jarvis", "agentic": True},
    )
    async with state["session_factory"]() as session:
        msg = ChatMessage(
            role="jarvis",
            content=reply_text,
            metadata_={"agentic": True, "actions": len(pending.actions_taken)},
        )
        session.add(msg)
        await session.commit()

    # Broadcast chat event via WebSocket
    await ws_manager.broadcast({
        "type": "chat_message",
        "role": "jarvis",
        "content": reply_text[:200],
        "agentic": True,
    })

    return ChatResponse(
        reply=reply_text,
        actions_taken=pending.actions_taken if pending.actions_taken else None,
        agentic=True,
    )


@router.get("/chat/history")
async def get_chat_history(limit: int = 50):
    """Get chat history."""
    state = get_app_state()
    history = await _get_chat_history(state["session_factory"], limit=limit)
    return {"messages": history}


async def _get_chat_history(session_factory, limit: int = 50) -> list[dict]:
    """Retrieve recent chat messages from DB."""
    from jarvis.models import ChatMessage
    async with session_factory() as session:
        result = await session.execute(
            select(ChatMessage).order_by(desc(ChatMessage.id)).limit(limit)
        )
        messages = result.scalars().all()
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                "metadata": m.metadata_ or {},
            }
            for m in reversed(messages)
        ]


@router.get("/history")
async def get_history(limit: int = 20):
    """Return recent repo change history from blob storage."""
    state = get_app_state()
    entries = state["blob"].read_recent(limit=200)
    git_entries = [e for e in entries if "git" in e.get("content", "").lower() or e.get("metadata", {}).get("tool") == "git"]
    return {"history": git_entries[:limit]}


# ── Analytics ──────────────────────────────────────────────────────────

@router.get("/analytics")
async def get_analytics(range: str = "24h"):
    """
    Return time-series analytics data for charts.
    Range: 1h, 6h, 24h, 7d, 30d
    Returns buckets with: cost, tokens, model calls, tool calls, errors.
    """
    from datetime import timedelta
    from sqlalchemy import text

    state = get_app_state()
    session_factory = state["session_factory"]

    # Parse range into timedelta and bucket size
    range_map = {
        "1h":  (timedelta(hours=1),   "5 minutes",  300),
        "6h":  (timedelta(hours=6),   "30 minutes", 1800),
        "24h": (timedelta(hours=24),  "1 hour",     3600),
        "7d":  (timedelta(days=7),    "6 hours",    21600),
        "30d": (timedelta(days=30),   "1 day",      86400),
    }
    delta, bucket_label, bucket_secs = range_map.get(range, range_map["24h"])
    since = datetime.now(timezone.utc) - delta
    # SQLite stores timestamps without timezone — use compatible format
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    async with session_factory() as session:
        # 1. Budget usage time series (cost, tokens, model breakdown)
        budget_rows = await session.execute(
            text("""
                SELECT
                    timestamp, provider, model,
                    input_tokens, output_tokens, cost_usd,
                    task_description
                FROM budget_usage
                WHERE timestamp >= :since
                ORDER BY timestamp
            """),
            {"since": since_str},
        )
        budget_data = budget_rows.fetchall()

        # 2. Tool usage time series
        tool_rows = await session.execute(
            text("""
                SELECT
                    timestamp, tool_name, success,
                    duration_ms, error
                FROM tool_usage_log
                WHERE timestamp >= :since
                ORDER BY timestamp
            """),
            {"since": since_str},
        )
        tool_data = tool_rows.fetchall()

    # Build time buckets
    now = datetime.now(timezone.utc)
    buckets = {}
    t = since
    while t <= now:
        key = t.strftime("%Y-%m-%dT%H:%M")
        buckets[key] = {
            "time": key,
            "cost": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "llm_calls": 0,
            "tool_calls": 0,
            "tool_errors": 0,
            "models": {},
            "providers": {},
            "tools": {},
        }
        t += timedelta(seconds=bucket_secs)

    def _bucket_key(ts_str):
        """Find the right bucket for a timestamp."""
        try:
            if isinstance(ts_str, str):
                # Handle SQLite format "2026-02-16 05:36:00" and ISO format
                ts_clean = ts_str.replace("Z", "+00:00")
                try:
                    ts = datetime.fromisoformat(ts_clean)
                except ValueError:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts_str
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            # Find the bucket start
            elapsed = (ts - since).total_seconds()
            if elapsed < 0:
                return None
            bucket_idx = int(elapsed // bucket_secs)
            bucket_start = since + timedelta(seconds=bucket_idx * bucket_secs)
            return bucket_start.strftime("%Y-%m-%dT%H:%M")
        except Exception:
            return None

    # Fill budget data into buckets
    for row in budget_data:
        ts, provider, model, inp_tok, out_tok, cost, task = row
        key = _bucket_key(ts)
        if key and key in buckets:
            b = buckets[key]
            b["cost"] += cost or 0
            b["input_tokens"] += inp_tok or 0
            b["output_tokens"] += out_tok or 0
            b["llm_calls"] += 1
            b["models"][model] = b["models"].get(model, 0) + 1
            b["providers"][provider] = b["providers"].get(provider, 0) + 1

    # Fill tool data into buckets
    for row in tool_data:
        ts, tool_name, success, duration, error = row
        key = _bucket_key(ts)
        if key and key in buckets:
            b = buckets[key]
            b["tool_calls"] += 1
            if not success:
                b["tool_errors"] += 1
            b["tools"][tool_name] = b["tools"].get(tool_name, 0) + 1

    # Convert to sorted list
    series = sorted(buckets.values(), key=lambda x: x["time"])

    # Compute summaries
    total_cost = sum(b["cost"] for b in series)
    total_llm = sum(b["llm_calls"] for b in series)
    total_tools = sum(b["tool_calls"] for b in series)
    total_errors = sum(b["tool_errors"] for b in series)
    total_input = sum(b["input_tokens"] for b in series)
    total_output = sum(b["output_tokens"] for b in series)

    # Aggregate model/provider/tool counts across all buckets
    all_models: dict[str, int] = {}
    all_providers: dict[str, int] = {}
    all_tools: dict[str, int] = {}
    for b in series:
        for m, c in b["models"].items():
            all_models[m] = all_models.get(m, 0) + c
        for p, c in b["providers"].items():
            all_providers[p] = all_providers.get(p, 0) + c
        for t, c in b["tools"].items():
            all_tools[t] = all_tools.get(t, 0) + c

    # Simplify series for the chart (remove nested dicts)
    chart_series = []
    for b in series:
        chart_series.append({
            "time": b["time"],
            "cost": round(b["cost"], 6),
            "input_tokens": b["input_tokens"],
            "output_tokens": b["output_tokens"],
            "llm_calls": b["llm_calls"],
            "tool_calls": b["tool_calls"],
            "tool_errors": b["tool_errors"],
        })

    return {
        "range": range,
        "bucket_label": bucket_label,
        "since": since.isoformat(),
        "summary": {
            "total_cost": round(total_cost, 4),
            "total_llm_calls": total_llm,
            "total_tool_calls": total_tools,
            "total_tool_errors": total_errors,
            "error_rate": round(total_errors / total_tools * 100, 1) if total_tools > 0 else 0,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "models": all_models,
            "providers": all_providers,
            "tools": all_tools,
        },
        "series": chart_series,
    }


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
