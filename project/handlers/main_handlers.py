import logging
import tempfile
from pathlib import Path

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Document, FSInputFile, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from project.api.pdf_analysis import PDFAnalysisError, analyze_pdf_path
from project.database.file_repository import FileRepository
from project.database.request_repository import RequestRepository
from project.database.user_repository import UserRepository
from project.keyboards.main_keyboards import (
    create_pagination_keyboard,
    create_tags_keyboard,
    main,
    time_selection,
)
from project.parser.parser import ParserError
from project.services.material_selector import MaterialSelector
from project.text.main_text import (
    delete_invalid_format,
    error_analysis,
    error_conversion,
    error_download,
    error_not_pdf,
    error_sender,
    export_ask_time,
    export_header,
    export_no_files,
    export_no_matches,
    export_no_matches_with_tags,
    export_sending,
    file_deleted,
    file_not_found,
    greet,
    help_text,
    library_empty,
    library_header,
    library_instruction,
    library_tags_header,
    pdf_processing,
    pdf_saved,
    stats_header,
    stats_instruction,
    stats_recent_header,
    stats_tags,
    stats_total_files,
    stats_total_sent,
    stats_total_time,
    url_multiple_processing,
    url_processing,
)
from project.utils.formatters import (
    clean_page_title,
    extract_tags_from_analysis,
    extract_urls,
    format_analysis_card,
    format_file_list_for_export,
    format_multiple_files_summary,
)
from project.utils.pagination import create_pagination_keyboard, format_files_page
from project.utils.request_parser import is_export_request, parse_export_request

logger = logging.getLogger(__name__)

router = Router()


class ExportStates(StatesGroup):
    """Состояния для процесса выгрузки материалов."""

    waiting_for_time = State()  # Ожидание выбора времени (тема уже выбрана)
    viewing_export = State()  # Просмотр списка подобранных файлов
    viewing_library = State()  # Просмотр библиотеки с пагинацией


@router.message(Command("start"))
async def start_handler(msg: Message, sessionmaker: async_sessionmaker):
    sender = msg.from_user
    if sender is None:
        await msg.answer(greet.format(name="Гость"), reply_markup=main)
        return

    user_repo = UserRepository(sessionmaker)
    await user_repo.create_or_update_user(sender.id, sender.full_name)

    await msg.answer(greet.format(name=sender.full_name), reply_markup=main)


@router.message(Command("help"))
async def help_handler(msg: Message):
    await msg.answer(help_text)


@router.callback_query(lambda c: c.data and (c.data.startswith("lib_page:") or c.data.startswith("exp_page:")))
async def pagination_callback_handler(callback: CallbackQuery, sessionmaker: async_sessionmaker, state: FSMContext):
    """Обрабатывает переключение страниц в библиотеке и экспорте."""
    await callback.answer()
    
    data_parts = callback.data.split(":")
    if len(data_parts) != 2:
        return
    
    prefix, page_str = data_parts
    try:
        page = int(page_str)
    except ValueError:
        return
    
    user_id = callback.from_user.id
    current_state = await state.get_state()
    
    if prefix == "lib_page" and current_state == ExportStates.viewing_library:
        # Пагинация библиотеки
        await show_library_page(callback.message, user_id, sessionmaker, state, page)
    elif prefix == "exp_page" and current_state == ExportStates.viewing_export:
        # Пагинация экспорта
        await show_export_page(callback.message, user_id, sessionmaker, state, page)


@router.message(Command("library"))
async def library_command_handler(msg: Message, sessionmaker: async_sessionmaker, state: FSMContext):
    sender = msg.from_user
    if sender is None:
        await msg.answer(error_sender)
        return

    await show_library(msg, sender.id, sessionmaker, state)


@router.message(Command("stats"))
async def stats_command_handler(msg: Message, sessionmaker: async_sessionmaker):
    sender = msg.from_user
    if sender is None:
        await msg.answer(error_sender)
        return

    await show_stats(msg, sender.id, sessionmaker)


@router.message()
async def pdf_handler(
    msg: Message, sessionmaker: async_sessionmaker, state: FSMContext, config, parser
):
    sender = msg.from_user
    if sender is None:
        await msg.answer(error_sender)
        return

    bot: Bot = msg.bot

    if msg.document:
        await handle_pdf_document(msg, sender.id, bot, sessionmaker)
    elif msg.text:
        await handle_text_message(msg, sender.id, bot, sessionmaker, state, parser)


