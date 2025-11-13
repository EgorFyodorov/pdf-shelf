import logging

from aiogram import Bot, Dispatcher

from project.database.engine import init_engine, verify_connection
from project.handlers.main_handlers import router
from project.parser.parser import Parser
from project.schemas.config_schemas import Config

logger = logging.getLogger(__name__)


async def main(config: Config):
    engine, sessionmaker = init_engine(config.postgres)
    await verify_connection(engine)
    
    bot = Bot(token=config.bot.bot_token)
    
    # Инициализируем парсер один раз
    parser = Parser.from_config(config.parser)
    await parser.initialize()
    logger.info("Parser initialized successfully")
    
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dispatcher.start_polling(bot, sessionmaker=sessionmaker, config=config, parser=parser)
    finally:
        # Закрываем парсер при завершении
        await parser.close()
        logger.info("Parser closed")
