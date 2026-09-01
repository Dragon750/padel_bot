from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Match

router = Router()

@router.message(Command("marcador"))
async def enter_score(message: Message, session: AsyncSession):
    """Comando exclusivo para el manager_id para introducir el resultado[cite: 5]"""
    # Ejemplo de uso: /marcador [match_id] 6-4 6-3
    try:
        parts = message.text.split(" ", 2)
        match_id = int(parts[1])
        score = parts[2]
        
        match = await session.get(Match, match_id)
        if match.manager_id != message.from_user.id:
            await message.answer("⛔ Solo el gestor del partido puede subir el resultado.")
            return
            
        match.result = score
        match.status = "VALIDATING"
        await session.commit()
        
        await message.answer("✅ Marcador guardado. Enviando confirmación al resto de jugadores...")
        
        # (Aquí se notificaría al equipo rival por privado con el teclado de [👍 Confirmar] / [⚠️ Disputar][cite: 3, 5])
        
    except (IndexError, ValueError):
        await message.answer("⛔ Formato incorrecto. Uso: `/marcador ID_PARTIDO 6-4 6-4`", parse_mode="Markdown")

@router.callback_query(F.data.startswith("consensus_ok_"))
async def consensus_approve(callback: CallbackQuery, session: AsyncSession):
    """El equipo rival aprueba el acta[cite: 5]"""
    match_id = int(callback.data.split("_")[2])
    match = await session.get(Match, match_id)
    match.status = "PLAYED"
    await session.commit()
    
    await callback.message.edit_text("✅ Has confirmado el marcador. ¡Niveles actualizados!")
    # (Llamada al servicio calculate_new_levels())