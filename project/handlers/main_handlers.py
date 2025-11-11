import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, Document
from sqlalchemy.ext.asyncio import async_sessionmaker

from project.database.pdf_repository import PDFRepository
from project.database.user_repository import UserRepository
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
    
    pdf_repo = PDFRepository(sessionmaker)
    
    if msg.document:
        document: Document = msg.document
        
        if not document.mime_type or not document.mime_type.startswith('application/pdf'):
            await msg.answer("Пожалуйста, отправьте PDF файл.")
            return
        
        await pdf_repo.log_pdf_upload(
            user_id=sender.id,
            filename=document.file_name or "unknown.pdf",
            file_id=document.file_id,
            file_size=document.file_size or 0
        )
        
        await msg.answer(f"PDF файл '{document.file_name}' получен и обработан!")
        
    elif msg.text:
        text = msg.text.strip()
        
        if text.startswith(('http://', 'https://')):
            await pdf_repo.log_pdf_url(
                user_id=sender.id,
                url=text
            )
            await msg.answer(f"URL получен и обработан: {text}")
        else:
            await msg.answer("Пожалуйста, отправьте PDF файл или URL ссылку.")
