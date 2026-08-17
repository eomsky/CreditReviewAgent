"""Environment-backed application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Credit Review Assistant"
    APP_ENV: str = "development"

    COLAB_LLM_BASE_URL: str = "http://localhost:8001/v1"
    COLAB_LLM_MODEL: str = "credit-review-qwen-vl-32b"
    COLAB_LLM_API_KEY: str = "change-me"
    COLAB_LLM_TIMEOUT_SECONDS: int = 300
    COLAB_LLM_MAX_RETRIES: int = 2
    COLAB_LLM_RETRY_BACKOFF_SECONDS: float = 0.5
    MAX_UPLOAD_SIZE_MB: int = 25
    # vLLM max-model-len=8192 안에서 DB/RAG/첨부 근거와 출력을 함께 수용한다.
    MAX_DOCUMENT_TEXT_CHARS: int = 4_000
    MAX_IMAGES_PER_MESSAGE: int = 2

    DATABASE_URL: str = "sqlite+aiosqlite:///./data/database/credit_review.db"
    CHROMA_PERSIST_DIR: Path = PROJECT_ROOT / "data" / "vector_db" / "chroma"
    UPLOAD_DIR: Path = PROJECT_ROOT / "data" / "uploads"
    PROCESSED_DIR: Path = PROJECT_ROOT / "data" / "processed"
    BACKUP_DIR: Path = PROJECT_ROOT / "data" / "backups"

    CHROMA_COLLECTION: str = "credit_documents"
    POC_AUTO_SEED: bool = True
    SQL_MAX_ROWS: int = 10
    SQL_QUERY_TIMEOUT_SECONDS: float = 3.0
    MAX_REVISION_COUNT: int = 2
    MAX_RETRIEVAL_COUNT: int = 2
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    RAG_TOP_K: int = 5

    def ensure_directories(self) -> None:
        for path in (
            self.CHROMA_PERSIST_DIR,
            self.UPLOAD_DIR,
            self.PROCESSED_DIR,
            self.BACKUP_DIR,
            PROJECT_ROOT / "data" / "database",
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    configured = Settings()
    configured.ensure_directories()
    return configured


settings = get_settings()
