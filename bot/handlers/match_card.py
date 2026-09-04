import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.states.action_states import MatchActionFSM
from bot.database.models import MatchWaitlist, Match, MatchPlayer, Location, User
from bot.keyboards.inline import match_card_kb
from datetime import datetime, timedelta
from sqlalchemy import select, asc, func
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()
logger = logging.getLogger(__name__)

# ==========================================
# FUNCIÓN DIBUJANTE: Reconstruye la tarjeta
# ==========================================
async def render_match_card(match_id: int, session: AsyncSession) -> tuple[str, str | None, bool]:
    match = await session.get(Match, match_id)
    loc = await session.get(Location, match.location_id)
    
    stmt = (
        select(MatchPlayer, User)
        .join(User, MatchPlayer.user_id == User.telegram_id)
        .where(MatchPlayer.match_id == match_id)
        .order_by(asc(MatchPlayer.joined_at))
    )
    result = await session.execute(stmt)
    players_data = result.all()
    
    team_1, team_2 = [], []
    for mp, user in players_data:
        player_name = f"@{user.username}" if user.username else user.full_name
        
        if user.telegram_id == match.manager_id:
            player_name += " ⭐️"
            
        player_text = f"👤 {player_name} ({user.level:.1f})"
            
        if mp.team == 1:
            team_1.append(player_text)
        else:
            team_2.append(player_text)

    p1_slots = [team_1[i] if i < len(team_1) else "[Libre]" for i in range(2)]
    p2_slots = [team_2[i] if i < len(team_2) else "[Libre]" for i in range(2)]
    
    court_info = f"🟢 Pista reservada ({match.court_number})" if match.is_court_booked else "🟡 Pendiente de reserva comunitaria"
    
    text = (
        f"🎾 <b>CONVOCATORIA PÁDEL #{match.id}</b>\n\n"
        f"📍 <b>Lugar:</b> {loc.name}\n"
        f"📅 <b>Fecha:</b> {match.datetime.strftime('%d/%m/%Y %H:%M')}\n"
        f"📊 <b>Nivel:</b> {match.min_level:.1f} - {match.max_level:.1f}\n"
        f"📌 <b>Estado:</b> {court_info}\n\n"
        f"👥 <b>Pareja 1:</b>\n"
        f"  1. {p1_slots[0]}\n"
        f"  2. {p1_slots[1]}\n\n"
        f"👥 <b>Pareja 2:</b>\n"
        f"  1. {p2_slots[0]}\n"
        f"  2. {p2_slots[1]}\n"
    )
    
    return text, loc.maps_url, match.is_court_booked

# ==========================================
# ACCIONES DE LOS BOTONES
# ==========================================

