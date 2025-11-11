import os
from pathlib import Path
from typing import Any

import yaml

from project.schemas.config_schemas import (
    AppSection,
    BotSection,
    Config,
    LoggerSection,
    PostgresSection,
)


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text())
    data = _apply_env_overrides(raw)
    return Config(
        app=AppSection(**data['app']),
        bot=BotSection(**data['bot']),
        logger=LoggerSection(**data['logger']),
        postgres=PostgresSection(**data['postgres']),
    )


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    bot_token = os.getenv('BOT_TOKEN')
    if bot_token:
        data.setdefault('bot', {})['bot_token'] = bot_token

    logger_level = os.getenv('LOG_LEVEL')
    if logger_level:
        data.setdefault('logger', {})['level'] = logger_level

    pg = data.setdefault('postgres', {})
    mapping = {
        'user': 'POSTGRES_USER',
        'database': 'POSTGRES_DB',
        'host': 'POSTGRES_HOST',
        'port': 'POSTGRES_PORT',
    }
    for key, env_key in mapping.items():
        value = os.getenv(env_key)
        if value is None:
            continue
        pg[key] = int(value) if key == 'port' else value

    return data
