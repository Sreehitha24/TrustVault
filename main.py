
from contextlib import asynccontextmanager
from routers.documents import router as documents_router
import os

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

from routers.auth import router as auth_router

load_dotenv()


def get_db_connection():
    """Create a PostgreSQL connection using environment settings."""
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "trustvault"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row,
        connect_timeout=5,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Check database availability when the application starts."""
    try:
        with get_db_connection() as connection:
            connection.execute("SELECT 1")
        app.state.database_ready = True
    except (psycopg.Error, ValueError):
        app.state.database_ready = False

    yield


app = FastAPI(
    title="TrustVault",
    description="Secure Document Sharing Platform",
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://127.0.0.1:5500",
    "http://localhost:5500",
],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Authentication endpoints: register and login.
app.include_router(auth_router)
app.include_router(documents_router)


@app.get("/")
def home():
    return {
        "app": "TrustVault",
        "message": "Secure document platform is running",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/database")
def database_health():
    """Check PostgreSQL connectivity without exposing credentials."""
    try:
        with get_db_connection() as connection:
            connection.execute("SELECT 1")
        return {"database": "connected"}
    except (psycopg.Error, ValueError):
        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable",
        )
