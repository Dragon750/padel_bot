from datetime import datetime, timedelta, date, time
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.private_match_states import PrivateMatchFSM
from bot.database.models import User, Match, MatchPlayer
from bot.keyboards.inline import score_consensus_kb

router = Router()

# ==========================================
# 1. TECLADOS ESPECÍFICOS PARA PARTIDOS PRIVADOS
# ==========================================
def build_private_dates_keyboard() -> InlineKeyboardMarkup:
    """Genera fechas desde AYER (-1 día) hasta +5 días vista."""
    builder = InlineKeyboardBuilder()
    today = datetime.now().date()
    
    for i in range(-1, 6):
        date_obj = today + timedelta(days=i)
        if i == -1:
            label = "Ayer"
        elif i == 0:
            label = "Hoy"
        elif i == 1:
            label = "Mañana"
        else:
            dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            label = f"{dias[date_obj.weekday()]} {date_obj.day}"
            
        builder.button(text=label, callback_data=f"privdate_{date_obj.strftime('%Y-%m-%d')}")
        
    builder.adjust(2)
    return builder.as_markup()

def build_private_hours_keyboard() -> InlineKeyboardMarkup:
    """Genera horas completas sin filtrar (permite horas pasadas para registrar actas)."""
    builder = InlineKeyboardBuilder()
    for h in range(7, 23):
        builder.button(text=f"{h:02d}h", callback_data=f"privhour_{h}")
    builder.adjust(4)
    return builder.as_markup()

def build_private_minutes_keyboard(hour: int) -> InlineKeyboardMarkup:
    """Genera minutos sin filtrar."""
    builder = InlineKeyboardBuilder()
    for m in [0, 15, 30, 45]:
        time_str = f"{hour:02d}:{m:02d}"
        builder.button(text=time_str, callback_data=f"privtime_{time_str}")
    builder.adjust(2)
    return builder.as_markup()

