import logging
import time
import uuid

from fastapi import FastAPI, Request

from app.api import account, auth, constraints, goals, health, life_model, onboarding, roadblocks
from app.core.config import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger("app.request")


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_for_runtime()
    setup_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version="0.1.0")

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = request.headers.get("x-request-id", uuid.uuid4().hex)
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["x-request-id"] = request_id
        logger.info(
            "%s %s -> %s (%.1f ms) rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response

    app.include_router(health.router)
    app.include_router(account.router)
    app.include_router(onboarding.router)
    app.include_router(roadblocks.router)
    app.include_router(roadblocks.router)
    app.include_router(life_model.router)
    app.include_router(onboarding.router)
    app.include_router(roadblocks.router)
    app.include_router(roadblocks.router)
    app.include_router(life_model.router)
    app.include_router(auth.router)
    app.include_router(goals.router)
    app.include_router(constraints.router)
    return app


app = create_app()
