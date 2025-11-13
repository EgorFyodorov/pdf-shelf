"""Клиент для работы с GigaChat API."""

import os
import asyncio
import aiohttp
import json
import logging
from typing import Any, Optional
from datetime import datetime, timedelta
import uuid

logger = logging.getLogger(__name__)


class GigaChatClient:
    """Клиент для работы с GigaChat API."""

    def __init__(self):
        self.auth_key = os.getenv("GIGACHAT_AUTH_KEY")  # Authorization key (Base64)
        self.scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.model = os.getenv("GIGACHAT_MODEL", "GigaChat-2")
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.api_base = "https://gigachat.devices.sberbank.ru/api/v1"
        self.auth_base = "https://ngw.devices.sberbank.ru:9443/api/v2"
        self._token_lock = asyncio.Lock()  # Lock для синхронизации получения токена

    async def _get_access_token(self) -> str:
        """Получает Access token (валиден 30 минут)."""
        # Используем lock для предотвращения параллельных запросов токена
        async with self._token_lock:
            # Проверяем еще раз после получения lock (возможно, другой поток уже получил токен)
            if (
                self.access_token
                and self.token_expires_at
                and datetime.now() < self.token_expires_at
            ):
                return self.access_token

            if not self.auth_key:
                raise RuntimeError("GIGACHAT_AUTH_KEY не установлен")

            rq_uid = str(uuid.uuid4())

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(
                        f"{self.auth_base}/oauth",
                        headers={
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Accept": "application/json",
                            "RqUID": rq_uid,
                            "Authorization": f"Basic {self.auth_key}",
                        },
                        data={"scope": self.scope},
                        ssl=False,  # GigaChat использует самоподписанный сертификат
                    ) as resp:
                        if resp.status == 429:
                            # Rate limit - ждем перед повтором
                            error_text = await resp.text()
                            logger.warning("Rate limit при получении токена, ждем 5 секунд...")
                            await asyncio.sleep(5)
                            raise RuntimeError(
                                f"Rate limit при получении токена: {resp.status} - {error_text}"
                            )
                        
                        if resp.status != 200:
                            error_text = await resp.text()
                            raise RuntimeError(
                                f"Failed to get access token: {resp.status} - {error_text}"
                            )

                        data = await resp.json()
                        self.access_token = data.get("access_token")
                        # expires_in обычно в секундах до истечения (например, 1800 = 30 минут)
                        # expires_at может быть timestamp в секундах или миллисекундах
                        expires_in = data.get("expires_in")
                        expires_at = data.get("expires_at")
                        
                        if expires_in:
                            # expires_in - это количество секунд до истечения
                            # Минус минута для запаса
                            self.token_expires_at = datetime.now() + timedelta(
                                seconds=int(expires_in) - 60
                            )
                        elif expires_at:
                            # expires_at - это timestamp
                            # Проверяем, в секундах или миллисекундах
                            if expires_at > 1e10:  # Если больше 10^10, вероятно миллисекунды
                                expires_at = expires_at / 1000
                            # Преобразуем timestamp в datetime
                            self.token_expires_at = datetime.fromtimestamp(expires_at) - timedelta(seconds=60)
                        else:
                            # По умолчанию 30 минут, минус минута для запаса
                            self.token_expires_at = datetime.now() + timedelta(seconds=1740)

                        logger.info("GigaChat access token получен")
                        return self.access_token
                except aiohttp.ClientError as e:
                    raise RuntimeError(f"Network error while getting access token: {e}") from e

    async def generate_content(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_retries: int = 5,
    ) -> str:
        """Генерирует контент через GigaChat API."""
        token = await self._get_access_token()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error = None
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.api_base}/chat/completions",
                        headers={
                            "Accept": "application/json",
                            "Authorization": f"Bearer {token}",
                        },
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": 0.7,
                        },
                        ssl=False,  # GigaChat использует самоподписанный сертификат
                    ) as resp:
                        if resp.status == 401:
                            # Токен истек, обновляем
                            logger.info("Access token истек, обновляем...")
                            token = await self._get_access_token()
                            continue

                        if resp.status == 503 or resp.status == 429:
                            # Временная ошибка, retry
                            wait_time = 2 ** (attempt + 1)
                            logger.info(
                                f"GigaChat API временно недоступен (попытка {attempt + 1}/{max_retries}), "
                                f"повтор через {wait_time}с..."
                            )
                            await asyncio.sleep(wait_time)
                            continue

                        if resp.status != 200:
                            error_text = await resp.text()
                            raise RuntimeError(
                                f"GigaChat API error: {resp.status} - {error_text}"
                            )

                        data = await resp.json()
                        logger.debug("GigaChat API response structure: %s", type(data))
                        
                        # Извлекаем текст из ответа
                        # GigaChat может возвращать ответ в разных форматах
                        content = None
                        
                        # Формат 1: OpenAI-совместимый формат
                        if isinstance(data, dict):
                            choices = data.get("choices", [])
                            if choices and len(choices) > 0:
                                message = choices[0].get("message", {})
                                if isinstance(message, dict):
                                    content = message.get("content", "")
                                elif isinstance(message, str):
                                    content = message
                        
                        # Формат 2: Прямой ответ в поле "content" или "text"
                        if not content and isinstance(data, dict):
                            content = data.get("content") or data.get("text") or data.get("message")
                        
                        # Формат 3: Ответ - строка напрямую
                        if not content and isinstance(data, str):
                            content = data
                        
                        if content:
                            # Если content - не строка, преобразуем в строку
                            if not isinstance(content, str):
                                content = str(content)
                            return content
                        else:
                            logger.error("Unexpected GigaChat response format: %s", data)
                            raise RuntimeError(f"Empty or unexpected content in GigaChat response: {data}")

            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                if (
                    ("503" in str(e) or "429" in str(e) or "unavailable" in error_str)
                    and attempt < max_retries - 1
                ):
                    wait_time = 2 ** (attempt + 1)
                    logger.info(
                        f"GigaChat временно недоступен (попытка {attempt + 1}/{max_retries}), "
                        f"повтор через {wait_time}с..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                elif attempt == max_retries - 1:
                    raise
                else:
                    raise

        if last_error:
            raise last_error
        raise RuntimeError("Failed to get content from GigaChat API")


# Глобальный клиент
_gigachat_client: Optional[GigaChatClient] = None


def get_gigachat_client() -> GigaChatClient:
    """Получить или создать глобальный клиент GigaChat."""
    global _gigachat_client
    if _gigachat_client is None:
        _gigachat_client = GigaChatClient()
    return _gigachat_client

