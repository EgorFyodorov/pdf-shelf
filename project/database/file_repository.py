import logging
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from project.database.models import File

logger = logging.getLogger(__name__)


class FileRepository:
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def create_file(
        self,
        file_id_int: int,
        user_id: int,
        complexity: int,
        size: int,
        labels: Optional[List[str]] = None,
    ) -> File:
        async with self.sessionmaker() as session:
            file = File(
                file_id_int=file_id_int,
                user_id=user_id,
                complexity=complexity,
                size=size,
                labels=labels or [],
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
            result = await session.execute(select(File).where(File.user_id == user_id))
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
