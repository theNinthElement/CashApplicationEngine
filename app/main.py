from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings, Settings
from app.db.session import get_db

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Automated cash application engine for matching payments to invoices",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint with database connectivity test."""
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "components": {
            "api": "healthy",
            "database": db_status,
        },
        "version": settings.app_version,
    }


@app.get("/config")
async def get_config(settings: Settings = Depends(get_settings)):
    """Get application configuration (non-sensitive values)."""
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "app_env": settings.app_env,
        "matching": {
            "auto_match_threshold": settings.auto_match_threshold,
            "manual_review_threshold": settings.manual_review_threshold,
            "weights": {
                "reference": settings.reference_match_weight,
                "amount": settings.amount_match_weight,
                "company": settings.company_match_weight,
                "date": settings.date_match_weight,
            },
        },
        "journal_defaults": {
            "company_code": settings.default_company_code,
            "document_type": settings.default_document_type,
            "gl_account": settings.default_gl_account,
            "currency": settings.default_currency,
        },
    }
