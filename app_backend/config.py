import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)

def _load_dotenv_fallback(dotenv_path: Path) -> None:
    try:
        with dotenv_path.open("r", encoding="utf-8") as fp:
            for raw_line in fp:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as exc:
        logger.warning("Failed to parse .env file %s: %s", dotenv_path, exc)


root_env = Path(__file__).resolve().parents[1] / ".env"
if root_env.exists():
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning("python-dotenv not installed; using manual .env parser")
        _load_dotenv_fallback(root_env)
    else:
        load_dotenv(dotenv_path=root_env)
        logger.info("Loaded .env from %s", root_env)

OPENAI_API_KEY: str | None = _env("OPENAI_API_KEY")
OPENAI_EMBEDDING_MODEL: str = _env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")  # type: ignore
OPENAI_CHAT_MODEL: str = _env("OPENAI_CHAT_MODEL", "gpt-4o-mini")  # type: ignore

if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY is not set.")

OPENAI_MAX_CONTEXT_CHARS: int = int(_env("OPENAI_MAX_CONTEXT_CHARS", "12000") or "12000")
OPENAI_MAX_OUTPUT_TOKENS: int = int(_env("OPENAI_MAX_OUTPUT_TOKENS", "1500") or "1500")

UPLOAD_DIR = Path(_env("UPLOAD_DIR", "/tmp/stat_app_uploads") or "/tmp/stat_app_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
