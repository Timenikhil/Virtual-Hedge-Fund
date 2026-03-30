import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from fastapi.middleware.cors import CORSMiddleware
from vhf.api.v1 import v1
from vhf.db import connection
from vhf.db.initialise import initialiseDB
from vhf.logging.log import logger
from vhf.services.reconcile_scheduler import SCHEDULER_ENABLED, scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure DB schema exists and lifecycle-manage the reconcile scheduler."""
    try:
        initialiseDB()
    except Exception:
        logger.exception("Database initialisation failed")
        raise

    # Verify DB is actually reachable before accepting traffic.
    try:
        connection.verify_connectivity()
    except Exception:
        logger.exception("Database connectivity check failed at startup")
        raise

    if SCHEDULER_ENABLED:
        await scheduler.start()
    try:
        yield
    finally:
        if SCHEDULER_ENABLED:
            await scheduler.stop()


app = FastAPI(title="Virtual Hedge Fund API",
              description="API for communication with Trading Community App.",
              version="1.0.0",
              lifespan=lifespan)
app.include_router(v1.router,
                   prefix="/api/v1",
                   tags=["v1"])

# Read allowed origins from env; fall back to localhost for local dev.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health_check():
    """Liveness + DB connectivity probe."""
    try:
        connection.verify_connectivity()
    except Exception as exc:
        logger.error("Health check DB probe failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "unhealthy", "detail": str(exc)})
    return {"status": "ok"}


# Prometheus monitoring
Instrumentator().instrument(app).expose(app)
# Tempo
FastAPIInstrumentor.instrument_app(app)
