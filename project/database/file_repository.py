import logging
import uuid
from typing import Any, List, Optional

from sqlalchemy import and_, not_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from project.database.models import File, Request

logger = logging.getLogger(__name__)


class FileRepository:
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def create_file(
        self,
        user_id: int,
        telegram_file_id: str,
        title: str,
        reading_time_min: float,
        analysis_json: dict[str, Any],
        source_url: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> File:
        async with self.sessionmaker() as session:
            file = File(
                user_id=user_id,
                telegram_file_id=telegram_file_id,
                source_url=source_url,
                title=title,
                reading_time_min=reading_time_min,
                tags=tags or [],
                analysis_json=analysis_json,
            )
            session.add(file)
            await session.commit()
            await session.refresh(file)
            logger.info(f"File created: {file.file_id} for user {user_id}")
            return file

    async def get_file(self, file_id: uuid.UUID) -> Optional[File]:
        async with self.sessionmaker() as session:
            result = await session.execute(select(File).where(File.file_id == file_id))
            return result.scalar_one_or_none()

    async def get_files_by_user(self, user_id: int) -> List[File]:
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(File)
                .where(File.user_id == user_id)
                .order_by(File.created_at.desc())
            )
            return list(result.scalars().all())

    async def get_files_by_user_filtered(
        self,
        user_id: int,
        tags: Optional[List[str]] = None,
        exclude_file_ids: Optional[List[uuid.UUID]] = None,
    ) -> List[File]:
        async with self.sessionmaker() as session:
            conditions = [File.user_id == user_id]

            if tags:
                # Используем оператор && (overlap) для PostgreSQL ARRAY
                conditions.append(File.tags.bool_op("&&")(tags))

            if exclude_file_ids:
                conditions.append(not_(File.file_id.in_(exclude_file_ids)))

            result = await session.execute(
                select(File).where(and_(*conditions)).order_by(File.created_at.desc())
            )
            return list(result.scalars().all())

    async def get_recently_sent_files(
        self, user_id: int, limit: int = 10
    ) -> List[uuid.UUID]:
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(Request.file_id)
                .where(Request.user_id == user_id)
                .order_by(Request.id.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def delete_file(self, file_id: uuid.UUID) -> bool:
        async with self.sessionmaker() as session:
            result = await session.execute(select(File).where(File.file_id == file_id))
            file = result.scalar_one_or_none()
            if file:
                await session.delete(file)
                await session.commit()
                logger.info(f"File deleted: {file_id}")
                return True
            return False
