from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
from sqlalchemy import text
from config import settings, create_db_and_tables, engine
from routes.api import router as api_router
from utils.logger import setup_logger

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application lifespan")
    
    # Enable pgvector extension before creating tables
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    logger.info("Enabled pgvector extension")
    
    # Create all tables (auto-sync models)
    create_db_and_tables()
    logger.info("Database tables synchronized")
    
    yield
    
    logger.info("Application shutdown complete")


app = FastAPI(title="TasteBud API", version="0.1.0", debug=settings.DEBUG, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    return {"app": "TasteBud", "status": "running"}

