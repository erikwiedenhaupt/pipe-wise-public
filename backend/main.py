# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware



from api import (
    routes_meta,
    routes_projects,
    routes_network,
    routes_runs,
    routes_chat,
    routes_tools,
    routes_memory,
)

from core.storage import Storage
from core.tool_registry import ToolRegistry as CoreToolRegistry
from core.agent_orchestrator import AgentOrchestrator
from core.models import ToolSpec as CoreToolSpec  # core registry spec
from core.ws_manager import DebugWSManager

from dotenv import load_dotenv
load_dotenv() 


def _register_builtin_core_tools(registry: CoreToolRegistry) -> None:
    builtins = [
        CoreToolSpec(id="builtin:pandapipes_runner", name="pandapipes_runner", description="Execute pandapipes networks", version="0.0.1"),
        CoreToolSpec(id="builtin:kpi_calculator", name="kpi_calculator", description="Compute per-node/edge KPIs", version="0.0.1"),
        CoreToolSpec(id="builtin:issue_detector", name="issue_detector", description="Rule-based issue detection", version="0.0.1"),
        CoreToolSpec(id="builtin:suggestor", name="suggestor", description="Generate fix suggestions", version="0.0.1"),
        CoreToolSpec(id="builtin:network_mutations", name="network_mutations", description="Apply network parameter changes", version="0.0.1"),
        CoreToolSpec(id="builtin:scenario_engine", name="scenario_engine", description="Sweep/DOE over parameters", version="0.0.1"),
    ]
    for spec in builtins:
        if not registry.get(spec.id):
            registry.register(spec, persist=True)


def _import_agents_for_registration() -> None:
    # Import agent modules so they self-register into supervisor.REGISTRY
    from agents import supervisor as _sup  # noqa: F401
    from agents import simulate_agent as _sim  # noqa: F401
    from agents import kpi_agent as _kpi  # noqa: F401
    from agents import diagnostics_agent as _diag  # noqa: F401
    from agents import optimize_agent as _opt  # noqa: F401
    from agents import toolsmith_agent as _ts  # noqa: F401


def create_app() -> FastAPI:
    app = FastAPI(title="Pandapipes Analyst Agent", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Core singletons
    app.state.storage = Storage()
    app.state.tools = CoreToolRegistry(storage=app.state.storage)
    app.state.orchestrator = AgentOrchestrator(storage=app.state.storage, tool_registry=app.state.tools)
    from core.memory import MemoryStore 
    app.state.memory = MemoryStore(db_path=app.state.storage.db_path)

    @app.on_event("startup")
    async def _startup_debug_ws():
        # live debug WS manager
        app.state.debug_ws = DebugWSManager()

    _register_builtin_core_tools(app.state.tools)
    _import_agents_for_registration()

    # IMPORTANT: ensure this import exists so the module loads
    from api import (
        routes_meta,
        routes_projects,
        routes_network,
        routes_runs,
        routes_chat,   # ← make sure this is included
        routes_tools,
    )

    # Mount routers (chat must be included)
    app.include_router(routes_meta.router, prefix="/api")
    app.include_router(routes_projects.router, prefix="/api")
    app.include_router(routes_network.router, prefix="/api")
    app.include_router(routes_runs.router, prefix="/api")
    app.include_router(routes_chat.router, prefix="/api")  # ← ensures POST /api/chat
    app.include_router(routes_tools.router, prefix="/api")
    app.include_router(routes_memory.router, prefix="/api")

    # Log all routes once to confirm /api/chat is present
    try:
        import logging
        logging.getLogger("uvicorn").info("Mounted routes: %s", [r.path for r in app.routes])
    except Exception:
        pass

    return app


app = create_app()
