import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv(override=True)

def _get_bool(name: str, default: bool) -> bool:
    v = os.getenv(name, str(default)).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _get_int(name: str, default: int) -> int:
    v = os.getenv(name)
    return int(v) if v and v.strip().isdigit() else default


def _get_float(name: str, default: float) -> float:
    v = os.getenv(name)
    try:
        return float(v) if v is not None else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    port: int = _get_int("PORT", 8000)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
    vector_index_path: str = os.getenv("VECTOR_INDEX_PATH", "./data/indexes/faiss/index.faiss")
    corpus_raw_path: str = os.getenv("CORPUS_RAW_PATH", "./data/corpus/raw")
    corpus_version: str = os.getenv("CORPUS_VERSION", "dev")
    top_k: int = _get_int("TOP_K", 5)
    top_sources: int = _get_int("TOP_SOURCES", 3)

    # Limits
    q_limit_day: int = _get_int("QUESTION_LIMIT_PER_DAY", 10)
    q_limit_session: int = _get_int("QUESTION_LIMIT_PER_SESSION", 10)
    char_limit: int = _get_int("CHARACTER_LIMIT_PER_QUESTION", 500)

    # Logging DB
    log_db_path: str = os.getenv("LOG_DB_PATH", "./data/logs/events.db")

    # Governance flags (not used yet in skeleton, but loaded)
    strict_grounding: bool = _get_bool("STRICT_GROUNDING", True)
    citations_required: bool = _get_bool("CITATIONS_REQUIRED", True)
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_temperature: float = _get_float("LLM_TEMPERATURE", 0.2)
    llm_max_output_tokens: int = _get_int("LLM_MAX_OUTPUT_TOKENS", 700)

    # Hashing
    hash_salt: str = os.getenv("HASH_SALT", "local-dev-salt")


settings = Settings()