def build_private_summary_keyboard() -> InlineKeyboardMarkup:
    """Botonera de confirmación final para el partido privado."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Confirmar y Registrar", callback_data="confirm_private_match")
    builder.button(text="❌ Cancelar Creación", callback_data="cancel_private_match")
    builder.adjust(1)
    return builder.as_markup()

# ==========================================
# 2. FUNCIONES AUXILIARES
# ==========================================
async def resolve_player(text: str, session: AsyncSession) -> User | None:
    """Busca al usuario por @username en la base de datos. Solo admite usuarios registrados."""
    text = text.strip()
    if not text.startswith("@"):
        return None
    username = text[1:].strip()
    stmt = select(User).where(User.username.ilike(username))
    return (await session.execute(stmt)).scalar_one_or_none()


# ==========================================
# 3. INICIO DEL ASISTENTE PRIVADO
# ==========================================
@router.message(Command("crear_privado"), F.chat.type == "private")
async def cmd_crear_privado(message: Message, state: FSMContext):
    """Inicia el registro de un partido cerrado."""
    await state.clear()
    await state.set_state(PrivateMatchFSM.waiting_for_date)
    await message.answer(
        "🤫 <b>NUEVO PARTIDO PRIVADO</b>\n\n"
        "Este partido no se publicará en los grupos. Sirve para actualizar estadísticas y nivel.\n"
        "📅 <b>¿Qué día se jugó o se va a jugar?</b>",
        reply_markup=build_private_dates_keyboard()
    )

# ==========================================
# 4. FECHA, HORA Y MINUTOS
# ==========================================
@router.callback_query(PrivateMatchFSM.waiting_for_date, F.data.startswith("privdate_"))
async def process_private_date(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split("_")[1]
    selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    await state.update_data(date=selected_date)
    await state.set_state(PrivateMatchFSM.waiting_for_hour)
    
    await callback.message.edit_text("⏰ Selecciona la hora:", reply_markup=build_private_hours_keyboard())
    await callback.answer()

@router.callback_query(PrivateMatchFSM.waiting_for_hour, F.data.startswith("privhour_"))
async def process_private_hour(callback: CallbackQuery, state: FSMContext):
    hour = int(callback.data.split("_")[1])
    await state.update_data(hour=hour)
    await state.set_state(PrivateMatchFSM.waiting_for_minute)
    
    await callback.message.edit_text(f"⏰ {hour:02d}h... ¿y los minutos?", reply_markup=build_private_minutes_keyboard(hour))
    await callback.answer()

@router.callback_query(PrivateMatchFSM.waiting_for_minute, F.data.startswith("privtime_"))
async def process_private_minute(callback: CallbackQuery, state: FSMContext):
    time_str = callback.data.split("_")[1]
    data = await state.get_data()
    
    selected_date = data["date"]
    time_obj = datetime.strptime(time_str, "%H:%M").time()
    final_datetime = datetime.combine(selected_date, time_obj)
    
    await state.update_data(datetime=final_datetime)
    await state.set_state(PrivateMatchFSM.waiting_for_p1_partner)
    
    await callback.message.edit_text(
        "👥 <b>ASIGNACIÓN DE JUGADORES</b>\n\n"
        "Tú eres el Jugador 1 de la Pareja 1.\n"
        "Escribe tu <b>compañero (Pareja 1)</b> usando su <b>@username</b>:\n"
        "<i>(Debe haber iniciado el bot previamente con /start)</i>"
    )
    await callback.answer()

# ==========================================
# 5. ASIGNACIÓN DE INTEGRANTES Y VALIDACIÓN
# ==========================================
@router.message(PrivateMatchFSM.waiting_for_p1_partner)
async def process_p1_partner(message: Message, state: FSMContext, session: AsyncSession):
    player = await resolve_player(message.text, session)
    if not player:
        await message.answer("⛔ <b>Usuario no registrado.</b> Debes escribir un @username válido que haya iniciado el bot con /start:")
        return
    if player.telegram_id == message.from_user.id:
        await message.answer("⛔ No puedes seleccionarte a ti mismo como compañero. Introduce otro @username:")
        return
        
    await state.update_data(p1_partner=player)
    await state.set_state(PrivateMatchFSM.waiting_for_p2_player1)
    await message.answer("Escribe el <b>Jugador 1 de la Pareja 2 (Rival)</b> usando su @username:")

@router.message(PrivateMatchFSM.waiting_for_p2_player1)
async def process_p2_player1(message: Message, state: FSMContext, session: AsyncSession):
    player = await resolve_player(message.text, session)
    data = await state.get_data()
    
    if not player:
        await message.answer("⛔ <b>Usuario no registrado.</b> Introduce su @username:")
        return
    if player.telegram_id in [message.from_user.id, data["p1_partner"].telegram_id]:
        await message.answer("⛔ Este jugador ya está en la Pareja 1. Introduce otro @username:")
        return
        
    await state.update_data(p2_player1=player)
    await state.set_state(PrivateMatchFSM.waiting_for_p2_player2)
    await message.answer("Por último, escribe el <b>Jugador 2 de la Pareja 2</b> usando su @username:")

@router.message(PrivateMatchFSM.waiting_for_p2_player2)
async def process_p2_player2(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    player = await resolve_player(message.text, session)
    data = await state.get_data()

    if not player:
        await message.answer("⛔ <b>Usuario no registrado.</b> Introduce su @username:")
        return
    if player.telegram_id in [message.from_user.id, data["p1_partner"].telegram_id, data["p2_player1"].telegram_id]:
        await message.answer("⛔ Este jugador ya está añadido en este partido. Introduce otro @username:")
        return

    await state.update_data(p2_player2=player)
    data["p2_player2"] = player
    
    match_dt = data["datetime"]
    if match_dt < datetime.now():
        await state.set_state(PrivateMatchFSM.waiting_for_score)
        await message.answer(
            "🎾 <b>PARTIDO YA DISPUTADO DETECTADO</b>\n\n"
            "Introduce el resultado final por sets (ej. <code>6-4 3-6 7-6</code>):"
        )
    else:
        await show_private_summary(message, state, session, is_past=False)

# ==========================================
# 7. MARCADOR INMEDIATO Y CIERRE
# ==========================================
@router.message(PrivateMatchFSM.waiting_for_score)
async def process_immediate_score(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    score = message.text.strip()
    await state.update_data(score=score)
    await show_private_summary(message, state, session, is_past=True)

# ---------- AÑADE ESTE BLOQUE COMPLETO AQUÍ ----------
async def show_private_summary(message: Message, state: FSMContext, session: AsyncSession, is_past: bool):
    """Muestra la tarjeta de resumen del partido privado con botones de confirmación o cancelación."""
    await state.update_data(is_past=is_past)
    data = await state.get_data()
    
    match_dt: datetime = data["datetime"]
    p1_partner = data["p1_partner"]
    p2_p1 = data["p2_player1"]
    p2_p2 = data["p2_player2"]
    
    creator_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    p1_partner_name = f"@{p1_partner.username}" if p1_partner.username else p1_partner.full_name
    p2_p1_name = f"@{p2_p1.username}" if p2_p1.username else p2_p1.full_name
    p2_p2_name = f"@{p2_p2.username}" if p2_p2.username else p2_p2.full_name
    
    tipo_str = "🔙 Partido ya jugado (Validación de acta)" if is_past else "📅 Partido agendado (Futuro)"
    score_line = f"📊 <b>Marcador:</b> {data.get('score')}\n" if is_past else ""
    
    text = (
        f"📋 <b>RESUMEN DEL PARTIDO PRIVADO</b>\n\n"
        f"📌 <b>Tipo:</b> {tipo_str}\n"
        f"📅 <b>Fecha y Hora:</b> {match_dt.strftime('%d/%m/%Y %H:%M')}\n"
        f"{score_line}\n"
        f"👥 <b>Pareja 1:</b>\n"
        f"  1. 👤 {creator_name} ⭐️\n"
        f"  2. 👤 {p1_partner_name}\n\n"
        f"👥 <b>Pareja 2:</b>\n"
        f"  1. 👤 {p2_p1_name}\n"
        f"  2. 👤 {p2_p2_name}\n\n"
        f"<i>Comprueba los datos. Pulsa para registrar el partido o cancelarlo.</i>"
    )
    
    await state.set_state(PrivateMatchFSM.confirming_summary)
    await message.answer(text, reply_markup=build_private_summary_keyboard())


@router.callback_query(PrivateMatchFSM.confirming_summary, F.data == "confirm_private_match")
async def process_confirm_private_match(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    """El usuario confirma: se guarda en base de datos."""
    data = await state.get_data()
    is_past = data.get("is_past", False)
    await finalize_private_match(callback, state, session, bot, is_past=is_past)
    await callback.answer()


@router.callback_query(PrivateMatchFSM.confirming_summary, F.data == "cancel_private_match")
async def process_cancel_private_match(callback: CallbackQuery, state: FSMContext):
    """El usuario cancela: se descarta la FSM sin tocar la base de datos."""
    await state.clear()
    await callback.message.edit_text("❌ <b>Creación cancelada.</b> El partido no se ha guardado en el sistema.")
    await callback.answer()

async def finalize_private_match(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot, is_past: bool):
    """Guarda el partido privado en BBDD y lanza el consenso si ya se jugó."""
    data = await state.get_data()
    user_id = callback.from_user.id

    new_match = Match(
        manager_id=user_id,
        datetime=data["datetime"],
        is_private=True,
        is_court_booked=True,
        status="VALIDATING" if is_past else "FULL",
        result=data.get("score")
    )
    session.add(new_match)
    await session.flush()

    # Inscribir a los 4 usuarios registrados directamente
    session.add(MatchPlayer(match_id=new_match.id, user_id=user_id, team=1))
    session.add(MatchPlayer(match_id=new_match.id, user_id=data["p1_partner"].telegram_id, team=1))
    session.add(MatchPlayer(match_id=new_match.id, user_id=data["p2_player1"].telegram_id, team=2))
    session.add(MatchPlayer(match_id=new_match.id, user_id=data["p2_player2"].telegram_id, team=2))

    await session.commit()
    await state.clear()

    if is_past:
        await callback.message.edit_text("✅ <b>Partido registrado con éxito.</b> Solicitando confirmación a los demás participantes...")
        
        for p in [data["p1_partner"], data["p2_player1"], data["p2_player2"]]:
            try:
                await bot.send_message(
                    p.telegram_id,
                    f"📋 <b>VALIDACIÓN DE PARTIDO PRIVADO #{new_match.id}</b>\n\n"
                    f"Marcador registrado: <b>{data['score']}</b>\n\n"
                    f"¿Confirmas el resultado?",
                    reply_markup=score_consensus_kb(new_match.id)
                )
            except Exception:
                pass
    else:
        await callback.message.edit_text("✅ <b>Partido privado agendado con éxito.</b> Se te avisará 2.5 horas después del inicio para introducir el resultado.")