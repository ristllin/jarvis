import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from jarvis.config import settings
from jarvis.database import engine, async_session, Base
from jarvis.observability.logger import setup_logging, get_logger, FileLogger
from jarvis.memory.blob import BlobStorage
from jarvis.memory.vector import VectorMemory
from jarvis.memory.working import WorkingMemory
from jarvis.budget.tracker import BudgetTracker
from jarvis.safety.validator import SafetyValidator
from jarvis.tools.registry import ToolRegistry
from jarvis.llm.router import LLMRouter
from jarvis.core.state import StateManager
from jarvis.core.planner import Planner
from jarvis.core.executor import Executor
from jarvis.core.loop import CoreLoop
from jarvis.core.email_listener import EmailInboxListener
from jarvis.core.watchdog import Watchdog
from jarvis.api.routes import router as api_router
from jarvis.api.websocket import ws_manager

setup_logging()
log = get_logger("main")

# Shared application state — accessed by API routes
app_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("jarvis_starting")

    data_dir = settings.data_dir
    os.makedirs(data_dir, exist_ok=True)

    # 1. Create database tables + migrate new columns
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add new columns to existing tables (safe to run repeatedly)
        for col, coldef in [
            ("short_term_goals", "TEXT DEFAULT '[]'"),
            ("mid_term_goals", "TEXT DEFAULT '[]'"),
            ("long_term_goals", "TEXT DEFAULT '[]'"),
            ("short_term_memories", "TEXT DEFAULT '[]'"),
        ]:
            try:
                await conn.execute(
                    __import__("sqlalchemy").text(f"ALTER TABLE jarvis_state ADD COLUMN {col} {coldef}")
                )
                log.info("column_added", table="jarvis_state", column=col)
            except Exception:
                pass  # Column already exists
        # Add currency column to provider_balances (safe to run repeatedly)
        try:
            await conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE provider_balances ADD COLUMN currency VARCHAR(20) DEFAULT 'USD'"
                )
            )
            log.info("column_added", table="provider_balances", column="currency")
        except Exception:
            pass  # Column already exists
    log.info("database_initialized")

    # 2. Initialize subsystems
    blob = BlobStorage(data_dir)
    file_logger = FileLogger(data_dir)

    vector = VectorMemory(data_dir)
    try:
        vector.connect()
        log.info("chromadb_connected")
    except Exception as e:
        log.warning("chromadb_connect_failed", error=str(e))

    working = WorkingMemory()
    budget = BudgetTracker(async_session)
    await budget.ensure_config()

    validator = SafetyValidator()
    router = LLMRouter(budget, blob_storage=blob)
    tools = ToolRegistry(vector, validator, budget_tracker=budget, llm_router=router, blob_storage=blob)
    log.info("tools_available", tools=sorted(tools.get_tool_names()))
    state_manager = StateManager(async_session)
    planner = Planner(router, working, vector)
    executor = Executor(tools, blob, file_logger, session_factory=async_session)

    # 3. Configure git inside container
    await _configure_git()

    # 4. Store in shared state for API access
    app_state.update({
        "blob": blob,
        "vector": vector,
        "working": working,
        "budget": budget,
        "tools": tools,
        "router": router,
        "state_manager": state_manager,
        "planner": planner,
        "executor": executor,
        "file_logger": file_logger,
        "session_factory": async_session,
    })

    # 5. Try to pull a small Ollama model in the background
    ollama_provider = router.providers.get("ollama")
    if ollama_provider:
        asyncio.create_task(_pull_ollama_model(ollama_provider))

    # 6. Start core loop
    core_loop = CoreLoop(
        state_manager=state_manager,
        planner=planner,
        executor=executor,
        budget=budget,
        blob=blob,
        vector=vector,
        file_logger=file_logger,
        broadcast_fn=ws_manager.broadcast,
    )
    loop_task = asyncio.create_task(core_loop.run())
    app_state["core_loop"] = core_loop
    app_state["loop_task"] = loop_task

    # 6b. Start email inbox listener (disabled by default — enable via EMAIL_LISTENER_ENABLED=true)
    email_listener = EmailInboxListener(
        enqueue_fn=core_loop.enqueue_chat,
        interval_seconds=settings.email_listener_interval_seconds,
    )
    email_listener.start()
    app_state["email_listener"] = email_listener

    # 7. Start watchdog
    watchdog = Watchdog(state_manager, settings.heartbeat_timeout_seconds)
    watchdog.set_loop_task(loop_task, lambda: _restart_loop(core_loop))
    watchdog_task = asyncio.create_task(watchdog.run())

    blob.store("system", "JARVIS started successfully — all systems online")
    log.info("jarvis_ready", providers=router.get_available_providers())

    yield

    # Shutdown
    log.info("jarvis_shutting_down")
    core_loop.stop()
    loop_task.cancel()
    watchdog_task.cancel()

    # Stop email listener
    try:
        email_listener = app_state.get("email_listener")
        if email_listener:
            await email_listener.stop()
    except Exception as e:
        log.warning("email_listener_stop_failed", error=str(e))

    await engine.dispose()


async def _configure_git():
    """Configure git identity inside the container."""
    try:
        for cmd in [
            ["git", "config", "--global", "user.name", settings.git_user_name],
            ["git", "config", "--global", "user.email", settings.git_user_email],
        ]:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        log.info("git_configured", name=settings.git_user_name, email=settings.git_user_email)
    except Exception as e:
        log.warning("git_config_failed", error=str(e))


async def _pull_ollama_model(ollama_provider):
    try:
        await ollama_provider.ensure_model("mistral:7b-instruct")
    except Exception as e:
        log.warning("ollama_model_pull_skipped", error=str(e))


def _restart_loop(core_loop: CoreLoop):
    log.info("restarting_core_loop")
    asyncio.create_task(core_loop.run())


app = FastAPI(title="JARVIS", version="0.1.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*']);

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
from jarvis.tools.authentication import get_current_user;


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            log.info("ws_message", data=data[:200])
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
