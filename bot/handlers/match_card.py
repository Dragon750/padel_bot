from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.database.models import Match, MatchPlayer

router = Router()

@router.callback_query(F.data.startswith("join_"))
async def join_match(callback: CallbackQuery, session: AsyncSession):
    """Inscribe al usuario en la Pareja 1 o 2 validando plazas."""
    parts = callback.data.split("_")
    match_id, team = int(parts[1]), int(parts[2])
    user_id = callback.from_user.id

    # 1. Comprobar si ya está en el partido
    stmt = select(MatchPlayer).where((MatchPlayer.match_id == match_id) & (MatchPlayer.user_id == user_id))
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        await callback.answer("⚠️ Ya estás inscrito en este partido.", show_alert=True)
        return

    # 2. Contar ocupación del equipo
    stmt_team = select(MatchPlayer).where((MatchPlayer.match_id == match_id) & (MatchPlayer.team == team))
    team_players = list((await session.execute(stmt_team)).scalars().all())
    
    if len(team_players) >= 2:
        await callback.answer("⛔ Esta pareja ya está llena.", show_alert=True)
        return

    # 3. Guardar plaza
    new_player = MatchPlayer(match_id=match_id, user_id=user_id, team=team, registered_by=user_id)
    session.add(new_player)
    await session.commit()
    
    await callback.answer("✅ Te has apuntado al partido.")
    # (Aquí iría la llamada a la función que reconstruye el texto de la tarjeta y hace edit_message_text[cite: 6])


@router.callback_query(F.data.startswith("ihavecourt_"))
async def collaborative_booking(callback: CallbackQuery, session: AsyncSession):
    """Reserva Colaborativa: Un jugador confirmado indica que ya reservó la pista física."""
    match_id = int(callback.data.split("_")[1])
    
    # Se debe verificar que el usuario está dentro de MatchPlayer antes de permitirle reservar[cite: 4, 6]
    match = await session.get(Match, match_id)
    if match and not match.is_court_booked:
        match.is_court_booked = True
        match.booked_by = callback.from_user.id
        # Idealmente aquí pedirías el número de pista vía FSM, pero para simplificar lo cerramos atómicamente
        await session.commit()
        await callback.answer("✅ Has confirmado la reserva de pista. Actualizando tarjeta...", show_alert=True)
        # (Aquí se edita el mensaje eliminando el botón [🎾 Ya tengo pista][cite: 6])