async def handle_pdf_document(
    msg: Message, user_id: int, bot: Bot, sessionmaker: async_sessionmaker
):
    document: Document = msg.document

    if not document.mime_type or not document.mime_type.startswith("application/pdf"):
        await msg.answer(error_not_pdf)
        return

    processing_msg = await msg.answer(pdf_processing)

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / (document.file_name or "document.pdf")

            file = await bot.get_file(document.file_id)
            await bot.download_file(file.file_path, temp_path)

            analysis_json = await analyze_pdf_path(str(temp_path), timeout=120.0)

            title = analysis_json.get("category", {}).get("label", document.file_name)
            reading_time_min = analysis_json.get("volume", {}).get(
                "reading_time_min", 0
            )
            tags = extract_tags_from_analysis(analysis_json)

            file_repo = FileRepository(sessionmaker)
            saved_file = await file_repo.create_file(
                user_id=user_id,
                telegram_file_id=document.file_id,
                title=title,
                reading_time_min=reading_time_min,
                analysis_json=analysis_json,
                source_url=None,
                tags=tags,
            )

            card = format_analysis_card(saved_file, include_url=False)
            await bot.delete_message(msg.chat.id, processing_msg.message_id)
            await msg.answer(card)
            await msg.answer(pdf_saved)

            logger.info(f"PDF saved for user {user_id}: {saved_file.file_id}")

    except PDFAnalysisError as e:
        await bot.delete_message(msg.chat.id, processing_msg.message_id)
        await msg.answer(error_analysis.format(error=str(e)))
        logger.error(f"PDF analysis error for user {user_id}: {e}")
    except Exception as e:
        await bot.delete_message(msg.chat.id, processing_msg.message_id)
        await msg.answer(error_download)
        logger.error(f"Error processing PDF for user {user_id}: {e}", exc_info=True)


async def handle_text_message(
    msg: Message,
    user_id: int,
    bot: Bot,
    sessionmaker: async_sessionmaker,
    state: FSMContext,
    parser,
):
    text = msg.text.strip()
    text_lower = text.lower()

    # Обработка команд с кнопок
    if text in ["📚 Моя библиотека"] or any(
        keyword in text_lower
        for keyword in ["библиотек", "список", "мои файлы", "мои материалы"]
    ):
        await show_library(msg, user_id, sessionmaker, state)
        return

    if text in ["📊 Статистика"] or "статистик" in text_lower:
        await show_stats(msg, user_id, sessionmaker)
        return

    if text in ["❓ Помощь"] or text_lower in ["помощь", "help", "/help"]:
        await msg.answer(help_text)
        return

    # Обработка кнопки "📤 Выгрузить материалы"
    if text == "📤 Выгрузить материалы":
        await start_export_flow(msg, user_id, sessionmaker, state)
        return

    # Обработка выбора темы (кнопки с "🏷")
    if text.startswith("🏷 ") or text == "📚 Все темы":
        await handle_tag_selection(msg, user_id, text, state)
        return

    # Обработка кнопок выбора времени (из time_selection keyboard)
    if text in ["15 минут", "30 минут", "1 час", "2 часа"]:
        await handle_time_selection(msg, user_id, bot, sessionmaker, text, state)
        return

    # Обработка текстовых запросов на выгрузку
    if is_export_request(text):
        await handle_export_request(msg, user_id, bot, sessionmaker)
        return

    # Обработка команды удаления файла
    if text.lower().startswith("удалить"):
        await handle_file_deletion(msg, user_id, text, bot, sessionmaker, state)
        return

    # Проверка, является ли сообщение числом (номер файла)
    if text.isdigit():
        await handle_file_number(msg, user_id, int(text), bot, sessionmaker, state)
        return

    urls = extract_urls(text)

    if not urls:
        return

    if len(urls) == 1:
        await process_single_url(msg, urls[0], user_id, bot, sessionmaker, parser)
    else:
        await process_multiple_urls(msg, urls, user_id, bot, sessionmaker, parser)


