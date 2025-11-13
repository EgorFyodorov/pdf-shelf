import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import async_sessionmaker

from project.database.file_repository import FileRepository
from project.database.models import File

logger = logging.getLogger(__name__)


class MaterialSelector:
    """Сервис для подбора материалов по времени и тегам."""

    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker
        self.file_repo = FileRepository(sessionmaker)

    async def select_materials(
        self,
        user_id: int,
        time_minutes: float,
        tags: Optional[List[str]] = None,
    ) -> tuple[List[File], float]:
        """
        Подбирает материалы для пользователя по времени и тегам.

        Args:
            user_id: ID пользователя
            time_minutes: доступное время в минутах
            tags: список тегов для фильтрации (None = без фильтрации)

        Returns:
            tuple[List[File], float]: (список файлов, общее время чтения)
        """
        # Получаем файлы пользователя с фильтрацией по тегам
        if tags:
            files = await self.file_repo.get_files_by_user_filtered(
                user_id=user_id,
                tags=tags,
                exclude_file_ids=None,
            )
        else:
            files = await self.file_repo.get_files_by_user(user_id)

        logger.info(
            f"User {user_id}: available files count={len(files)}, time_limit={time_minutes}, tags={tags}"
        )

        if not files:
            logger.info(f"No files found for user {user_id} with tags={tags}")
            return [], 0.0

        # Применяем жадный алгоритм для подбора материалов
        selected = self._greedy_selection(files, time_minutes)

        total_time = sum(float(f.reading_time_min) for f in selected)

        logger.info(
            f"Selected {len(selected)} files for user {user_id}, "
            f"total time: {total_time:.1f} min, requested: {time_minutes:.1f} min"
        )

        return selected, total_time

    def _greedy_selection(self, files: List[File], time_limit: float) -> List[File]:
        """
        Жадный алгоритм подбора файлов по времени.

        Стратегия: сортируем файлы по времени чтения (от меньшего к большему)
        и добавляем пока умещаемся в лимит времени.

        Args:
            files: список файлов
            time_limit: лимит времени в минутах

        Returns:
            List[File]: список выбранных файлов
        """
        # Сортируем по времени чтения (от меньшего к большему)
        sorted_files = sorted(files, key=lambda f: float(f.reading_time_min))

        logger.info(
            f"Greedy selection: time_limit={time_limit}, files count={len(sorted_files)}"
        )
        for f in sorted_files:
            logger.info(f"  File: {f.title} - {float(f.reading_time_min):.1f} min")

        selected = []
        total_time = 0.0

        for file in sorted_files:
            file_time = float(file.reading_time_min)

            # Добавляем файл если он умещается в лимит
            if total_time + file_time <= time_limit:
                selected.append(file)
                total_time += file_time
                logger.info(
                    f"  ✓ Selected: {file.title} ({file_time:.1f} min), total: {total_time:.1f}"
                )
            else:
                logger.info(f"  ✗ Skipped: {file.title} ({file_time:.1f} min) - would exceed limit")
        
        # Если ничего не выбрано, берем первый файл даже если он немного больше
        # (в пределах 50% от лимита)
        if not selected and sorted_files:
            first_file = sorted_files[0]
            first_file_time = float(first_file.reading_time_min)
            if first_file_time <= time_limit * 1.5:
                selected.append(first_file)
                logger.info(
                    f"  ✓ Selected (fallback): {first_file.title} ({first_file_time:.1f} min), exceeds limit by {first_file_time - time_limit:.1f} min"
                )

        return selected

    def _knapsack_selection(self, files: List[File], time_limit: float) -> List[File]:
        """
        Алгоритм динамического программирования (0/1 knapsack) для подбора файлов.

        Более оптимальный, но медленнее жадного. Используется для небольших наборов.

        Args:
            files: список файлов
            time_limit: лимит времени в минутах

        Returns:
            List[File]: список выбранных файлов
        """
        n = len(files)
        if n == 0:
            return []

        # Переводим время в целые числа (в десятых долях минуты)
        W = int(time_limit * 10)
        weights = [int(f.reading_time_min * 10) for f in files]

        # DP таблица
        dp = [[0 for _ in range(W + 1)] for _ in range(n + 1)]

        # Заполняем таблицу
        for i in range(1, n + 1):
            for w in range(1, W + 1):
                if weights[i - 1] <= w:
                    dp[i][w] = max(
                        weights[i - 1] + dp[i - 1][w - weights[i - 1]], dp[i - 1][w]
                    )
                else:
                    dp[i][w] = dp[i - 1][w]

        # Восстанавливаем решение
        selected = []
        w = W
        for i in range(n, 0, -1):
            if dp[i][w] != dp[i - 1][w]:
                selected.append(files[i - 1])
                w -= weights[i - 1]

        selected.reverse()
        return selected

    async def get_available_tags(self, user_id: int) -> List[str]:
        """
        Получает список всех доступных тегов у файлов пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            List[str]: список уникальных тегов
        """
        files = await self.file_repo.get_files_by_user(user_id)

        tags = set()
        for file in files:
            if file.tags:
                tags.update(file.tags)

        return sorted(list(tags))
