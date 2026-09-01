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

# ==========================================
# 2. FUNCIONES AUXILIARES
# ==========================================
async def resolve_player(text: str, session: AsyncSession) -> User | str | None:
    """
    Busca al usuario si empieza por '@'. 
    Devuelve objeto User si lo encuentra, string si es externo, o None si hay error.
    """
    text = text.strip()
    if text.startswith("@"):
        username = text[1:].strip()
        stmt = select(User).where(User.username.ilike(username))
        user = (await session.execute(stmt)).scalar_one_or_none()
        return user if user else None # None significa que introdujo un @ incorrecto
    return text # Es un invitado externo


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
        "Escribe tu <b>compañero (Pareja 1)</b>.\n"
        "<i>(Usa su @username si está registrado, o su nombre si es externo)</i>:"
    )
    await callback.answer()

# ==========================================
# 5. ASIGNACIÓN DE INTEGRANTES Y VALIDACIÓN
# ==========================================
@router.message(PrivateMatchFSM.waiting_for_p1_partner)
async def process_p1_partner(message: Message, state: FSMContext, session: AsyncSession):
    player = await resolve_player(message.text, session)
    if player is None:
        await message.answer("⛔ El @username indicado no está registrado en el bot. Vuelve a escribirlo (o introduce un nombre sin @ si es externo):")
        return
        
    # Guardamos el objeto User o el string
    await state.update_data(p1_partner=player)
    await state.set_state(PrivateMatchFSM.waiting_for_p2_player1)
    await message.answer("Escribe el <b>Jugador 1 de la Pareja 2 (Rival)</b>:")


@router.message(PrivateMatchFSM.waiting_for_p2_player1)
async def process_p2_player1(message: Message, state: FSMContext, session: AsyncSession):
    player = await resolve_player(message.text, session)
    if player is None:
        await message.answer("⛔ El @username indicado no está registrado. Vuelve a intentarlo:")
        return
        
    await state.update_data(p2_player1=player)
    await state.set_state(PrivateMatchFSM.waiting_for_p2_player2)
    await message.answer("Por último, escribe el <b>Jugador 2 de la Pareja 2</b>:")


@router.message(PrivateMatchFSM.waiting_for_p2_player2)
async def process_p2_player2(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    player = await resolve_player(message.text, session)
    if player is None:
        await message.answer("⛔ El @username indicado no está registrado. Vuelve a intentarlo:")
        return

    data = await state.get_data()
    p2_player1 = data["p2_player1"]
    
    # REGLA ESTRICTA: Mínimo 1 registrado en Pareja 2[cite: 1, 4]
    if not isinstance(p2_player1, User) and not isinstance(player, User):
        await message.answer(
            "⛔ <b>Validación fallida:</b>\n"
            "Para garantizar la validez del resultado, debe haber al menos un jugador con cuenta de Telegram en la Pareja 2.\n\n"
            "Vuelve a introducir el <b>Jugador 2 de la Pareja 2</b> usando su @username:"
        )
        return

    await state.update_data(p2_player2=player)
    data["p2_player2"] = player  # Actualizamos el diccionario local
    
    # 6. BIFURCACIÓN TEMPORAL (Pasado vs Futuro)[cite: 4]
    match_dt = data["datetime"]
    now = datetime.now()
    
    if match_dt < now:
        await state.set_state(PrivateMatchFSM.waiting_for_score)
        await message.answer(
            "🎾 <b>PARTIDO YA DISPUTADO DETECTADO</b>\n\n"
            "Como la fecha es anterior a este momento, por favor introduce el resultado final "
            "por sets (ej. <code>6-4 3-6 7-6</code>):"
        )
    else:
        await finalize_private_match(message, state, session, bot, is_past=False)

# ==========================================
# 7. MARCADOR INMEDIATO Y CIERRE
# ==========================================
@router.message(PrivateMatchFSM.waiting_for_score)
async def process_immediate_score(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    score = message.text.strip()
    await state.update_data(score=score)
    await finalize_private_match(message, state, session, bot, is_past=True)


async def finalize_private_match(message: Message, state: FSMContext, session: AsyncSession, bot: Bot, is_past: bool):
    """Guarda el partido privado en BBDD y lanza el consenso si ya se jugó."""
    data = await state.get_data()
    user_id = message.from_user.id
    
    # 1. Crear el partido
    new_match = Match(
        manager_id=user_id,
        datetime=data["datetime"],
        is_private=True,
        is_court_booked=True, # Se presupone
        status="VALIDATING" if is_past else "FULL",
        result=data.get("score")
    )
    session.add(new_match)
    await session.flush()

    # 2. Registrar Pareja 1
    # Titular
    session.add(MatchPlayer(match_id=new_match.id, user_id=user_id, team=1))
    
    # Compañero P1
    p1_part = data["p1_partner"]
    if isinstance(p1_part, User):
        session.add(MatchPlayer(match_id=new_match.id, user_id=p1_part.telegram_id, team=1))
    else:
        session.add(MatchPlayer(match_id=new_match.id, guest_name=p1_part, registered_by=user_id, team=1))

    # 3. Registrar Pareja 2
    for p2_player in [data["p2_player1"], data["p2_player2"]]:
        if isinstance(p2_player, User):
            session.add(MatchPlayer(match_id=new_match.id, user_id=p2_player.telegram_id, team=2))
        else:
            session.add(MatchPlayer(match_id=new_match.id, guest_name=p2_player, registered_by=user_id, team=2))

    await session.commit()
    await state.clear()

    if is_past:
        await message.answer("✅ Partido pasado registrado. Solicitando confirmación a la pareja rival...")
        
        # Enviar consenso a los registrados de la Pareja 2[cite: 1, 4]
        for p2_player in [data["p2_player1"], data["p2_player2"]]:
            if isinstance(p2_player, User):
                try:
                    await bot.send_message(
                        p2_player.telegram_id,
                        f"📋 <b>VALIDACIÓN DE PARTIDO PRIVADO</b>\n\n"
                        f"Se ha registrado un partido donde participaste.\n"
                        f"<b>Marcador indicado:</b> {data['score']}\n\n"
                        f"¿Confirmas que el resultado es correcto?",
                        reply_markup=score_consensus_kb(new_match.id)
                    )
                except Exception:
                    pass # Evitar crash si el rival tiene bloqueado al bot
    else:
        await message.answer("✅ Partido privado agendado con éxito. Se te avisará 2.5 horas después del inicio para introducir el resultado.")