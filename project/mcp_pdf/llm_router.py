"""Роутер для LLM с fallback между провайдерами через LiteLLM."""

import os
import logging
from typing import Optional, Any

try:
    from litellm import acompletion
    from litellm.exceptions import (
        APIConnectionError,
        APIError,
        RateLimitError,
        ServiceUnavailableError,
        AuthenticationError,
    )
except ImportError:
    # Если litellm не установлен, создаем заглушки
    acompletion = None
    APIConnectionError = Exception
    APIError = Exception
    RateLimitError = Exception
    ServiceUnavailableError = Exception
    AuthenticationError = Exception

logger = logging.getLogger(__name__)


class LLMRouter:
    """Роутер для LLM с fallback между провайдерами."""

    def __init__(self):
        self.providers = self._setup_providers()

    def _setup_providers(self) -> list[dict[str, Any]]:
        """Настраивает список провайдеров в порядке приоритета."""
        providers = []

        # 1. Gemini (если доступен)
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            providers.append({
                "name": "gemini",
                "model": "gemini/gemini-2.5-flash-lite",
                "api_key": gemini_key,
                "enabled": True,
            })
            logger.info("Gemini provider enabled")

        # 2. Perplexity (если доступен)
        # Проверяем обе переменные для совместимости
        perplexity_key = os.getenv("PERPLEXITYAI_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
        if perplexity_key:
            providers.append({
                "name": "perplexity",
                "model": "perplexity/sonar",
                "api_key": perplexity_key,
                "enabled": True,
            })
            logger.info("Perplexity provider enabled (model: sonar)")

        # 3. GigaChat (если доступен)
        gigachat_key = os.getenv("GIGACHAT_AUTH_KEY")
        if gigachat_key:
            # Для GigaChat через LiteLLM нужна специальная настройка
            # Пока используем прямой клиент, но можно добавить поддержку
            providers.append({
                "name": "gigachat",
                "model": "gigachat/gigachat-2",
                "api_key": gigachat_key,
                "enabled": True,
                "use_direct_client": True,  # Используем прямой клиент
            })
            logger.info("GigaChat provider enabled")

        return providers

    async def generate_content(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_retries: int = 3,
    ) -> tuple[str, str]:  # (content, provider_name)
        """Генерирует контент с fallback между провайдерами."""
        
        if not self.providers:
            raise RuntimeError("No LLM providers configured. Set at least one API key.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error = None

        for provider in self.providers:
            if not provider.get("enabled", True):
                continue

            provider_name = provider["name"]
            
            # Если GigaChat использует прямой клиент
            if provider.get("use_direct_client") and provider_name == "gigachat":
                try:
                    logger.info(f"Trying {provider_name} (direct client)...")
                    from .gigachat_client import get_gigachat_client
                    
                    client = get_gigachat_client()
                    content = await client.generate_content(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        max_retries=max_retries,
                    )
                    logger.info(f"Successfully got response from {provider_name}")
                    return content, provider_name
                    
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    is_temporary = any(
                        keyword in error_str
                        for keyword in ["503", "429", "unavailable", "overloaded", "rate limit"]
                    )
                    
                    if is_temporary:
                        logger.warning(
                            f"{provider_name} temporarily unavailable: {e}, "
                            f"trying next provider..."
                        )
                    else:
                        logger.warning(
                            f"{provider_name} failed: {e}, trying next provider..."
                        )
                    continue

            # Для остальных провайдеров используем LiteLLM
            if acompletion is None:
                raise RuntimeError("litellm is not installed. Install it with: pip install litellm")
            
            try:
                logger.info(f"Trying {provider_name} via LiteLLM...")
                
                response = await acompletion(
                    model=provider["model"],
                    messages=messages,
                    api_key=provider["api_key"],
                    timeout=30.0,
                    max_retries=1,  # LiteLLM сам делает retry, мы делаем fallback
                )
                
                content = response.choices[0].message.content
                if not content:
                    raise RuntimeError("Empty response from LLM")
                
                logger.info(f"Successfully got response from {provider_name}")
                return content, provider_name

            except AuthenticationError as e:
                # Ошибка аутентификации - API ключ невалидный или отсутствует
                last_error = e
                error_str = str(e).lower()
                if "api key" in error_str or "invalid" in error_str or "authentication" in error_str:
                    logger.info(
                        f"{provider_name} authentication failed (invalid API key), "
                        f"skipping to next provider..."
                    )
                else:
                    logger.warning(
                        f"{provider_name} authentication error: {e}, "
                        f"trying next provider..."
                    )
                continue

            except (
                APIConnectionError,
                ServiceUnavailableError,
                RateLimitError,
            ) as e:
                last_error = e
                logger.warning(
                    f"{provider_name} temporarily unavailable: {e}, "
                    f"trying next provider..."
                )
                continue

            except APIError as e:
                last_error = e
                error_str = str(e).lower()
                
                # Проверяем, это временная ошибка?
                is_temporary = any(
                    keyword in error_str
                    for keyword in ["503", "429", "unavailable", "overloaded", "rate limit"]
                )
                
                if is_temporary:
                    logger.warning(
                        f"{provider_name} temporarily unavailable: {e}, "
                        f"trying next provider..."
                    )
                else:
                    logger.warning(
                        f"{provider_name} failed: {e}, trying next provider..."
                    )
                continue

            except Exception as e:
                last_error = e
                logger.warning(
                    f"{provider_name} failed with unexpected error: {e}, "
                    f"trying next provider..."
                )
                continue

        # Если все провайдеры не сработали
        if last_error:
            last_provider_name = self.providers[-1]["name"] if self.providers else "unknown"
            raise RuntimeError(
                f"All LLM providers failed. Last error from {last_provider_name}: {last_error}"
            ) from last_error

        raise RuntimeError("No LLM providers available")


# Глобальный роутер
_llm_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Получить или создать глобальный роутер LLM."""
    global _llm_router
    if _llm_router is None:
        _llm_router = LLMRouter()
    return _llm_router