async def process_single_url(
    msg: Message, url: str, user_id: int, bot: Bot, sessionmaker: async_sessionmaker, parser
):
    file_repo = FileRepository(sessionmaker)
    
    # Проверяем, есть ли уже этот URL в библиотеке
    existing_file = await file_repo.get_file_by_source_url(user_id, url)
    if existing_file:
        card = format_analysis_card(existing_file, include_url=True)
        await msg.answer("ℹ️ Этот материал уже есть в вашей библиотеке:\n\n" + card)
        logger.info(f"Duplicate URL skipped for user {user_id}: {url}")
        return
    
    processing_msg = await msg.answer(url_processing)

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "converted.pdf"

            page_title = await parser.parse(url, temp_path)

            analysis_json = await analyze_pdf_path(str(temp_path), timeout=120.0)

            # Очищаем и используем заголовок страницы, если он есть, иначе label из категории
            cleaned_title = clean_page_title(page_title)
            title = cleaned_title if cleaned_title and cleaned_title != "Документ" else analysis_json.get("category", {}).get("label", "Документ")
            reading_time_min = analysis_json.get("volume", {}).get(
                "reading_time_min", 0
            )
            tags = extract_tags_from_analysis(analysis_json)

            pdf_file = FSInputFile(temp_path, filename=f"{title}.pdf")
            sent_msg = await bot.send_document(msg.chat.id, pdf_file)

            telegram_file_id = sent_msg.document.file_id

            saved_file = await file_repo.create_file(
                user_id=user_id,
                telegram_file_id=telegram_file_id,
                title=title,
                reading_time_min=reading_time_min,
                analysis_json=analysis_json,
                source_url=url,
                tags=tags,
            )

            card = format_analysis_card(saved_file, include_url=True)
            await bot.delete_message(msg.chat.id, processing_msg.message_id)
            await msg.answer(card)
            await msg.answer(pdf_saved)

            logger.info(f"URL converted and saved for user {user_id}: {url}")

    except ParserError as e:
        await bot.delete_message(msg.chat.id, processing_msg.message_id)
        await msg.answer(error_conversion)
        logger.error(f"Parser error for user {user_id}, URL {url}: {e}")
    except PDFAnalysisError as e:
        await bot.delete_message(msg.chat.id, processing_msg.message_id)
        await msg.answer(error_analysis.format(error=str(e)))
        logger.error(f"Analysis error for user {user_id}, URL {url}: {e}")
    except Exception as e:
        await bot.delete_message(msg.chat.id, processing_msg.message_id)
        await msg.answer(error_conversion)
        logger.error(
            f"Error processing URL for user {user_id}, URL {url}: {e}", exc_info=True
        )


async def process_multiple_urls(
    msg: Message,
    urls: list[str],
    user_id: int,
    bot: Bot,
    sessionmaker: async_sessionmaker,
    parser,
):
    processing_msg = await msg.answer(url_multiple_processing.format(count=len(urls)))

    file_repo = FileRepository(sessionmaker)
    successful_files = []
    skipped_files = []
    total_time = 0.0

    for url in urls:
        # Проверяем, есть ли уже этот URL в библиотеке
        existing_file = await file_repo.get_file_by_source_url(user_id, url)
        if existing_file:
            skipped_files.append(url)
            logger.info(f"Duplicate URL skipped for user {user_id}: {url}")
            continue
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / "converted.pdf"

                page_title = await parser.parse(url, temp_path)

                analysis_json = await analyze_pdf_path(str(temp_path), timeout=120.0)

                # Очищаем и используем заголовок страницы, если он есть, иначе label из категории
                cleaned_title = clean_page_title(page_title)
                title = cleaned_title if cleaned_title and cleaned_title != "Документ" else analysis_json.get("category", {}).get("label", "Документ")
                reading_time_min = analysis_json.get("volume", {}).get(
                    "reading_time_min", 0
                )
                tags = extract_tags_from_analysis(analysis_json)

                pdf_file = FSInputFile(temp_path, filename=f"{title}.pdf")
                sent_msg = await bot.send_document(msg.chat.id, pdf_file)

                telegram_file_id = sent_msg.document.file_id

                saved_file = await file_repo.create_file(
                    user_id=user_id,
                    telegram_file_id=telegram_file_id,
                    title=title,
                    reading_time_min=reading_time_min,
                    analysis_json=analysis_json,
                    source_url=url,
                    tags=tags,
                )

                card = format_analysis_card(saved_file, include_url=True)
                await msg.answer(card)

                main_topic = tags[0] if tags else "Без темы"
                complexity_level = analysis_json.get("complexity", {}).get("level", "средняя")
                successful_files.append((url, reading_time_min, main_topic, complexity_level))
                total_time += reading_time_min

                logger.info(f"URL {url} converted and saved for user {user_id}")

        except Exception as e:
            logger.error(f"Error processing URL {url} for user {user_id}: {e}")
            await msg.answer(f"❌ Ошибка при обработке {url}")

    await bot.delete_message(msg.chat.id, processing_msg.message_id)

    if successful_files:
        summary = format_multiple_files_summary(successful_files, total_time)
        await msg.answer(summary)
    
    if skipped_files:
        skipped_count = len(skipped_files)
        skipped_msg = (
            f"ℹ️ Пропущено {skipped_count} материал (уже есть в библиотеке)"
            if skipped_count == 1
            else f"ℹ️ Пропущено {skipped_count} материала (уже есть в библиотеке)"
            if 2 <= skipped_count <= 4
            else f"ℹ️ Пропущено {skipped_count} материалов (уже есть в библиотеке)"
        )
        await msg.answer(skipped_msg)


