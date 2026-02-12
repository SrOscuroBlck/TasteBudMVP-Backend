import os
from typing import Optional, List
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project folder explicitly (works even if CWD differs)
_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_BASE_DIR / ".env")


class Settings:
    # Database
    DATABASE_URL: str = os.getenv("TASTEBUD_DATABASE_URL", "sqlite:///./tastebud.db")

    # OpenAI (bounded usage)
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8010"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

    # CORS
    ALLOWED_ORIGINS: List[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")

    # Onboarding
    ONBOARDING_MAX_QUESTIONS: int = int(os.getenv("ONBOARDING_MAX_QUESTIONS", "7"))
    ONBOARDING_EARLY_STOP_CONFIDENCE: float = float(os.getenv("ONBOARDING_EARLY_STOP_CONFIDENCE", "0.8"))
    ONBOARDING_K: float = float(os.getenv("ONBOARDING_K", "0.1"))
    ONBOARDING_SIGMA_STEP: float = float(os.getenv("ONBOARDING_SIGMA_STEP", "0.12"))

    # Recommendation weights
    LAMBDA_CUISINE: float = float(os.getenv("LAMBDA_CUISINE", "0.2"))
    LAMBDA_POP: float = float(os.getenv("LAMBDA_POP", "0.2"))
    MMR_ALPHA: float = float(os.getenv("MMR_ALPHA", "0.7"))
    GPT_CONFIDENCE_DISCOUNT: float = float(os.getenv("GPT_CONFIDENCE_DISCOUNT", "0.3"))

    # Popularity
    DECAY_HALF_LIFE_DAYS: int = int(os.getenv("DECAY_HALF_LIFE_DAYS", "30"))

    # FAISS
    FAISS_INDEX_PATH: str = os.getenv("FAISS_INDEX_PATH", "data/faiss_indexes/")
    FAISS_DIMENSION: int = int(os.getenv("FAISS_DIMENSION", "1536"))

    # Frontend
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # JWT
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    # OTP
    OTP_EXPIRE_MINUTES: int = int(os.getenv("OTP_EXPIRE_MINUTES", "10"))
    OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "3"))


settings = Settings()
