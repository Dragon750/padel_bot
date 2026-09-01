from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Location
from bot.config import config

router = Router()

@router.message(Command("sugerir_ubicacion"), F.chat.type == "private")
async def cmd_sugerir(message: Message):
    """Inicia la sugerencia. Por simplicidad, pedimos formato directo."""
    await message.answer(
        "Para sugerir una pista, escribe el nombre y enlace de Maps así:\n\n"
        "`/nueva_pista Nombre del Club | URL de Google Maps`",
        parse_mode="Markdown"
    )

@router.message(Command("nueva_pista"))
async def process_new_location(message: Message, session: AsyncSession):
    """Procesa la sugerencia y avisa al admin"""
    try:
        _, data = message.text.split(" ", 1)
        name, url = data.split("|")
        
        # Guardar en estado "No aprobado"
        new_loc = Location(name=name.strip(), maps_url=url.strip(), is_approved=False, suggested_by=message.from_user.id)
        session.add(new_loc)
        await session.commit()
        
        await message.answer("✅ Ubicación enviada al administrador para su revisión.")
        
        # Enviar aviso al Admin
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Aprobar", callback_data=f"admin_approve_{new_loc.id}")],
            [InlineKeyboardButton(text="❌ Rechazar", callback_data=f"admin_reject_{new_loc.id}")]
        ])
        await message.bot.send_message(
            config.ADMIN_TELEGRAM_ID,
            f"🔔 **Nueva sugerencia de pista:**\nNombre: {new_loc.name}\nURL: {new_loc.maps_url}",
            reply_markup=kb
        )
    except ValueError:
        await message.answer("⛔ Formato incorrecto. Usa: `/nueva_pista Nombre | URL`")

@router.callback_query(F.data.startswith("admin_approve_"))
async def admin_approve(callback: CallbackQuery, session: AsyncSession):
    """Aprueba la pista"""
    loc_id = int(callback.data.split("_")[2])
    loc = await session.get(Location, loc_id)
    if loc:
        loc.is_approved = True
        await session.commit()
        await callback.message.edit_text(f"✅ Pista '{loc.name}' aprobada.")
    await callback.answer()