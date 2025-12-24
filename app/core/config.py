import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(override=True)
_app_env = os.getenv("APP_ENV", "development")
_is_production = _app_env.strip().lower() == "production"
_data_base_default = os.getenv("DATA_BASE_PATH") or ("/data" if _is_production else "./data")


def _resolve_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        if (parent / "app").exists() and (parent / "data").exists():
            return parent
    return Path.cwd()


_repo_root = _resolve_repo_root()

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
    app_env: str = _app_env
    port: int = _get_int("PORT", 8000)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
    data_base_path: str = _data_base_default
    vector_index_path: str = os.getenv("VECTOR_INDEX_PATH") or os.path.join(_data_base_default, "indexes/faiss/index.faiss")
    corpus_raw_path: str = os.getenv("CORPUS_RAW_PATH") or os.path.join(_data_base_default, "corpus/raw")
    corpus_version: str = os.getenv("CORPUS_VERSION", "dev")
    top_k: int = _get_int("TOP_K", 5)
    top_sources: int = _get_int("TOP_SOURCES", 3)

    # Limits
    q_limit_day: int = _get_int("QUESTION_LIMIT_PER_DAY", 10)
    q_limit_session: int = _get_int("QUESTION_LIMIT_PER_SESSION", 10)
    char_limit: int = _get_int("CHARACTER_LIMIT_PER_QUESTION", 500)

    # Logging DB
    log_db_path: str = os.getenv("LOG_DB_PATH") or os.path.join(_data_base_default, "logs/events.db")
    seed_urls_dir: str = os.getenv("SEED_URLS_DIR") or str(_repo_root / "data" / "corpus" / "seed_urls")

    # Governance flags (not used yet in skeleton, but loaded)
    strict_grounding: bool = _get_bool("STRICT_GROUNDING", True)
    citations_required: bool = _get_bool("CITATIONS_REQUIRED", True)
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_temperature: float = _get_float("LLM_TEMPERATURE", 0.2)
    llm_max_output_tokens: int = _get_int("LLM_MAX_OUTPUT_TOKENS", 700)

    # Hashing
    hash_salt: str = os.getenv("HASH_SALT", "local-dev-salt")

    # Admin / rate limiting
    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    admin_token_enabled: bool = _get_bool(
        "ADMIN_TOKEN_ENABLED",
        True if _is_production else bool(os.getenv("ADMIN_TOKEN"))
    )
    ip_rate_limit_enabled: bool = _get_bool("IP_RATE_LIMIT_ENABLED", _is_production)
    ip_rate_limit_window_seconds: int = _get_int("IP_RATE_LIMIT_WINDOW_SECONDS", 60)
    ip_rate_limit_max_requests: int = _get_int("IP_RATE_LIMIT_MAX_REQUESTS", 30)


settings = Settings()
