import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Document, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from project.keyboards.main_keyboards import main
from project.text.main_text import greet

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("start"))
async def start_handler(msg: Message, sessionmaker: async_sessionmaker):
    sender = msg.from_user
    if sender is None:
        await msg.answer(greet.format(name="Гость"), reply_markup=main)
        return

    user_repo = UserRepository(sessionmaker)
    await user_repo.create_or_update_user(sender.id, sender.full_name)

    await msg.answer(greet.format(name=sender.full_name), reply_markup=main)


@router.message()
async def pdf_handler(msg: Message, sessionmaker: async_sessionmaker):
    sender = msg.from_user
    if sender is None:
        await msg.answer("Не удалось определить отправителя.")
        return
    
    
    if msg.document:
        document: Document = msg.document

        if not document.mime_type or not document.mime_type.startswith(
            "application/pdf"
        ):
            await msg.answer("Пожалуйста, отправьте PDF файл.")
            return
        
        pass
        
        await msg.answer(f"PDF файл '{document.file_name}' получен и обработан!")

    elif msg.text:
        text = msg.text.strip()
        
        pass
