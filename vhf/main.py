from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from fastapi.middleware.cors import CORSMiddleware
from vhf.api.v1 import v1
from vhf.db.initialise import initialiseDB
from vhf.logging.log import logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure the database schema exists before serving requests."""
    try:
        initialiseDB()
    except Exception:
        logger.exception("Database initialisation failed")
        raise
    yield


app = FastAPI(title="Virtual Hedge Fund API",
              description="API for communication with Trading Community App.",
              version="1.0.0",
              lifespan=lifespan)
app.include_router(v1.router,
                   prefix="/api/v1",
                     tags=["v1"])

origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus monitoring
Instrumentator().instrument(app).expose(app)
# Tempo
FastAPIInstrumentor.instrument_app(app)