async def handle_export_request(
    msg: Message, user_id: int, bot: Bot, sessionmaker: async_sessionmaker
):
    """Обработка запроса на выгрузку материалов."""
    text = msg.text.strip()

    selector = MaterialSelector(sessionmaker)
    available_tags = await selector.get_available_tags(user_id)

    time_minutes, tags = parse_export_request(text, available_tags)

    if time_minutes is None:
        await msg.answer(export_ask_time, reply_markup=time_selection)
        return

    await export_materials(msg, user_id, bot, sessionmaker, time_minutes, tags, state)


async def export_materials(
    msg: Message,
    user_id: int,
    bot: Bot,
    sessionmaker: async_sessionmaker,
    time_minutes: float,
    tags: list[str],
    state: FSMContext,
):
    """Показывает список подобранных материалов пользователю."""
    processing_msg = await msg.answer(export_sending)

    try:
        selector = MaterialSelector(sessionmaker)
        selected_files, total_time = await selector.select_materials(
            user_id=user_id,
            time_minutes=time_minutes,
            tags=tags if tags else None,
        )

        await bot.delete_message(msg.chat.id, processing_msg.message_id)

        if not selected_files:
            file_repo = FileRepository(sessionmaker)
            request_repo = RequestRepository(sessionmaker)
            all_files = await file_repo.get_files_by_user(user_id)

            if not all_files:
                await msg.answer(export_no_files, reply_markup=main)
                await state.clear()
                return
            
            # Получаем последние запрошенные файлы
            recent_files = await request_repo.get_recent_requested_files(user_id, limit=5)
            
            if not recent_files:
                # Если нет истории запросов, показываем сообщение об отсутствии совпадений
                if tags:
                    await msg.answer(
                        export_no_matches_with_tags.format(tags=", ".join(tags)),
                        reply_markup=main,
                    )
                else:
                    await msg.answer(export_no_matches, reply_markup=main)
                await state.clear()
                return
            
            # Показываем последние запрошенные файлы
            if tags:
                response = f"😔 Не нашлось материалов по темам: {', '.join(tags)}\n\n"
            else:
                response = "😔 Не нашлось подходящих материалов\n\n"
            
            response += "📚 Вот ваши последние запрошенные материалы:\n\n"
            
            for idx, file in enumerate(recent_files, 1):
                tags_str = ", ".join(file.tags) if file.tags else "Без тегов"
                complexity_level = file.analysis_json.get("complexity", {}).get("level", "средняя")
                
                response += f"{idx}. 📄 {file.title}\n"
                response += f"   ⏱ {float(file.reading_time_min):.0f} мин • 📊 {complexity_level} • 🏷 {tags_str}\n\n"
            
            response += "\n" + library_instruction
            
            # Сохраняем список файлов в state
            await state.update_data(selected_files=[f.file_id for f in recent_files])
            await state.set_state(ExportStates.viewing_export)
            
            await msg.answer(response, disable_web_page_preview=True, reply_markup=main)
            return

        # Формируем сообщение со списком подобранных файлов
        response = export_header.format(count=len(selected_files), total_time=total_time)
        response += "\n"

        for idx, file in enumerate(selected_files, 1):
            tags_str = ", ".join(file.tags) if file.tags else "Без тегов"
            complexity_level = file.analysis_json.get("complexity", {}).get("level", "средняя")
            
            response += f"{idx}. 📄 {file.title}\n"
            response += f"   ⏱ {float(file.reading_time_min):.0f} мин • 📊 {complexity_level} • 🏷 {tags_str}\n"

            if file.source_url:
                url_display = (
                    file.source_url[:50] + "..."
                    if len(file.source_url) > 50
                    else file.source_url
                )
                response += f"   🔗 {url_display}\n"

            response += "\n"

        response += "\n" + library_instruction

        # Сохраняем список файлов в state
        await state.update_data(selected_files=[f.file_id for f in selected_files])
        await state.set_state(ExportStates.viewing_export)

        await msg.answer(response, disable_web_page_preview=True, reply_markup=main)

        logger.info(
            f"Showed {len(selected_files)} files for export to user {user_id}, "
            f"total time: {total_time:.1f} min"
        )

    except Exception as e:
        await bot.delete_message(msg.chat.id, processing_msg.message_id)
        await msg.answer(
            f"❌ Ошибка при подборе материалов: {str(e)}", reply_markup=main
        )
        await state.clear()
        logger.error(
            f"Error exporting materials for user {user_id}: {e}", exc_info=True
        )


