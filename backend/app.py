"""Application factory and FastAPI wiring."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .common import router as common_router
from .device import router as device_router
from .logging_config import configure_logging
from .middleware import install_middleware
from .api_errors import register_exception_handlers
from .services import get_test_service
from .tests_routes import router as tests_router
from .tunnel_routes import router as tunnel_router
from .services.utils_routes import router as utils_router
from backend.services.results_routes import router as results_router
from backend.routes.traps import router as trap_router
from backend.routes.client_info import router as client_router

def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title="OSM-K Tester API", version="5.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_middleware(app)
    register_exception_handlers(app)

    app.include_router(common_router)
    app.include_router(device_router)
    app.include_router(tests_router)
    app.include_router(tunnel_router)
    app.include_router(utils_router)
    app.include_router(results_router)
    app.include_router(trap_router)
    app.include_router(client_router)

    @app.on_event("startup")
    async def _startup() -> None:
        get_test_service()

    return app


app = create_app()

__all__ = ["app", "create_app"]
