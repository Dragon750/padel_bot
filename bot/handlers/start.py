from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User

router = Router()

def build_initial_level_keyboard():
    """Genera botones desde 0.0 hasta 6.0 en saltos de 0.5."""
    builder = InlineKeyboardBuilder()
    levels = [round(x * 0.5, 1) for x in range(13)]  # [0.0, 0.5, 1.0, ..., 6.0]
    
    for lvl in levels:
        builder.button(text=f"{lvl:.1f}", callback_data=f"setlevel_{lvl:.1f}")
        
    builder.adjust(4)  # 4 botones por fila
    return builder.as_markup()

@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    
    if user:
        await message.answer(
            f"👋 ¡Hola de nuevo, <b>{user.full_name}</b>!\n\n"
            f"📊 <b>Tu nivel actual:</b> {user.level:.2f}\n"
            f"🎾 <b>Partidos jugados:</b> {user.matches_played}\n"
            f"⚠️ <b>Cancelaciones tardías:</b> {user.late_cancellations}\n\n"
            f"Usa /crear para convocar un partido público o /crear_privado para registrar uno cerrado."
        )
        return

    await message.answer(
        f"👋 ¡Bienvenido al Bot de Pádel, <b>{message.from_user.full_name}</b>!\n\n"
        "Para poder inscribirte y organizar partidos, selecciona tu <b>nivel inicial orientativo</b> (escala 0.0 a 6.0):",
        reply_markup=build_initial_level_keyboard()
    )

@router.callback_query(F.data.startswith("setlevel_"))
async def process_initial_level(callback: CallbackQuery, session: AsyncSession):
    level_val = float(callback.data.split("_")[1])
    
    user = await session.get(User, callback.from_user.id)
    if not user:
        user = User(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
            level=level_val
        )
        session.add(user)
    else:
        user.level = level_val

    await session.commit()
    await callback.message.edit_text(
        f"✅ ¡Perfil completado!\n\n"
        f"Tu nivel inicial ha sido fijado en <b>{level_val:.1f}</b>.\n\n"
        f"Ya puedes usar /crear para organizar convocatorias en tus grupos."
    )
    await callback.answer()