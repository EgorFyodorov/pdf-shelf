import logging
import uuid
from typing import List, Optional

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from project.database.models import File, Request

logger = logging.getLogger(__name__)


class RequestRepository:
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def create_request(self, user_id: int, file_id: uuid.UUID) -> Request:
        async with self.sessionmaker() as session:
            request = Request(user_id=user_id, file_id=file_id)
            session.add(request)
            await session.commit()
            await session.refresh(request)
            logger.info(f"Request created: {request.id} for user {user_id}")
            return request

    async def get_request(self, request_id: uuid.UUID) -> Optional[Request]:
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(Request)
                .options(selectinload(Request.user), selectinload(Request.file))
                .where(Request.id == request_id)
            )
            return result.scalar_one_or_none()

    async def get_requests_by_user(self, user_id: int) -> List[Request]:
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(Request)
                .options(selectinload(Request.file))
                .where(Request.user_id == user_id)
            )
            return list(result.scalars().all())

    async def get_requests_by_file(self, file_id: uuid.UUID) -> List[Request]:
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(Request)
                .options(selectinload(Request.user))
                .where(Request.file_id == file_id)
            )
            return list(result.scalars().all())

    async def create_batch_requests(
        self, user_id: int, file_ids: List[uuid.UUID]
    ) -> List[Request]:
        async with self.sessionmaker() as session:
            requests = [
                Request(user_id=user_id, file_id=file_id) for file_id in file_ids
            ]
            session.add_all(requests)
            await session.commit()
            for req in requests:
                await session.refresh(req)
            logger.info(f"Created {len(requests)} requests for user {user_id}")
            return requests

    async def delete_request(self, request_id: uuid.UUID) -> bool:
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(Request).where(Request.id == request_id)
            )
            request = result.scalar_one_or_none()
            if request:
                await session.delete(request)
                await session.commit()
                logger.info(f"Request deleted: {request_id}")
                return True
            return False

    async def get_recent_requested_files(self, user_id: int, limit: int = 5) -> List[File]:
        """Получает последние уникальные файлы, запрошенные пользователем."""
        async with self.sessionmaker() as session:
            # Подзапрос для получения последнего request_id для каждого file_id
            subquery = (
                select(
                    Request.file_id,
                    func.max(Request.created_at).label("last_request_time")
                )
                .where(Request.user_id == user_id)
                .group_by(Request.file_id)
                .subquery()
            )
            
            # Основной запрос для получения файлов
            result = await session.execute(
                select(File)
                .join(subquery, File.file_id == subquery.c.file_id)
                .order_by(subquery.c.last_request_time.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
