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


# ── Provider balance management ───────────────────────────────────────────

@router.get("/providers")
async def get_providers():
    """Get per-provider balance and spending info."""
    state = get_app_state()
    budget_status = await state["budget"].get_status()
    return {"providers": budget_status.get("providers", [])}


@router.put("/providers/{provider}")
async def update_provider(provider: str, body: ProviderBalanceUpdate):
    """Update a provider's known balance, tier, or notes."""
    state = get_app_state()
    result = await state["budget"].update_provider_balance(
        provider=provider,
        known_balance=body.known_balance,
        tier=body.tier,
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
        notes=body.notes,
    )
    return {"ok": True, **result}


# ── Chat endpoint ──────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    """Chat directly with JARVIS. Messages are recorded in blob and DB."""
    state = get_app_state()
    blob = state["blob"]
    llm_router = state["router"]
    budget = state["budget"]
    state_mgr = state["state_manager"]

    # Record creator message in blob
    blob.store(
        event_type="chat_creator",
        content=body.message,
        metadata={"role": "creator"},
    )

    # Store in DB
    from jarvis.models import ChatMessage
    async with state["session_factory"]() as session:
        msg = ChatMessage(role="creator", content=body.message)
        session.add(msg)
        await session.commit()

    # Build context: recent chat history + system prompt
    chat_history = await _get_chat_history(state["session_factory"], limit=20)
    current_state = await state_mgr.get_state()
    budget_status = await budget.get_status()

    system_prompt = build_chat_system_prompt(
        directive=current_state["directive"],
        budget_status=budget_status,
    )

    messages = [{"role": "system", "content": system_prompt}]
    for entry in chat_history:
        role = "user" if entry["role"] == "creator" else "assistant"
        messages.append({"role": role, "content": entry["content"]})

    # Get JARVIS response
    response = await llm_router.complete(
        messages=messages,
        tier="level2",
        temperature=0.7,
        max_tokens=2048,
        task_description="chat_with_creator",
    )

    # Record JARVIS reply in blob
    blob.store(
        event_type="chat_jarvis",
        content=response.content,
        metadata={"role": "jarvis", "model": response.model, "provider": response.provider},
    )

    # Store in DB
    async with state["session_factory"]() as session:
        msg = ChatMessage(
            role="jarvis",
            content=response.content,
            metadata_={"model": response.model, "provider": response.provider},
        )
        session.add(msg)
        await session.commit()

    # Broadcast chat event via WebSocket
    await ws_manager.broadcast({
        "type": "chat_message",
        "role": "jarvis",
        "content": response.content[:200],
    })

    # Wake the core loop so JARVIS processes any implications quickly
    core_loop = state.get("core_loop")
    if core_loop:
        core_loop.wake()

    return ChatResponse(
        reply=response.content,
        model=response.model,
        provider=response.provider,
        tokens_used=response.total_tokens,
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


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
