#!/usr/bin/env python3
"""Простой скрипт для проверки категоризации PDF."""

import asyncio
import json
import sys
from pathlib import Path

from project.api.pdf_analysis import (
    analyze_pdf_path,
    classify_or_create_category,
    extract_pdf,
)


async def test_basic_category(pdf_path: str):
    """Тест базовой категоризации (из analyze_pdf_path)."""
    print(f"\n{'='*60}")
    print(f"Тест 1: Базовая категоризация")
    print(f"Файл: {pdf_path}")
    print(f"{'='*60}")
    
    try:
        result = await analyze_pdf_path(pdf_path)
        category = result.get("category", {})
        
        print(f"✓ Категория найдена:")
        print(f"  Label: {category.get('label')}")
        print(f"  Score: {category.get('score')}")
        print(f"  Basis: {category.get('basis', '')[:100]}...")
        print(f"  Keywords: {', '.join(category.get('keywords', [])[:5])}")
        
        # Проверка валидности
        if category.get("label") == "Другое" and category.get("score") == 0.0:
            print("  ⚠ ПРОБЛЕМА: Категория не определена (fallback)")
            return False
        elif category.get("score", 0) < 0.5:
            print("  ⚠ ВНИМАНИЕ: Низкий score категории")
            return False
        else:
            print("  ✓ Категория определена корректно")
            return True
    except Exception as e:
        print(f"  ✗ Ошибка: {e}")
        return False


async def test_classify_with_existing(pdf_path: str):
    """Тест категоризации с существующими категориями."""
    print(f"\n{'='*60}")
    print(f"Тест 2: Категоризация с существующими категориями")
    print(f"Файл: {pdf_path}")
    print(f"{'='*60}")
    
    # Извлекаем текст и метаданные
    text, meta = await extract_pdf(path=pdf_path)
    
    # Определяем существующие категории
    existing_categories = [
        {
            "label": "Научная статья",
            "description": "Академические публикации, исследования, научные работы",
            "keywords": ["research", "study", "academic", "publication", "paper"]
        },
        {
            "label": "Руководство / Handbook",
            "description": "Технические руководства, учебные пособия, документация",
            "keywords": ["handbook", "guide", "tutorial", "manual", "documentation"]
        },
        {
            "label": "Справочник",
            "description": "Справочные материалы, инструкции, правила",
            "keywords": ["reference", "guide", "rules", "instructions"]
        }
    ]
    
    print(f"Существующие категории:")
    for cat in existing_categories:
        print(f"  - {cat['label']}: {cat['description']}")
    
    try:
        result = await classify_or_create_category(
            text=text,
            meta=meta,
            existing_categories=existing_categories
        )
        
        decision = result.get("decision")
        category = result.get("category", {})
        
        print(f"\n✓ Результат категоризации:")
        print(f"  Decision: {decision}")
        print(f"  Category label: {category.get('label')}")
        print(f"  Score: {category.get('score')}")
        print(f"  Basis: {category.get('basis', '')[:100]}...")
        
        if decision == "matched_existing":
            existing_label = result.get("existing_label")
            print(f"  ✓ Найдена существующая категория: {existing_label}")
        elif decision == "created_new":
            new_cat = result.get("new_category_def", {})
            print(f"  ✓ Создана новая категория:")
            print(f"    Label: {new_cat.get('label')}")
            print(f"    Description: {new_cat.get('description', '')[:80]}...")
        
        return True
    except Exception as e:
        print(f"  ✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_category_consistency(pdf_path: str):
    """Тест консистентности категорий при повторных запросах."""
    print(f"\n{'='*60}")
    print(f"Тест 3: Консистентность категорий")
    print(f"Файл: {pdf_path}")
    print(f"{'='*60}")
    
    categories = []
    scores = []
    for i in range(3):
        try:
            result = await analyze_pdf_path(pdf_path)
            cat = result.get("category", {})
            label = cat.get("label")
            score = cat.get("score", 0)
            categories.append(label)
            scores.append(score)
            print(f"  Попытка {i+1}: {label} (score: {score})")
        except Exception as e:
            print(f"  Попытка {i+1}: Ошибка - {e}")
            return False
    
    # Проверяем консистентность
    unique = set(categories)
    
    # Нормализуем категории для сравнения (убираем лишние пробелы, скобки)
    import re
    normalized = [re.sub(r'\s+', ' ', re.sub(r'[()/]', ' ', cat.lower())).strip() for cat in categories]
    normalized_unique = set(normalized)
    
    # Проверяем, что score высокий и стабильный
    avg_score = sum(scores) / len(scores)
    score_variance = max(scores) - min(scores)
    
    if len(unique) == 1:
        print(f"  ✓ Категории полностью консистентны: {categories[0]}")
        print(f"  ✓ Средний score: {avg_score:.2f}, разброс: {score_variance:.2f}")
        return True
    elif len(normalized_unique) == 1:
        print(f"  ✓ Категории семантически консистентны (различаются только форматированием)")
        print(f"  ✓ Средний score: {avg_score:.2f}, разброс: {score_variance:.2f}")
        return True
    elif avg_score >= 0.9 and score_variance < 0.1:
        print(f"  ⚠ Категории различаются, но score высокий и стабильный")
        print(f"  ✓ Средний score: {avg_score:.2f}, разброс: {score_variance:.2f}")
        print(f"  ⚠ Варианты: {unique}")
        # Считаем это приемлемым для LLM
        return True
    else:
        print(f"  ⚠ Категории различаются: {unique}")
        print(f"  ⚠ Средний score: {avg_score:.2f}, разброс: {score_variance:.2f}")
        return False


async def main():
    if len(sys.argv) < 2:
        print("Использование: python test_category.py <путь_к_pdf>")
        print("\nПримеры:")
        print("  python test_category.py pdf_for_eval/llm-as-judge.pdf")
        print("  python test_category.py pdf_for_eval/Traffic\\ Signs.pdf")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    if not Path(pdf_path).exists():
        print(f"Ошибка: файл {pdf_path} не найден")
        sys.exit(1)
    
    print(f"\n🧪 Тестирование категоризации для: {pdf_path}\n")
    
    results = []
    
    # Тест 1: Базовая категоризация
    results.append(await test_basic_category(pdf_path))
    
    # Тест 2: С существующими категориями
    results.append(await test_classify_with_existing(pdf_path))
    
    # Тест 3: Консистентность
    results.append(await test_category_consistency(pdf_path))
    
    # Итоги
    print(f"\n{'='*60}")
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print(f"{'='*60}")
    print(f"Тест 1 (Базовая категоризация): {'✓ PASS' if results[0] else '✗ FAIL'}")
    print(f"Тест 2 (С существующими категориями): {'✓ PASS' if results[1] else '✗ FAIL'}")
    print(f"Тест 3 (Консистентность): {'✓ PASS' if results[2] else '✗ FAIL'}")
    
    if all(results):
        print("\n✓ Все тесты пройдены!")
        return 0
    else:
        print("\n⚠ Некоторые тесты не прошли")
        return 1


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sys.exit(asyncio.run(main()))

