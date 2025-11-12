import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from project.database.models import User

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def create_or_update_user(self, user_id: int, user_name: str) -> User:
        async with self.sessionmaker() as session:
            stmt = (
                insert(User)
                .values(user_id=user_id, user_name=user_name)
                .on_conflict_do_update(
                    index_elements=[User.user_id],
                    set_={"user_name": user_name},
                )
                .returning(User)
            )
            result = await session.execute(stmt)
            user = result.scalar_one()
            await session.commit()
            logger.info(f"User {user_id} ({user_name}) created/updated")
            return user

    async def get_user(self, user_id: int) -> Optional[User]:
        async with self.sessionmaker() as session:
            return await session.get(User, user_id)

    async def get_user_with_files(self, user_id: int) -> Optional[User]:
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(User)
                .options(selectinload(User.files), selectinload(User.requests))
                .where(User.user_id == user_id)
            )
            return result.scalar_one_or_none()

    async def get_all_users(self) -> List[User]:
        async with self.sessionmaker() as session:
            result = await session.execute(select(User))
            return list(result.scalars().all())