async def start_export_flow(
    msg: Message, user_id: int, sessionmaker: async_sessionmaker, state: FSMContext
):
    """Начинает процесс выгрузки материалов - показывает клавиатуру с тегами."""
    selector = MaterialSelector(sessionmaker)
    available_tags = await selector.get_available_tags(user_id)

    if not available_tags:
        await msg.answer(export_ask_time, reply_markup=time_selection)
        return

    tags_keyboard = create_tags_keyboard(available_tags)
    await msg.answer('🏷 Выберите тему или "Все темы":', reply_markup=tags_keyboard)
    await state.set_state(ExportStates.waiting_for_time)


async def handle_tag_selection(
    msg: Message, user_id: int, text: str, state: FSMContext
):
    """Обрабатывает выбор темы и показывает клавиатуру с временем."""
    # Извлекаем тег из текста (убираем "🏷 ")
    if text == "📚 Все темы":
        selected_tag = None
    else:
        selected_tag = text.replace("🏷 ", "").strip()

    # Сохраняем выбранную тему в state
    await state.update_data(selected_tag=selected_tag)

    # Показываем клавиатуру с временем
    await msg.answer(export_ask_time, reply_markup=time_selection)


async def handle_time_selection(
    msg: Message,
    user_id: int,
    bot: Bot,
    sessionmaker: async_sessionmaker,
    text: str,
    state: FSMContext,
):
    """Обрабатывает выбор времени и выгружает материалы с учетом выбранной темы."""
    # Получаем сохраненную тему из state
    state_data = await state.get_data()
    selected_tag = state_data.get("selected_tag")

    # Очищаем state
    await state.clear()

    # Парсим время
    selector = MaterialSelector(sessionmaker)
    available_tags = await selector.get_available_tags(user_id)
    time_minutes, _ = parse_export_request(text, available_tags)

    if time_minutes:
        tags = [selected_tag] if selected_tag else []
        await export_materials(msg, user_id, bot, sessionmaker, time_minutes, tags, state)


