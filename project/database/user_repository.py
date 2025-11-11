import logging
from typing import Optional

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from project.database.models import User

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def create_or_update_user(self, user_id: int, user_name: str) -> None:
        """Создает нового пользователя или обновляет существующего"""
        async with self.sessionmaker() as session:
            stmt = (
                insert(User)
                .values(
                    user_id=user_id,
                    user_name=user_name,
                )
                .on_conflict_do_update(
                    index_elements=[User.user_id],
                    set_={'user_name': user_name},
                )
            )
            await session.execute(stmt)
            await session.commit()
            logger.info(f"User {user_id} ({user_name}) created/updated")

    async def get_user(self, user_id: int) -> Optional[User]:
        """Получает пользователя по ID"""
        async with self.sessionmaker() as session:
            return await session.get(User, user_id)
