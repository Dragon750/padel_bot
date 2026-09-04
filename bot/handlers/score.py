import re
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Match, MatchPlayer, User
from bot.services.rating import update_team_ratings

router = Router()

def build_consensus_kb(match_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="👍 Confirmar", callback_data=f"score_ok_{match_id}")
    builder.button(text="⚠️ Disputar", callback_data=f"score_ko_{match_id}")
    builder.adjust(2)
    return builder.as_markup()

@router.message(Command("marcador"), F.chat.type == "private")
async def cmd_report_score(message: Message, session: AsyncSession, bot: Bot):
    """Permite al gestor introducir el resultado: /marcador <id> <set1> <set2> [set3]"""
    pattern = r"^/marcador\s+(\d+)\s+([0-7]-[0-7](?:\s+[0-7]-[0-7]){1,2})$"
    match_regex = re.match(pattern, message.text.strip())

    if not match_regex:
        await message.answer("⚠️ <b>Formato incorrecto.</b>\nUsa: <code>/marcador &lt;id&gt; &lt;s1&gt; &lt;s2&gt; [s3]</code>")
        return

    match_id = int(match_regex.group(1))
    score_str = match_regex.group(2)

    match = await session.get(Match, match_id)
    if not match:
        await message.answer("❌ El partido indicado no existe.")
        return

    if match.manager_id != message.from_user.id:
        await message.answer("⛔ Solo el gestor de la convocatoria puede introducir el marcador.")
        return

    if match.status not in ["FULL", "OPEN"]:
        await message.answer(f"⚠️ Este partido ya se encuentra en estado <b>{match.status}</b>.")
        return

    # Validación de empates lógicos
    t1_sets, t2_sets = 0, 0
    for s in score_str.split():
        g1, g2 = map(int, s.split("-"))
        if g1 > g2: t1_sets += 1
        elif g2 > g1: t2_sets += 1

    if t1_sets == t2_sets:
        await message.answer("❌ El resultado no puede terminar en empate de sets.")
        return

    # 1. Guardar el acta temporal en la base de datos y cambiar estado
    match.result_p1 = score_str
    match.status = "VALIDATING"

    # 2. Resetear las confirmaciones de todos los jugadores a False
    stmt_players = select(MatchPlayer).where(MatchPlayer.match_id == match_id)
    players = (await session.scalars(stmt_players)).all()
    for p in players:
        p.has_confirmed_result = False
        
    await session.commit()
    await message.answer(f"✅ Acta registrada: <b>{score_str}</b>.\nEnviando solicitud a los otros jugadores...")

    # 3. Notificar a los rivales
    for p in players:
        if p.user_id != message.from_user.id:
            try:
                await bot.send_message(
                    chat_id=p.user_id,
                    text=f"🎾 <b>VALIDACIÓN (Partido #{match_id})</b>\n\nMarcador: <b>{score_str}</b>\n¿Estás conforme?",
                    reply_markup=build_consensus_kb(match_id)
                )
            except Exception:
                pass

@router.callback_query(F.data.startswith("score_ok_"))
async def handle_confirm_score(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    match_id = int(callback.data.split("_")[2])
    uid = callback.from_user.id

    match = await session.get(Match, match_id)
    if not match or match.status != "VALIDATING":
        await callback.answer("Este partido ya no está pendiente de validación.", show_alert=True)
        return

    stmt_player = select(MatchPlayer).where(MatchPlayer.match_id == match_id, MatchPlayer.user_id == uid)
    player = await session.scalar(stmt_player)

    if player.has_confirmed_result:
        await callback.answer("Ya habías confirmado este resultado.", show_alert=True)
        return

    # Marcar confirmación en DB persistente
    player.has_confirmed_result = True
    await session.commit()
    await callback.message.edit_text(f"✅ Has confirmado el resultado ({match.result_p1}). ¡Gracias!")

    # Contar total de confirmaciones
    stmt_count = select(func.count()).select_from(MatchPlayer).where(MatchPlayer.match_id == match_id, MatchPlayer.has_confirmed_result == True)
    confirmations = await session.scalar(stmt_count)

    if confirmations >= 2:
        await finalize_match_closure(match_id, session, bot)

@router.callback_query(F.data.startswith("score_ko_"))
async def handle_dispute_score(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    match_id = int(callback.data.split("_")[2])
    
    match = await session.get(Match, match_id)
    if match and match.status == "VALIDATING":
        # Devolver a FULL para que el manager vuelva a enviar el marcador
        match.status = "FULL"
        match.result_p1 = None
        await session.commit()
        
        await callback.message.edit_text("⚠️ Has disputado el resultado. El gestor deberá revisar el acta.")
        try:
            await bot.send_message(
                chat_id=match.manager_id,
                text=f"⚠️ <b>MARCADOR DISPUTADO</b>\n\nUn jugador ha rechazado el resultado del partido #{match_id}. Reenvía el correcto con <code>/marcador</code>."
            )
        except Exception:
            pass

async def finalize_match_closure(match_id: int, session: AsyncSession, bot: Bot):
    """Aplica el resultado leyendo desde la BD, actualiza ratings y cierra el partido."""
    match = await session.get(Match, match_id)
    if not match or match.status == "PLAYED":
        return

    score_str = match.result_p1
    t1_sets, t2_sets = 0, 0
    for s in score_str.split():
        g1, g2 = map(int, s.split("-"))
        if g1 > g2: t1_sets += 1
        elif g2 > g1: t2_sets += 1

    stmt = select(MatchPlayer, User).join(User, MatchPlayer.user_id == User.telegram_id).where(MatchPlayer.match_id == match_id)
    players_data = (await session.execute(stmt)).all()

    t1, t2 = [], []
    for mp, u in players_data:
        info = (u.telegram_id, u.level, u.matches_played)
        if mp.team == 1: t1.append(info)
        else: t2.append(info)

    updated_ratings = update_team_ratings(t1, t2, t1_sets, t2_sets)

    summary = []
    for mp, u in players_data:
        old_lvl = u.level
        new_lvl = updated_ratings.get(u.telegram_id, old_lvl)
        u.level = new_lvl
        u.matches_played += 1
        summary.append(f"• {u.full_name}: {old_lvl:.2f} ➔ <b>{new_lvl:.2f}</b>")

    match.status = "PLAYED"
    await session.commit()

    report_text = f"🏆 <b>PARTIDO #{match_id} CERRADO</b>\n\nResultado final: <b>{score_str}</b>\n\n<b>Actualización de Niveles:</b>\n" + "\n".join(summary)

    for mp, u in players_data:
        try:
            await bot.send_message(chat_id=u.telegram_id, text=report_text)
        except Exception:
            pass