async def handle_file_deletion(
    msg: Message, user_id: int, text: str, bot: Bot, sessionmaker: async_sessionmaker, state: FSMContext
):
    """Обрабатывает команду удаления файла."""
    try:
        # Парсим номер файла из команды "удалить N"
        parts = text.lower().split()
        if len(parts) != 2 or not parts[1].isdigit():
            await msg.answer(delete_invalid_format)
            return

        file_number = int(parts[1])

        file_repo = FileRepository(sessionmaker)
        
        # Проверяем, находимся ли мы в режиме просмотра экспорта
        current_state = await state.get_state()
        if current_state == ExportStates.viewing_export:
            # Получаем файлы из state (подобранные для экспорта)
            data = await state.get_data()
            selected_file_ids = data.get("selected_files", [])
            
            if not selected_file_ids:
                await msg.answer(library_empty)
                await state.clear()
                return
            
            if file_number < 1 or file_number > len(selected_file_ids):
                await msg.answer(f"❌ Неверный номер. Введите число от 1 до {len(selected_file_ids)}")
                return
            
            # Получаем ID файла для удаления
            file_id = selected_file_ids[file_number - 1]
            file = await file_repo.get_file(file_id)
            
            if not file:
                await msg.answer(file_not_found)
                return
            
            # Удаляем файл из БД
            deleted = await file_repo.delete_file(file.file_id)
            
            if deleted:
                # Обновляем список файлов в state
                selected_file_ids.pop(file_number - 1)
                
                await msg.answer(file_deleted)
                logger.info(
                    f"User {user_id} deleted file {file.file_id} from export view (number {file_number})"
                )
                
                if selected_file_ids:
                    # Если файлы еще остались, обновляем state и показываем обновленный список
                    await state.update_data(selected_files=selected_file_ids)
                    # Получаем текущую страницу
                    current_page = data.get("current_page", 0)
                    # Показываем обновленный список
                    await send_export_list(msg.chat.id, user_id, sessionmaker, state, current_page, bot)
                else:
                    # Если файлов не осталось, очищаем state
                    await state.clear()
                    await msg.answer(export_no_files, reply_markup=main)
            else:
                await msg.answer(file_not_found)
        elif current_state == ExportStates.viewing_library:
            # Режим просмотра библиотеки с пагинацией
            data = await state.get_data()
            all_file_ids = data.get("all_file_ids", [])
            
            if not all_file_ids:
                await msg.answer(library_empty)
                await state.clear()
                return
            
            # Проверяем номер
            if file_number < 1 or file_number > len(all_file_ids):
                await msg.answer(f"❌ Неверный номер. Введите число от 1 до {len(all_file_ids)}")
                return
            
            # Получаем ID файла для удаления (номер относительно всего списка, не страницы)
            file_id = all_file_ids[file_number - 1]
            file = await file_repo.get_file(file_id)
            
            if not file:
                await msg.answer(file_not_found)
                return
            
            # Удаляем файл из БД
            deleted = await file_repo.delete_file(file.file_id)
            
            if deleted:
                await msg.answer(file_deleted)
                logger.info(
                    f"User {user_id} deleted file {file.file_id} from library (number {file_number})"
                )
                
                # Получаем текущую страницу и показываем обновленный список
                current_page = data.get("current_page", 0)
                await send_library_list(msg.chat.id, user_id, sessionmaker, state, current_page, bot)
            else:
                await msg.answer(file_not_found)
        else:
            # Обычный режим - удаляем из всей библиотеки (без пагинации/state)
            files = await file_repo.get_files_by_user(user_id)

            if not files:
                await msg.answer(library_empty)
                return

            if file_number < 1 or file_number > len(files):
                await msg.answer(f"❌ Неверный номер. Введите число от 1 до {len(files)}")
                return

            # Получаем файл по индексу (file_number - 1)
            file = files[file_number - 1]

            # Удаляем файл
            deleted = await file_repo.delete_file(file.file_id)

            if deleted:
                await msg.answer(file_deleted)
                logger.info(
                    f"User {user_id} deleted file {file.file_id} (number {file_number})"
                )
            else:
                await msg.answer(file_not_found)

    except Exception as e:
        logger.error(f"Error deleting file for user {user_id}: {e}", exc_info=True)
        await msg.answer("❌ Ошибка при удалении файла")


async def handle_file_number(
    msg: Message,
    user_id: int,
    file_number: int,
    bot: Bot,
    sessionmaker: async_sessionmaker,
    state: FSMContext,
):
    """Обрабатывает ввод номера файла пользователем."""
    try:
        file_repo = FileRepository(sessionmaker)
        
        # Проверяем, находимся ли мы в режиме просмотра экспорта
        current_state = await state.get_state()
        if current_state == ExportStates.viewing_export:
            # Получаем файлы из state (подобранные для экспорта)
            data = await state.get_data()
            selected_file_ids = data.get("selected_files", [])
            
            if not selected_file_ids:
                await msg.answer(library_empty)
                await state.clear()
                return
            
            if file_number < 1 or file_number > len(selected_file_ids):
                await msg.answer(f"❌ Неверный номер. Введите число от 1 до {len(selected_file_ids)}")
                return
            
            # Получаем конкретный файл по ID
            file_id = selected_file_ids[file_number - 1]
            file = await file_repo.get_file(file_id)
            
            if not file:
                await msg.answer(file_not_found)
                return
            
            # Сохраняем запрос в базе
            request_repo = RequestRepository(sessionmaker)
            await request_repo.create_request(user_id, file.file_id)
        elif current_state == ExportStates.viewing_library:
            # Режим просмотра библиотеки с пагинацией
            data = await state.get_data()
            all_file_ids = data.get("all_file_ids", [])
            
            if not all_file_ids:
                await msg.answer(library_empty)
                await state.clear()
                return
            
            if file_number < 1 or file_number > len(all_file_ids):
                await msg.answer(f"❌ Неверный номер. Введите число от 1 до {len(all_file_ids)}")
                return
            
            # Получаем файл по ID (номер относительно всего списка)
            file_id = all_file_ids[file_number - 1]
            file = await file_repo.get_file(file_id)
            
            if not file:
                await msg.answer(file_not_found)
                return
            
            # Сохраняем запрос в базе
            request_repo = RequestRepository(sessionmaker)
            await request_repo.create_request(user_id, file.file_id)
        else:
            # Обычный режим - показываем файлы из всей библиотеки
            files = await file_repo.get_files_by_user(user_id)

            if not files:
                await msg.answer(library_empty)
                return

            if file_number < 1 or file_number > len(files):
                await msg.answer(f"❌ Неверный номер. Введите число от 1 до {len(files)}")
                return

            # Получаем файл по индексу (file_number - 1)
            file = files[file_number - 1]
            
            # Сохраняем запрос в базе
            request_repo = RequestRepository(sessionmaker)
            await request_repo.create_request(user_id, file.file_id)

        # Отправляем PDF файл
        await bot.send_document(
            msg.chat.id, file.telegram_file_id, caption=f"📄 {file.title}"
        )

        logger.info(
            f"Sent file {file.file_id} (number {file_number}) to user {user_id}"
        )

    except Exception as e:
        logger.error(f"Error sending file by number: {e}", exc_info=True)
        await msg.answer(f"❌ Ошибка при отправке файла: {str(e)}")


