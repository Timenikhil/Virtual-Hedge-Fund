import os
import secrets
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import Response

# Observability imports
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

security = HTTPBasic()

def verify_metrics_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Validates the basic auth credentials for the metrics endpoint."""
    prom_us = os.getenv("PROM_NAME", "cfl")
    prom_pass = os.getenv("PROM_PASS", "")

    # Use secrets.compare_digest to prevent timing attacks
    correct_username = secrets.compare_digest(credentials.username, prom_us)
    correct_password = secrets.compare_digest(credentials.password, prom_pass)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials

def setup_observability(app: FastAPI):
    """Initializes Prometheus and OpenTelemetry instrumentation.

    Grafana Observability
    """

    # Prometheus monitoring

    Instrumentator().instrument(app)

    # 2. Expose the custom /metrics endpoint with Basic Auth protection
    @app.get(
        "/metrics",
        include_in_schema=False,
        dependencies=[Depends(verify_metrics_credentials)]
    )
    def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    #  Tempo traces
    FastAPIInstrumentor.instrument_app(app)