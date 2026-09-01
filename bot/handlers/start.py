from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.database.models import User

router = Router()

def build_level_keyboard() -> InlineKeyboardMarkup:
    """Genera un teclado para seleccionar el nivel inicial (0.0 a 6.0)"""
    builder = InlineKeyboardBuilder()
    levels = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
    for lvl in levels:
        builder.button(text=f"Nivel {lvl}", callback_data=f"setlevel_{lvl}")
    builder.adjust(3)
    return builder.as_markup()

@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    """Comprueba si el usuario existe o le pide el nivel inicial"""
    user_id = message.from_user.id
    stmt = select(User).where(User.telegram_id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        await message.answer(f"¡Hola de nuevo, {user.full_name}! Tu nivel actual es {user.level} 🎾.")
    else:
        await message.answer(
            "👋 ¡Bienvenido al Gestor de Pádel!\n\n"
            "Para empezar, selecciona tu nivel orientativo (0.0 a 6.0). "
            "Este nivel se ajustará automáticamente según tus resultados:",
            reply_markup=build_level_keyboard()
        )

@router.callback_query(F.data.startswith("setlevel_"))
async def process_initial_level(callback: CallbackQuery, session: AsyncSession):
    """Guarda el nuevo usuario en Supabase con el nivel seleccionado"""
    level = float(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    new_user = User(
        telegram_id=user_id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
        level=level
    )
    session.add(new_user)
    await session.commit()
    
    await callback.message.edit_text(f"✅ ¡Perfil creado con éxito!\nNivel inicial fijado en: **{level}**")
    await callback.answer()