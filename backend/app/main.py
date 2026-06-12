import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import connect_db, disconnect_db

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ChurnIQ API starting...")
    await connect_db()
    yield
    logger.info("ChurnIQ API shutting down...")
    await disconnect_db()


# ---------------------------------------------------------------------------
# Create FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    description="Multi-tenant SaaS churn prediction platform",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from app.routers.auth import router as auth_router
from app.routers.customers import router as customers_router
from app.routers.predictions import router as predictions_router
from app.routers.analytics import router as analytics_router
from app.routers.chat import router as chat_router

app.include_router(auth_router,        prefix="/api/v1/auth",        tags=["auth"])
app.include_router(customers_router,   prefix="/api/v1/customers",   tags=["customers"])
app.include_router(predictions_router, prefix="/api/v1/predictions", tags=["predictions"])
app.include_router(analytics_router,   prefix="/api/v1/analytics",   tags=["analytics"])
app.include_router(chat_router,        prefix="/api/v1/chat",        tags=["chat"])


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Return service liveness status."""
    return {"status": "ok", "app": settings.APP_NAME, "environment": settings.ENVIRONMENT}


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": f"Welcome to {settings.APP_NAME}", "docs": "http://localhost:8000/docs"}