async def send_library_list(chat_id: int, user_id: int, sessionmaker: async_sessionmaker, state: FSMContext, page: int = 0, bot=None):
    """Отправляет новое сообщение со списком библиотеки."""
    file_repo = FileRepository(sessionmaker)
    files = await file_repo.get_files_by_user(user_id)
    
    if not files:
        await bot.send_message(chat_id, library_empty)
        await state.clear()
        return
    
    total_time = sum(float(f.reading_time_min) for f in files)
    header = library_header.format(count=len(files), total_time=total_time) + "\n"
    
    # Форматируем страницу
    response, total_pages = format_files_page(files, page, page_size=10, header=header)
    
    # Добавляем инструкцию и теги
    response += "\n" + library_instruction + "\n"
    
    selector = MaterialSelector(sessionmaker)
    available_tags = await selector.get_available_tags(user_id)
    
    if available_tags:
        response += library_tags_header.format(tags=", ".join(available_tags))
    
    # Создаем кнопки пагинации
    pagination_kb = create_pagination_keyboard(page, total_pages, prefix="lib_page")
    
    # Сохраняем все ID файлов и текущую страницу в state
    await state.update_data(all_file_ids=[f.file_id for f in files], current_page=page)
    await state.set_state(ExportStates.viewing_library)
    
    await bot.send_message(chat_id, response, disable_web_page_preview=True, reply_markup=pagination_kb)


async def send_export_list(chat_id: int, user_id: int, sessionmaker: async_sessionmaker, state: FSMContext, page: int = 0, bot=None):
    """Отправляет новое сообщение со списком подобранных материалов."""
    data = await state.get_data()
    selected_file_ids = data.get("selected_files", [])
    
    if not selected_file_ids:
        await bot.send_message(chat_id, export_no_files, reply_markup=main)
        await state.clear()
        return
    
    # Получаем файлы по ID
    file_repo = FileRepository(sessionmaker)
    files = []
    for file_id in selected_file_ids:
        file = await file_repo.get_file(file_id)
        if file:
            files.append(file)
    
    total_time = sum(float(f.reading_time_min) for f in files)
    header = export_header.format(count=len(files), total_time=total_time) + "\n"
    
    # Форматируем страницу
    response, total_pages = format_files_page(files, page, page_size=10, header=header)
    
    response += "\n" + library_instruction
    
    # Создаем кнопки пагинации
    pagination_kb = create_pagination_keyboard(page, total_pages, prefix="exp_page")
    
    # Обновляем страницу в state
    await state.update_data(current_page=page)
    
    await bot.send_message(chat_id, response, disable_web_page_preview=True, reply_markup=pagination_kb)


