import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.cache import cache_manager
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.database_init import init_database_schema
from app.routers import get_api_router
from app.services.bootstrap import ensure_default_admin


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    logger = logging.getLogger("app.validation")

    app = FastAPI(title=settings.PROJECT_NAME)

    # Add CORS middleware (always enabled)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        body_bytes = await request.body()
        body_text = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
        logger.error(
            "Validation error on %s %s body=%s detail=%s",
            request.method,
            request.url.path,
            body_text,
            exc.errors(),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors(), "body": exc.body},
        )

    api_router = get_api_router()
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.on_event("startup")
    def startup_event():
        init_database_schema(settings.DATABASE_URL)
        cache_manager.init_backend()
        ensure_default_admin()

    return app


app = create_app()