@router.callback_query(F.data.startswith("join_"))
async def handle_join(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Permite a un usuario ocupar un hueco validando nivel y plazas libres."""
    _, str_match_id, str_team = callback.data.split("_")
    match_id, team = int(str_match_id), int(str_team)
    user_id = callback.from_user.id
    
    match = await session.get(Match, match_id)
    if match.status not in ["OPEN", "FULL"]:
        await callback.answer("❌ Este partido ya no admite inscripciones.", show_alert=True)
        return

    # --- NUEVA VALIDACIÓN DE NIVEL ---
    user = await session.get(User, user_id)
    if not (match.min_level <= user.level <= match.max_level):
        await callback.answer(
            f"⛔ Tu nivel ({user.level:.1f}) está fuera del rango permitido ({match.min_level:.1f} - {match.max_level:.1f}).", 
            show_alert=True
        )
        return
    # ---------------------------------

    stmt_exist = select(MatchPlayer).where(MatchPlayer.match_id == match_id, MatchPlayer.user_id == user_id)
    if await session.scalar(stmt_exist):
        await callback.answer("⚠️ Ya estás inscrito en este partido.", show_alert=True)
        return

    stmt_count = select(MatchPlayer).where(MatchPlayer.match_id == match_id, MatchPlayer.team == team)
    team_players = (await session.scalars(stmt_count)).all()
    
    if len(team_players) >= 2:
        await callback.answer("❌ Esa pareja ya está llena. Intenta en la otra.", show_alert=True)
        return

    new_player = MatchPlayer(match_id=match_id, user_id=user_id, team=team)
    session.add(new_player)
    
    stmt_total = select(MatchPlayer).where(MatchPlayer.match_id == match_id)
    total_players = len((await session.scalars(stmt_total)).all()) + 1 
    
    if total_players == 4:
        match.status = "FULL"
        
    await session.commit()
    
    text, maps_url, is_booked = await render_match_card(match_id, session)
    await callback.message.edit_text(text, reply_markup=match_card_kb(match_id, is_booked, maps_url))
    await callback.answer("✅ ¡Te has unido al partido!")


@router.callback_query(F.data.startswith("swap_"))
async def handle_swap(callback: CallbackQuery, session: AsyncSession):
    """Permite cambiar de Pareja 1 a Pareja 2 y viceversa si hay hueco."""
    match_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    # Buscar al jugador
    stmt_player = select(MatchPlayer).where(MatchPlayer.match_id == match_id, MatchPlayer.user_id == user_id)
    player = await session.scalar(stmt_player)
    
    if not player:
        await callback.answer("❌ No estás inscrito en este partido.", show_alert=True)
        return
        
    target_team = 2 if player.team == 1 else 1
    
    # Comprobar hueco en el otro equipo
    stmt_count = select(MatchPlayer).where(MatchPlayer.match_id == match_id, MatchPlayer.team == target_team)
    if len((await session.scalars(stmt_count)).all()) >= 2:
        await callback.answer(f"❌ La Pareja {target_team} ya está llena.", show_alert=True)
        return
        
    player.team = target_team
    await session.commit()
    
    text, maps_url, is_booked = await render_match_card(match_id, session)
    await callback.message.edit_text(text, reply_markup=match_card_kb(match_id, is_booked, maps_url))
    await callback.answer("🔄 ¡Has cambiado de pareja!")


@router.callback_query(F.data.startswith("leave_"))
async def handle_leave(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Saca al jugador del partido, aplica penalizaciones y gestiona relevos."""
    match_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    stmt_player = select(MatchPlayer).where(MatchPlayer.match_id == match_id, MatchPlayer.user_id == user_id)
    player = await session.scalar(stmt_player)
    
    if not player:
        await callback.answer("❌ No estás inscrito en este partido.", show_alert=True)
        return
        
    match = await session.get(Match, match_id)
    
    # --- NUEVA PENALIZACIÓN POR BAJA TARDÍA ---
    time_diff = match.datetime - datetime.now()
    if time_diff < timedelta(hours=2):
        user = await session.get(User, user_id)
        user.late_cancellations += 1
        await callback.answer("⚠️ Baja tardía (menos de 2h). Se ha sumado una penalización a tu perfil.", show_alert=True)
    else:
        await callback.answer("👋 Te has salido del partido correctamente.")
    # ------------------------------------------
    
    # ¿Era el organizador? Traspasamos el liderazgo o eliminamos la convocatoria
    match_deleted = False
    if match.manager_id == user_id:
        stmt_oldest = select(MatchPlayer).where(MatchPlayer.match_id == match_id).order_by(asc(MatchPlayer.joined_at)).limit(1)
        oldest_player = await session.scalar(stmt_oldest)
        
        if oldest_player:
            match.manager_id = oldest_player.user_id
            try:
                await bot.send_message(
                    oldest_player.user_id,
                    f"👑 <b>ERES EL NUEVO ORGANIZADOR</b>\n"
                    f"El creador del partido #{match.id} se ha dado de baja. Ahora eres el responsable."
                )
            except Exception:
                pass
        else:
            # Si no queda ningún jugador, eliminamos completamente el partido de PostgreSQL
            await session.delete(match)
            match_deleted = True
            
    await session.commit()
    
    if match_deleted:
        await callback.message.edit_text(f"❌ Convocatoria #{match_id} cancelada y retirada (todos los jugadores se dieron de baja).")
    else:
        text, maps_url, is_booked = await render_match_card(match_id, session)
        await callback.message.edit_text(text, reply_markup=match_card_kb(match_id, is_booked, maps_url))
        await notify_waitlist(match_id, session, bot)

@router.callback_query(F.data.startswith("cancel_club_"))
async def handle_cancel_by_club(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Cancela el partido por motivos del club (se conserva en BD para estadísticas)"""
    match_id = int(callback.data.split("_")[2])
    match = await session.get(Match, match_id)
    
    if not match:
        await callback.answer("El partido no existe o ya fue eliminado.", show_alert=True)
        return

    # Solo el gestor o quien reservó puede anular por causa de club
    if callback.from_user.id not in [match.manager_id, match.booked_by]:
        await callback.answer("⛔ Solo el organizador o el titular de la reserva puede anular la convocatoria.", show_alert=True)
        return

    # Marcamos como cancelado conservando el registro
    match.status = "CANCELLED"
    # Si tu modelo tiene la columna cancellation_reason:
    if hasattr(match, "cancellation_reason"):
        match.cancellation_reason = "CLUB_CANCELLED"
        
    await session.commit()

    # Actualizar la tarjeta pública en el grupo
    await callback.message.edit_text(
        f"<b>CONVOCATORIA #{match_id} ANULADA POR EL CLUB</b>\n\n"
        f"La pista no está disponible por motivos del club o meteorología. "
        f"Este partido no penaliza a ningún participante."
    )
    await callback.answer("Convocatoria cancelada por motivos del club.")


# ==========================================
# RESERVA COLABORATIVA (CUALQUIER JUGADOR)
# ==========================================
@router.callback_query(F.data.startswith("ihavecourt_"))
async def handle_i_have_court(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Activa el modo de escucha para que un jugador indique la pista reservada."""
    match_id = int(callback.data.split("_")[1])
    
    # Verificamos si otro jugador se adelantó
    match = await session.get(Match, match_id)
    if match.is_court_booked:
        await callback.answer("✅ La pista ya ha sido confirmada por otro jugador.", show_alert=True)
        return
        
    await state.update_data(collab_match_id=match_id)
    await state.update_data(origin_chat_id=callback.message.chat.id)
    await state.update_data(origin_msg_id=callback.message.message_id)
    
    await state.set_state(MatchActionFSM.waiting_for_collab_court)
    
    msg = await callback.message.answer(
        f"🎾 <b>Reserva Colaborativa (Partido #{match_id})</b>\n\n"
        "Escribe en este chat el <b>número o nombre de la pista</b> que has reservado (ej. <i>Pista 3</i>):"
    )
    await state.update_data(prompt_msg_id=msg.message_id)
    await callback.answer()


@router.message(MatchActionFSM.waiting_for_collab_court)
async def process_collab_court(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Consume el número de pista, actualiza la tarjeta y notifica al resto."""
    try:
        await message.delete() # Borramos el texto del usuario para no ensuciar el grupo
    except Exception:
        pass
        
    data = await state.get_data()
    match_id = data["collab_match_id"]
    court_number = message.text.strip()
    
    # 1. Actualizamos la base de datos
    match = await session.get(Match, match_id)
    match.is_court_booked = True
    match.court_number = court_number
    match.booked_by = message.from_user.id
    
    # Obtenemos los otros jugadores para notificarles
    stmt_others = select(MatchPlayer.user_id).where(
        MatchPlayer.match_id == match_id,
        MatchPlayer.user_id != message.from_user.id,
        MatchPlayer.user_id.is_not(None)
    )
    other_players = (await session.scalars(stmt_others)).all()
    
    await session.commit()
    
    # 2. Actualizamos la tarjeta interactiva original
    text, maps_url, is_booked = await render_match_card(match_id, session)
    try:
        await bot.edit_message_text(
            chat_id=data["origin_chat_id"],
            message_id=data["origin_msg_id"],
            text=text,
            reply_markup=match_card_kb(match_id, is_booked, maps_url)
        )
        # Borramos el mensaje donde le pedíamos la pista
        await bot.delete_message(chat_id=message.chat.id, message_id=data["prompt_msg_id"])
    except Exception:
        pass
        
    await state.clear()
    
    # 3. Notificaciones cruzadas por privado
    for user_id in other_players:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"✅ <b>PISTA CONFIRMADA</b>\n\n"
                     f"@{message.from_user.username or message.from_user.first_name} ha confirmado la reserva física para el partido #{match_id}.\n"
                     f"📍 <b>Pista asignada:</b> {court_number}"
            )
        except Exception:
            pass


# ==========================================
# LISTA DE ESPERA
# ==========================================
@router.callback_query(F.data.startswith("waitlist_"))
async def handle_waitlist(callback: CallbackQuery, session: AsyncSession):
    """Permite apuntarse a la cola de sustituciones."""
    match_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    # 1. ¿Ya está jugando?
    stmt_playing = select(MatchPlayer).where(MatchPlayer.match_id == match_id, MatchPlayer.user_id == user_id)
    if await session.scalar(stmt_playing):
        await callback.answer("⚠️ Ya estás inscrito en este partido. No puedes estar en lista de espera.", show_alert=True)
        return
        
    # 2. ¿Ya está en la lista de espera?
    stmt_waiting = select(MatchWaitlist).where(MatchWaitlist.match_id == match_id, MatchWaitlist.user_id == user_id)
    if await session.scalar(stmt_waiting):
        await callback.answer("✅ Ya estabas en la lista de espera de este partido.", show_alert=True)
        return
        
    # 3. Lo añadimos a la cola
    new_waitlist = MatchWaitlist(match_id=match_id, user_id=user_id)
    session.add(new_waitlist)
    await session.commit()
    
    await callback.answer("⏳ Te has apuntado a la lista de espera. Te avisaremos automáticamente si queda un hueco libre.", show_alert=True)

async def notify_waitlist(match_id: int, session: AsyncSession, bot: Bot):
    """Lanza la alerta push a todos los usuarios en lista de espera."""
    stmt = select(MatchWaitlist).where(MatchWaitlist.match_id == match_id)
    waitlist_users = (await session.scalars(stmt)).all()
    
    if not waitlist_users:
        return
        
    match = await session.get(Match, match_id)
    loc = await session.get(Location, match.location_id)
    match_time = match.datetime.strftime('%d/%m/%Y %H:%M')
    
    # Botón mágico para capturar la plaza desde el chat privado
    builder = InlineKeyboardBuilder()
    builder.button(text="⚡ Ocupar Plaza Libre", callback_data=f"takeslot_{match_id}")
    kb = builder.as_markup()
    
    for wl in waitlist_users:
        try:
            await bot.send_message(
                chat_id=wl.user_id,
                text=f"🚨 <b>¡PLAZA LIBRE DISPONIBLE!</b>\n\n"
                     f"Se ha liberado un hueco para el partido en {loc.name} el {match_time}.\n\n"
                     f"🏃‍♂️ <i>El primero en pulsar el botón se queda la plaza.</i>",
                reply_markup=kb
            )
        except Exception:
            pass # Ignorar si el usuario ha bloqueado al bot


@router.callback_query(F.data.startswith("takeslot_"))
async def handle_take_slot(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Gestiona la concurrencia: el primero que llega, se lo queda."""
    match_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    match = await session.get(Match, match_id)
    
    if match.status not in ["OPEN"]:
        await callback.message.edit_text("❌ Llegaste tarde, la plaza ya ha sido ocupada.")
        return
        
    # Doble validación atómica: Contamos jugadores reales
    stmt_count = select(func.count()).select_from(MatchPlayer).where(MatchPlayer.match_id == match_id)
    players_count = await session.scalar(stmt_count)
    
    if players_count >= 4:
        match.status = "FULL"
        await session.commit()
        await callback.message.edit_text("❌ Llegaste tarde, la plaza ya ha sido ocupada por otro jugador.")
        return
        
    # Comprobar en qué equipo hay hueco
    stmt_t1 = select(func.count()).select_from(MatchPlayer).where(MatchPlayer.match_id == match_id, MatchPlayer.team == 1)
    t1_count = await session.scalar(stmt_t1)
    team_to_join = 1 if t1_count < 2 else 2
    
    # ¡Adjudicado!
    new_player = MatchPlayer(match_id=match_id, user_id=user_id, team=team_to_join)
    session.add(new_player)
    
    # Lo borramos de la lista de espera
    stmt_wl = select(MatchWaitlist).where(MatchWaitlist.match_id == match_id, MatchWaitlist.user_id == user_id)
    wl_entry = await session.scalar(stmt_wl)
    if wl_entry:
        await session.delete(wl_entry)
        
    if players_count + 1 == 4:
        match.status = "FULL"
        
    await session.commit()
    
    # 1. Editamos el mensaje privado de éxito
    await callback.message.edit_text("✅ <b>¡Enhorabuena!</b> Has sido el más rápido y has ocupado la plaza libre.")
    
    # 2. Actualizamos la tarjeta grupal
    if match.chat_id and match.message_id:
        text, maps_url, is_booked = await render_match_card(match_id, session)
        try:
            await bot.edit_message_text(
                chat_id=match.chat_id,
                message_id=match.message_id,
                text=text,
                reply_markup=match_card_kb(match_id, is_booked, maps_url)
            )
        except Exception:
            pass