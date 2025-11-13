"""Тесты для проверки работы LLM провайдеров (Gemini, GigaChat, Perplexity)."""

import logging
import os

import pytest

# Настройка логирования для тестов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def sample_text():
    """Пример текста для тестирования."""
    return """
    Artificial Intelligence and Machine Learning are rapidly transforming various industries.
    Deep learning models, particularly Large Language Models (LLMs), have shown remarkable
    capabilities in natural language processing tasks. These models require significant
    computational resources and large datasets for training.
    """


@pytest.fixture
def sample_meta():
    """Пример метаданных для тестирования."""
    return {
        "page_count": 1,
        "byte_size": 500,
        "precomputed_word_count": 50,
    }


@pytest.mark.asyncio
async def test_gemini_provider(sample_text, sample_meta):
    """Тест для проверки работы Gemini провайдера."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        pytest.skip("GEMINI_API_KEY не установлен, пропускаем тест")

    from project.mcp_pdf.llm_router import LLMRouter

    router = LLMRouter()
    
    # Проверяем, что Gemini провайдер настроен
    gemini_provider = next(
        (p for p in router.providers if p["name"] == "gemini"), None
    )
    assert gemini_provider is not None, "Gemini провайдер не настроен"
    assert gemini_provider["model"] == "gemini/gemini-2.5-flash-lite"

    # Тестируем генерацию контента
    prompt = "Проанализируй следующий текст и верни краткое резюме в JSON формате: " + sample_text
    system_prompt = "Ты помощник для анализа текста. Возвращай только валидный JSON."

    try:
        content, provider_name = await router.generate_content(
            prompt=prompt,
            system_prompt=system_prompt,
            max_retries=2,
        )
        
        assert provider_name == "gemini", f"Ожидался gemini, получен {provider_name}"
        assert content is not None, "Контент не должен быть None"
        assert len(content) > 0, "Контент не должен быть пустым"
        
        logger.info(f"✓ Gemini тест пройден. Длина ответа: {len(content)} символов")
        logger.debug(f"Ответ Gemini (первые 200 символов): {content[:200]}")
        
    except Exception as e:
        pytest.fail(f"Gemini провайдер вернул ошибку: {e}")


@pytest.mark.asyncio
async def test_gigachat_provider(sample_text, sample_meta):
    """Тест для проверки работы GigaChat провайдера."""
    gigachat_key = os.getenv("GIGACHAT_AUTH_KEY")
    if not gigachat_key:
        pytest.skip("GIGACHAT_AUTH_KEY не установлен, пропускаем тест")

    from project.mcp_pdf.llm_router import LLMRouter
    from project.mcp_pdf.gigachat_client import get_gigachat_client

    router = LLMRouter()
    
    # Проверяем, что GigaChat провайдер настроен
    gigachat_provider = next(
        (p for p in router.providers if p["name"] == "gigachat"), None
    )
    assert gigachat_provider is not None, "GigaChat провайдер не настроен"
    assert gigachat_provider.get("use_direct_client") is True, "GigaChat должен использовать прямой клиент"

    # Тестируем генерацию контента напрямую через GigaChat клиент
    # (так как роутер может использовать другой провайдер первым)
    prompt = "Проанализируй следующий текст и верни краткое резюме в JSON формате: " + sample_text
    system_prompt = "Ты помощник для анализа текста. Возвращай только валидный JSON."

    try:
        # Используем прямой клиент GigaChat для тестирования
        client = get_gigachat_client()
        content = await client.generate_content(
            prompt=prompt,
            system_prompt=system_prompt,
            max_retries=2,
        )
        
        assert content is not None, "Контент не должен быть None"
        assert len(content) > 0, "Контент не должен быть пустым"
        
        logger.info(f"✓ GigaChat тест пройден. Длина ответа: {len(content)} символов")
        logger.debug(f"Ответ GigaChat (первые 200 символов): {content[:200]}")
        
        # Также проверяем, что GigaChat доступен через роутер (может быть использован при fallback)
        # Временно отключаем другие провайдеры для проверки
        original_providers = router.providers.copy()
        router.providers = [gigachat_provider]  # Только GigaChat
        
        try:
            content2, provider_name = await router.generate_content(
                prompt=prompt,
                system_prompt=system_prompt,
                max_retries=2,
            )
            assert provider_name == "gigachat", f"Ожидался gigachat, получен {provider_name}"
            logger.info("✓ GigaChat работает через роутер")
        finally:
            router.providers = original_providers  # Восстанавливаем
        
    except Exception as e:
        pytest.fail(f"GigaChat провайдер вернул ошибку: {e}")


@pytest.mark.asyncio
async def test_perplexity_provider(sample_text, sample_meta):
    """Тест для проверки работы Perplexity провайдера."""
    # Проверяем обе переменные для совместимости
    perplexity_key = os.getenv("PERPLEXITYAI_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        pytest.skip("PERPLEXITYAI_API_KEY или PERPLEXITY_API_KEY не установлен, пропускаем тест")

    from project.mcp_pdf.llm_router import LLMRouter

    router = LLMRouter()
    
    # Проверяем, что Perplexity провайдер настроен
    perplexity_provider = next(
        (p for p in router.providers if p["name"] == "perplexity"), None
    )
    assert perplexity_provider is not None, "Perplexity провайдер не настроен"
    assert "perplexity" in perplexity_provider["model"]

    # Тестируем генерацию контента
    # Временно отключаем другие провайдеры для проверки Perplexity
    prompt = "Проанализируй следующий текст и верни краткое резюме в JSON формате: " + sample_text
    system_prompt = "Ты помощник для анализа текста. Возвращай только валидный JSON."

    try:
        # Временно оставляем только Perplexity провайдер
        original_providers = router.providers.copy()
        router.providers = [perplexity_provider]  # Только Perplexity
        
        try:
            content, provider_name = await router.generate_content(
                prompt=prompt,
                system_prompt=system_prompt,
                max_retries=2,
            )
            
            assert provider_name == "perplexity", f"Ожидался perplexity, получен {provider_name}"
            assert content is not None, "Контент не должен быть None"
            assert len(content) > 0, "Контент не должен быть пустым"
            
            logger.info(f"✓ Perplexity тест пройден. Длина ответа: {len(content)} символов")
            logger.debug(f"Ответ Perplexity (первые 200 символов): {content[:200]}")
        finally:
            router.providers = original_providers  # Восстанавливаем
        
    except Exception as e:
        pytest.fail(f"Perplexity провайдер вернул ошибку: {e}")


@pytest.mark.asyncio
async def test_llm_router_fallback(sample_text, sample_meta):
    """Тест для проверки fallback механизма между провайдерами."""
    from project.mcp_pdf.llm_router import LLMRouter

    router = LLMRouter()
    
    if not router.providers:
        pytest.skip("Нет настроенных провайдеров, пропускаем тест")

    # Проверяем, что есть хотя бы один провайдер
    assert len(router.providers) > 0, "Должен быть настроен хотя бы один провайдер"
    
    logger.info(f"Настроено провайдеров: {len(router.providers)}")
    for provider in router.providers:
        logger.info(f"  - {provider['name']}: {provider['model']}")

    # Тестируем генерацию контента (должен использоваться первый доступный провайдер)
    prompt = "Проанализируй следующий текст и верни краткое резюме: " + sample_text
    system_prompt = "Ты помощник для анализа текста."

    try:
        content, provider_name = await router.generate_content(
            prompt=prompt,
            system_prompt=system_prompt,
            max_retries=2,
        )
        
        assert provider_name in [p["name"] for p in router.providers], \
            f"Провайдер {provider_name} не найден в списке настроенных"
        assert content is not None, "Контент не должен быть None"
        assert len(content) > 0, "Контент не должен быть пустым"
        
        logger.info(f"✓ Fallback тест пройден. Использован провайдер: {provider_name}")
        
    except Exception as e:
        pytest.fail(f"Роутер вернул ошибку: {e}")


@pytest.mark.asyncio
async def test_llm_analysis_integration(sample_text, sample_meta):
    """Интеграционный тест для проверки полного анализа через _call_llm."""
    from project.mcp_pdf.tools import _call_llm

    # Проверяем наличие хотя бы одного API ключа
    has_provider = any([
        os.getenv("GEMINI_API_KEY"),
        os.getenv("GIGACHAT_AUTH_KEY"),
        os.getenv("PERPLEXITYAI_API_KEY") or os.getenv("PERPLEXITY_API_KEY"),
    ])
    
    if not has_provider:
        pytest.skip("Нет настроенных API ключей, пропускаем тест")

    try:
        result = await _call_llm(sample_text, sample_meta, max_retries=2)
        
        # Проверяем структуру результата
        assert isinstance(result, dict), "Результат должен быть словарем"
        assert "volume" in result, "Результат должен содержать поле 'volume'"
        assert "complexity" in result, "Результат должен содержать поле 'complexity'"
        assert "category" in result, "Результат должен содержать поле 'category'"
        
        # Проверяем структуру volume
        assert "word_count" in result["volume"], "volume должен содержать word_count"
        assert "char_count" in result["volume"], "volume должен содержать char_count"
        
        # Проверяем структуру complexity
        assert "score" in result["complexity"], "complexity должен содержать score"
        assert "level" in result["complexity"], "complexity должен содержать level"
        
        # Проверяем структуру category
        assert "label" in result["category"], "category должен содержать label"
        assert "score" in result["category"], "category должен содержать score"
        
        logger.info(f"✓ Интеграционный тест пройден")
        logger.debug(f"Результат анализа: category={result['category']['label']}, "
                    f"complexity={result['complexity']['level']}")
        
    except Exception as e:
        pytest.fail(f"Интеграционный тест вернул ошибку: {e}")


if __name__ == "__main__":
    # Запуск тестов напрямую
    pytest.main([__file__, "-v", "-s"])

