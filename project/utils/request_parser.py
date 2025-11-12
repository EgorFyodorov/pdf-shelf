import re
from typing import List, Optional, Tuple


def parse_time_from_text(text: str) -> Optional[float]:
    """
    Извлекает время в минутах из текста пользователя.

    Примеры:
        "у меня есть 30 минут" -> 30.0
        "выгрузи на час чтения" -> 60.0
        "статьи на 1.5 часа" -> 90.0
        "20 мин" -> 20.0
        "полтора часа" -> 90.0
        "два часа" -> 120.0

    Returns:
        float: время в минутах или None если не найдено
    """
    text_lower = text.lower()

    # Словесные числа
    word_numbers = {
        "один": 1,
        "одна": 1,
        "одного": 1,
        "одной": 1,
        "два": 2,
        "две": 2,
        "двух": 2,
        "три": 3,
        "трёх": 3,
        "трех": 3,
        "четыре": 4,
        "четырёх": 4,
        "четырех": 4,
        "пять": 5,
        "пяти": 5,
        "шесть": 6,
        "шести": 6,
        "семь": 7,
        "семи": 7,
        "восемь": 8,
        "восьми": 8,
        "девять": 9,
        "девяти": 9,
        "десять": 10,
        "десяти": 10,
        "полтора": 1.5,
        "полутора": 1.5,
        "половина": 0.5,
    }

    # Паттерны для поиска времени
    patterns = [
        # "30 минут", "20 мин", "15минут"
        (r"(\d+(?:\.\d+)?)\s*(?:минут|мин)", 1.0),
        # "1 час", "2 часа", "1.5 часа"
        (r"(\d+(?:\.\d+)?)\s*(?:час|часа|часов)", 60.0),
        # "полтора часа", "два часа"
        (r"(полтора|полутора)\s*(?:час|часа)", 90.0),
        (r"(половина)\s*(?:час|часа)", 30.0),
    ]

    # Проверяем цифровые паттерны
    for pattern, multiplier in patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1))
                return value * multiplier
            except ValueError:
                # Если не число, проверяем словесное
                word = match.group(1)
                if word in word_numbers:
                    return word_numbers[word] * multiplier

    # Проверяем словесные числа + единицы
    for word, value in word_numbers.items():
        # "два часа"
        if re.search(rf"\b{word}\s*(?:час|часа|часов)\b", text_lower):
            return value * 60.0
        # "пять минут"
        if re.search(rf"\b{word}\s*(?:минут|мин)\b", text_lower):
            return value * 1.0

    return None


def parse_tags_from_text(
    text: str, available_tags: Optional[List[str]] = None
) -> List[str]:
    """
    Извлекает теги/темы из текста пользователя.

    Args:
        text: текст запроса пользователя
        available_tags: список доступных тегов в БД (для матчинга)

    Примеры:
        "материалы по ML на час" -> ["ML"]
        "статьи про экономику и бизнес" -> ["экономику", "бизнес"]
        "выгрузи по тематике наука" -> ["наука"]

    Returns:
        List[str]: список найденных тегов
    """
    text_lower = text.lower()
    found_tags = []

    # Ключевые фразы для определения тегов
    tag_patterns = [
        r"по\s+(?:тематике|теме|темам)\s+([а-яёa-z\s,]+?)(?:\s+на|\s+у\s+меня|$)",
        r"(?:про|о|об)\s+([а-яёa-z\s,]+?)(?:\s+на|\s+у\s+меня|$)",
        r"по\s+([а-яёa-z\s,]+?)(?:\s+на|\s+у\s+меня|$)",
        r"материал[ыа]*\s+([а-яёa-z\s,]+?)(?:\s+на|\s+у\s+меня|$)",
    ]

    for pattern in tag_patterns:
        match = re.search(pattern, text_lower)
        if match:
            tags_str = match.group(1).strip()
            # Разделяем по запятым и "и"
            potential_tags = re.split(r"[,и]\s*", tags_str)
            found_tags.extend([tag.strip() for tag in potential_tags if tag.strip()])

    # Если доступны теги из БД, пытаемся матчить
    if available_tags:
        matched_tags = []
        for tag in found_tags:
            # Точное совпадение (case-insensitive)
            for avail_tag in available_tags:
                if tag.lower() == avail_tag.lower():
                    matched_tags.append(avail_tag)
                    break
            else:
                # Частичное совпадение
                for avail_tag in available_tags:
                    if (
                        tag.lower() in avail_tag.lower()
                        or avail_tag.lower() in tag.lower()
                    ):
                        matched_tags.append(avail_tag)
                        break
        return list(set(matched_tags))

    return list(set(found_tags))


def is_export_request(text: str) -> bool:
    """
    Определяет, является ли сообщение запросом на выгрузку материалов.

    Примеры запросов на выгрузку:
        - "у меня есть 30 минут"
        - "выгрузи материалы"
        - "дай почитать"
        - "что почитать"
        - "материалы на час"

    Returns:
        bool: True если это запрос на выгрузку
    """
    text_lower = text.lower()

    export_keywords = [
        r"\bвыгруз",
        r"\bдай\b",
        r"\bпокаж",
        r"\bпочитать\b",
        r"\bчитать\b",
        r"\bматериал",
        r"\bстать[иья]",
        r"\bу\s+меня\s+есть\s+\d+",
        r"\bна\s+\d+\s*(?:минут|час)",
        r"\bчто\s+почитать",
        r"\bподбер",
        r"\bпорекомендуй",
    ]

    for keyword in export_keywords:
        if re.search(keyword, text_lower):
            return True

    return False


def parse_export_request(
    text: str, available_tags: Optional[List[str]] = None
) -> Tuple[Optional[float], List[str]]:
    """
    Парсит запрос на выгрузку материалов.

    Returns:
        Tuple[Optional[float], List[str]]: (время в минутах, список тегов)
    """
    time_minutes = parse_time_from_text(text)
    tags = parse_tags_from_text(text, available_tags)

    return time_minutes, tags
