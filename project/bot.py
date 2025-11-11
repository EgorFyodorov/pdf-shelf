import logging

from aiogram import Bot, Dispatcher

from project.database.engine import init_engine, verify_connection
from project.handlers.main_handlers import router
from project.schemas.config_schemas import Config

logger = logging.getLogger(__name__)


async def main(config: Config):
    engine, sessionmaker = init_engine(config.postgres)
    await verify_connection(engine)
    bot = Bot(token=config.bot.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot, sessionmaker=sessionmaker)
