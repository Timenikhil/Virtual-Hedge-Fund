import os
from contextlib import asynccontextmanager

from fastapi import FastAPI,Request
from fastapi.middleware.cors import CORSMiddleware
from vhf.api.v1 import v1
from vhf.db.initialise import initialiseDB
from vhf.logging.log import logger
from vhf.logging.observability import setup_observability


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

origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000")

# Split the string into a list of actual origins
origins = [origin.strip() for origin in origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    # Force HTTPS in development and production (HSTS)
    if os.getenv("APP_ENVIRONMENT","LOCAL") != "LOCAL":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

    # csp_policy = """\
    #             default-src 'self'; \
    #             script-src 'self' https://*.firebaseio.com https://*.googleapis.com; \
    #             connect-src 'self' https://*.firebaseio.com https://*.googleapis.com; \
    #             style-src 'self' 'unsafe-inline'; \
    #             font-src 'self' data:;"""
    # response.headers["Content-Security-Policy"] = csp_policy

    # Add other useful headers
    response.headers["X-Frame-Options"] = "DENY" # Prevents clickjacking
    response.headers["X-Content-Type-Options"] = "nosniff" # Prevents MIME type sniffing

    return response

# uncomment this after setting appropriate environment variables
# setup_observability(app)
