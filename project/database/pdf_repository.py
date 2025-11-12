import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)


class PDFRepository:
    """Заглушка репозитория для логирования PDF событий.

    В текущей версии не пишет в БД, только журналирует факты получения
    файла/URL. Оставлено для совместимости с хэндлерами.
    """

    def __init__(self, sessionmaker: async_sessionmaker):  # noqa: ARG002
        self.sessionmaker = sessionmaker

    async def log_pdf_upload(
        self, user_id: int, filename: str, file_id: str, file_size: int
    ) -> None:
        logger.info(
            "PDF upload: user_id=%s filename=%s file_id=%s size=%s",
            user_id,
            filename,
            file_id,
            file_size,
        )

    async def log_pdf_url(self, user_id: int, url: str) -> None:
        logger.info("PDF url submitted: user_id=%s url=%s", user_id, url)
