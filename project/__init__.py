import asyncio
import logging
import os
from pathlib import Path
from typing import Any, TYPE_CHECKING

# Lazy import of config to avoid hard dependency on PyYAML during simple tools/CLI usage
try:  # noqa: SIM105
    from project.config import load_config as _load_config  # type: ignore
except Exception:  # pragma: no cover - optional at import time
    _load_config = None  # type: ignore

if TYPE_CHECKING:  # for type checkers only
    from project.schemas.config_schemas import Config as _ConfigType  # noqa: F401

BASE_DIR = Path(__file__).parent.parent
ENV_PATH = BASE_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config.yaml"


def load_env_file(env_path: Path):
    """Load environment variables from .env file without external dependencies."""
    if not env_path.exists():
        return

    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Parse KEY=VALUE format
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    # Only set if not already in environment
                    if key and key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        logging.warning(f"Failed to load .env file: {e}")


if ENV_PATH.exists():
    load_env_file(ENV_PATH)

def init_logger(config: Any | None):
    """Initialize root logger.

    Works even if full Config is not available (e.g., when running CLI tools that
    don't require YAML). Falls back to reasonable defaults.
    """
    default_format = "%(levelname)s %(name)s: %(message)s"
    level_name = "INFO"
    app_name = "project"

    try:
        if config is not None and getattr(config, "logger", None):
            level_name = getattr(config.logger, "level", level_name)
            default_format = getattr(config.logger, "format", default_format)
        if config is not None and getattr(config, "app", None):
            app_name = getattr(config.app, "name", app_name) or app_name
    except Exception:  # pragma: no cover - be defensive
        pass

    logging.basicConfig(
        level=getattr(logging, str(level_name).upper(), logging.INFO),
        format=default_format,
    )
    return logging.getLogger(app_name)


if _load_config is not None and CONFIG_PATH.exists():
    try:
        CONFIG = _load_config(CONFIG_PATH)  # type: ignore[call-arg]
    except Exception as e:  # pragma: no cover - config may be optional for some tools
        logging.warning(f"Failed to load config.yaml: {e}")
        CONFIG = None  # type: ignore[assignment]
else:
    CONFIG = None  # type: ignore[assignment]

logger = init_logger(CONFIG)

loop = asyncio.get_event_loop()