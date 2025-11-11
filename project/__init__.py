import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

from project.config import Config, load_config

BASE_DIR = Path(__file__).parent.parent
ENV_PATH = BASE_DIR / '.env'
CONFIG_PATH = BASE_DIR / 'config.yaml'

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def init_logger(config: Config):
    logging.basicConfig(
        level=getattr(logging, config.logger.level.upper(), logging.INFO),
        format=config.logger.format,
    )
    return logging.getLogger(config.app.name)


CONFIG = load_config(CONFIG_PATH)
logger = init_logger(CONFIG)

loop = asyncio.get_event_loop()
