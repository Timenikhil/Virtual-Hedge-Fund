from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from fastapi.middleware.cors import CORSMiddleware
from vhf.api.v1 import v1

app = FastAPI(title="Virtual Hedge Fund API",
              description="API for communication with Trading Community App.",
              version="1.0.0")
app.include_router(v1.router,
                   prefix="/api/v1",
                     tags=["v1"])

origins = ["http://localhost"]

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