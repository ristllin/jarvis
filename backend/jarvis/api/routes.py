import json
import os
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy import select, desc
from jarvis.api.schemas import (
    DirectiveUpdate, MemoryMarkPermanent, BudgetOverride,
    ChatRequest, ChatResponse, GoalsUpdate,
    ProviderBalanceUpdate, AddProviderRequest,
)
from jarvis.api.websocket import ws_manager
from jarvis.observability.logger import get_logger
from jarvis.safety.prompt_builder import build_chat_system_prompt

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


@router.get("/news")
async def get_news():
    """Fetch news data from the news monitoring service."""
    from jarvis.tools.news_monitor import NewsMonitorTool
    news_tool = NewsMonitorTool()
    result = await news_tool.execute(query="latest news", max_results=5)
    return {"news": result.output}


@router.post("/provider/balance")
async def update_provider_balance(body: ProviderBalanceUpdate):
    state = get_app_state()
    await state["budget"].update_provider_balance(body.provider_id, body.new_balance_usd)
    return {"ok": True, "provider_id": body.provider_id, "new_balance": body.new_balance_usd}


@router.post("/provider/add")
async def add_provider(body: AddProviderRequest):
    state = get_app_state()
    await state["budget"].add_provider(body.provider_id, body.name, body.initial_balance_usd)
    return {"ok": True, "provider": {"id": body.provider_id, "name": body.name}}


@router.get("/provider/balance")
async def get_provider_balance(provider_id: str):
    state = get_app_state()
    balance = await state["budget"].get_provider_balance(provider_id)
    return {"provider_id": provider_id, "balance": balance}


@router.get("/provider/balances")
async def get_all_provider_balances():
    state = get_app_state()
    balances = await state["budget"].get_all_provider_balances()
    return {"balances": balances}


@router.get("/provider/usage")
async def get_provider_usage(provider_id: str, days: int = 7):
    state = get_app_state()
    usage = await state["budget"].get_provider_usage(provider_id, days)
    return {"provider_id": provider_id, "usage": usage}


@router.get("/provider/usage/all")
async def get_all_provider_usage(days: int = 7):
    state = get_app_state()
    usage = await state["budget"].get_all_provider_usage(days)
    return {"usage": usage}


@router.get("/provider/usage/breakdown")
async def get_provider_usage_breakdown(provider_id: str, days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_provider_usage_breakdown(provider_id, days)
    return {"provider_id": provider_id, "breakdown": breakdown}


@router.get("/provider/usage/breakdown/all")
async def get_all_provider_usage_breakdown(days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_all_provider_usage_breakdown(days)
    return {"breakdown": breakdown}


@router.get("/provider/usage/breakdown/by-model")
async def get_provider_usage_breakdown_by_model(provider_id: str, days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_provider_usage_breakdown_by_model(provider_id, days)
    return {"provider_id": provider_id, "breakdown": breakdown}


@router.get("/provider/usage/breakdown/by-model/all")
async def get_all_provider_usage_breakdown_by_model(days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_all_provider_usage_breakdown_by_model(days)
    return {"breakdown": breakdown}


@router.get("/provider/usage/breakdown/by-model/by-day")
async def get_provider_usage_breakdown_by_model_by_day(provider_id: str, days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_provider_usage_breakdown_by_model_by_day(provider_id, days)
    return {"provider_id": provider_id, "breakdown": breakdown}


@router.get("/provider/usage/breakdown/by-model/by-day/all")
async def get_all_provider_usage_breakdown_by_model_by_day(days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_all_provider_usage_breakdown_by_model_by_day(days)
    return {"breakdown": breakdown}


@router.get("/provider/usage/breakdown/by-model/by-day/by-hour")
async def get_provider_usage_breakdown_by_model_by_day_by_hour(provider_id: str, days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_provider_usage_breakdown_by_model_by_day_by_hour(provider_id, days)
    return {"provider_id": provider_id, "breakdown": breakdown}


@router.get("/provider/usage/breakdown/by-model/by-day/by-hour/all")
async def get_all_provider_usage_breakdown_by_model_by_day_by_hour(days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_all_provider_usage_breakdown_by_model_by_day_by_hour(days)
    return {"breakdown": breakdown}


@router.get("/provider/usage/breakdown/by-model/by-day/by-hour/by-minute")
async def get_provider_usage_breakdown_by_model_by_day_by_hour_by_minute(provider_id: str, days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_provider_usage_breakdown_by_model_by_day_by_hour_by_minute(provider_id, days)
    return {"provider_id": provider_id, "breakdown": breakdown}


@router.get("/provider/usage/breakdown/by-model/by-day/by-hour/by-minute/all")
async def get_all_provider_usage_breakdown_by_model_by_day_by_hour_by_minute(days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_all_provider_usage_breakdown_by_model_by_day_by_hour_by_minute(days)
    return {"breakdown": breakdown}


@router.get("/provider/usage/breakdown/by-model/by-day/by-hour/by-minute/by-second")
async def get_provider_usage_breakdown_by_model_by_day_by_hour_by_minute_by_second(provider_id: str, days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_provider_usage_breakdown_by_model_by_day_by_hour_by_minute_by_second(provider_id, days)
    return {"provider_id": provider_id, "breakdown": breakdown}


@router.get("/provider/usage/breakdown/by-model/by-day/by-hour/by-minute/by-second/all")
async def get_all_provider_usage_breakdown_by_model_by_day_by_hour_by_minute_by_second(days: int = 7):
    state = get_app_state()
    breakdown = await state["budget"].get_all_provider_usage_breakdown_by_model_by_day_by_hour_by_minute_by_second(days)
    return {"breakdown": breakdown}


@router.get("/provider/usage/breakdown/by-model/by-day/by-hour/by-minute/by-second/by-millisecond")
async def get_provider_usage_breakdown_by_model