async def show_library_page(msg: Message, user_id: int, sessionmaker: async_sessionmaker, state: FSMContext, page: int = 0):
    """Показывает страницу библиотеки с пагинацией (редактирует существующее сообщение)."""
    file_repo = FileRepository(sessionmaker)
    files = await file_repo.get_files_by_user(user_id)
    
    if not files:
        await msg.edit_text(library_empty)
        await state.clear()
        return
    
    total_time = sum(float(f.reading_time_min) for f in files)
    header = library_header.format(count=len(files), total_time=total_time) + "\n"
    
    # Форматируем страницу
    response, total_pages = format_files_page(files, page, page_size=10, header=header)
    
    # Добавляем инструкцию и теги
    response += "\n" + library_instruction + "\n"
    
    selector = MaterialSelector(sessionmaker)
    available_tags = await selector.get_available_tags(user_id)
    
    if available_tags:
        response += library_tags_header.format(tags=", ".join(available_tags))
    
    # Создаем кнопки пагинации
    pagination_kb = create_pagination_keyboard(page, total_pages, prefix="lib_page")
    
    # Сохраняем все ID файлов и текущую страницу в state
    await state.update_data(all_file_ids=[f.file_id for f in files], current_page=page)
    await state.set_state(ExportStates.viewing_library)
    
    try:
        await msg.edit_text(response, disable_web_page_preview=True, reply_markup=pagination_kb)
    except:
        # Если не удалось отредактировать, отправляем новое сообщение
        await msg.answer(response, disable_web_page_preview=True, reply_markup=pagination_kb)


async def show_export_page(msg: Message, user_id: int, sessionmaker: async_sessionmaker, state: FSMContext, page: int = 0):
    """Показывает страницу подобранных материалов с пагинацией."""
    data = await state.get_data()
    selected_file_ids = data.get("selected_files", [])
    
    if not selected_file_ids:
        await msg.edit_text(export_no_files)
        await state.clear()
        return
    
    # Получаем файлы по ID
    file_repo = FileRepository(sessionmaker)
    files = []
    for file_id in selected_file_ids:
        file = await file_repo.get_file(file_id)
        if file:
            files.append(file)
    
    total_time = sum(float(f.reading_time_min) for f in files)
    header = export_header.format(count=len(files), total_time=total_time) + "\n"
    
    # Форматируем страницу
    response, total_pages = format_files_page(files, page, page_size=10, header=header)
    
    response += "\n" + library_instruction
    
    # Создаем кнопки пагинации
    pagination_kb = create_pagination_keyboard(page, total_pages, prefix="exp_page")
    
    # Обновляем страницу в state
    await state.update_data(current_page=page)
    
    try:
        await msg.edit_text(response, disable_web_page_preview=True, reply_markup=pagination_kb)
    except:
        # Если не удалось отредактировать, отправляем новое сообщение
        await msg.answer(response, disable_web_page_preview=True, reply_markup=pagination_kb)


async def show_library(msg: Message, user_id: int, sessionmaker: async_sessionmaker, state: FSMContext):
    """Показывает список файлов в библиотеке пользователя с пагинацией."""
    bot = msg.bot
    await send_library_list(msg.chat.id, user_id, sessionmaker, state, page=0, bot=bot)
    logger.info(f"Showed library for user {user_id}")


async def show_stats(msg: Message, user_id: int, sessionmaker: async_sessionmaker):
    """Показывает статистику библиотеки пользователя."""
    file_repo = FileRepository(sessionmaker)
    request_repo = RequestRepository(sessionmaker)

    files = await file_repo.get_files_by_user(user_id)
    requests = await request_repo.get_requests_by_user(user_id)

    if not files:
        await msg.answer(library_empty)
        return

    total_time = sum(float(f.reading_time_min) for f in files)
    hours = total_time / 60

    # Собираем уникальные теги
    all_tags = set()
    for file in files:
        if file.tags:
            all_tags.update(file.tags)

    response = stats_header + "\n"
    response += stats_total_files.format(count=len(files)) + "\n"
    response += stats_total_time.format(hours=hours, minutes=total_time) + "\n"
    response += stats_total_sent.format(count=len(requests)) + "\n"
    response += stats_tags.format(count=len(all_tags)) + "\n"

    if all_tags:
        response += f"\n🏷 Темы: {', '.join(sorted(all_tags))}"

    # Получаем последние запрошенные файлы
    recent_files = await request_repo.get_recent_requested_files(user_id, limit=5)
    
    if recent_files:
        response += stats_recent_header + "\n"
        for idx, file in enumerate(recent_files, 1):
            tags_str = ", ".join(file.tags[:2]) if file.tags else "Без тегов"
            if file.tags and len(file.tags) > 2:
                tags_str += f" +{len(file.tags) - 2}"
            
            title = file.title
            if len(title) > 50:
                title = title[:47] + "..."
            
            response += f"\n{idx}. 📄 {title}"
            response += f"\n   ⏱ {float(file.reading_time_min):.0f} мин • 🏷 {tags_str}"
        
        response += stats_instruction

    await msg.answer(response)

    logger.info(f"Showed stats for user {user_id}")
