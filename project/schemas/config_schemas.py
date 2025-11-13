from dataclasses import dataclass


@dataclass
class AppSection:
    name: str


@dataclass
class BotSection:
    bot_token: str


@dataclass
class LoggerSection:
    format: str
    level: str = "INFO"


@dataclass
class PostgresSection:
    user: str
    password: str
    database: str
    host: str
    port: int


@dataclass
class ParserSection:
    timeout: int = 120000
    wait_until: str = "networkidle"
    pdf_format: str = "A4"


@dataclass
class Config:
    app: AppSection
    bot: BotSection
    logger: LoggerSection
    postgres: PostgresSection
    parser: ParserSection
