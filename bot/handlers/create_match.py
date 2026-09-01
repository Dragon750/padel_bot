from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.match_states import CreateMatchFSM
from bot.database.models import Location, Match, MatchPlayer
from bot.database.base import AsyncSessionLocal
from bot.keyboards.builders import (
    build_locations_keyboard,
    build_dates_keyboard,
    build_hours_keyboard,
    build_minutes_keyboard,
    build_level_types_keyboard,
    build_back_to_levels_keyboard,      
    build_back_to_locations_keyboard,
    build_address_keyboard,
    build_back_to_min_level_keyboard
)

from bot.keyboards.inline import court_booking_status_kb, match_card_kb

router = Router()

# ==========================================
# 1. INICIO DEL ASISTENTE (/crear)
# ==========================================
@router.message(Command("crear"))
async def cmd_crear_partido(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    
    stmt = select(Location).order_by(Location.name)
    result = await session.execute(stmt)
    locations = list(result.scalars().all())
    
    await state.set_state(CreateMatchFSM.waiting_for_location)
    
    # Mandamos el mensaje y GUARDAMOS su ID en la variable 'msg'
    msg = await message.answer(
        "🎾 <b>NUEVA CONVOCATORIA</b>\n\n"
        "¿Dónde se jugará el partido?\n"
        "<i>(📍 = Pistas verificadas | ❓ = Pendientes)</i>",
        reply_markup=build_locations_keyboard(locations)
    )
    
    # Guardamos el ID en la memoria del FSM para usarlo luego
    await state.update_data(prompt_message_id=msg.message_id)

# ==========================================
# 2. SELECCIÓN DE UBICACIÓN
# ==========================================
@router.callback_query(CreateMatchFSM.waiting_for_location, F.data.startswith("loc_"))
async def process_location(callback: CallbackQuery, state: FSMContext):
    location_data = callback.data.split("_")[1]
    
    if location_data == "manual":
        await state.set_state(CreateMatchFSM.waiting_for_custom_location_name)
        await callback.message.edit_text(
            "Escribe el <b>nombre</b> del club o lugar:",
            reply_markup=build_back_to_locations_keyboard() # AQUÍ AÑADIMOS EL BOTÓN "VOLVER"
        )
    else:
        await state.update_data(location_id=int(location_data))
        await state.set_state(CreateMatchFSM.waiting_for_date)
        
        await callback.message.edit_text(
            "📅 <b>¿Qué día se jugará?</b>\n\n"
            "Selecciona una de las siguientes fechas:",
            reply_markup=build_dates_keyboard()
        )
    await callback.answer()

# ==========================================
# 2B. ENTRADA MANUAL DE PISTA Y OMITIR DIRECCIÓN
# ==========================================
@router.message(CreateMatchFSM.waiting_for_custom_location_name)
async def process_custom_location_name(message: Message, state: FSMContext, bot: Bot):
    """Captura el nombre, borra el mensaje del usuario y edita la tarjeta original"""
    try:
        await message.delete()
    except Exception:
        pass 
        
    await state.update_data(custom_loc_name=message.text.strip())
    await state.set_state(CreateMatchFSM.waiting_for_custom_location_address)
    
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    
    if prompt_message_id:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text="📍 Ahora escribe la <b>dirección aproximada o el enlace de Google Maps</b>:\n\n"
                 "<i>(Si no lo tienes a mano, pulsa en Omitir y se añadirá más adelante)</i>.",
            reply_markup=build_address_keyboard()
        )


@router.callback_query(CreateMatchFSM.waiting_for_custom_location_address, F.data == "skip_address")
async def skip_custom_location_address(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """El usuario decide no introducir enlace de Maps"""
    data = await state.get_data()
    custom_loc_name = data["custom_loc_name"]
    
    # Creamos la pista con maps_url = None
    new_loc = Location(
        name=custom_loc_name,
        maps_url=None, 
        is_approved=False,
        suggested_by=callback.from_user.id
    )
    session.add(new_loc)
    await session.flush()
    
    await state.update_data(location_id=new_loc.id)
    await state.set_state(CreateMatchFSM.waiting_for_date)
    await session.commit()
    
    await callback.message.edit_text(
        "✅ Pista guardada sin enlace (pendiente de moderación).\n\n"
        "📅 <b>¿Qué día se jugará?</b>\n\n"
        "Selecciona una de las siguientes fechas:",
        reply_markup=build_dates_keyboard()
    )
    await callback.answer()


@router.message(CreateMatchFSM.waiting_for_custom_location_address)
async def process_custom_location_address(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Captura el enlace, borra el mensaje y avanza editando la tarjeta"""
    try:
        await message.delete()
    except Exception:
        pass
        
    custom_loc_address = message.text.strip()
    data = await state.get_data()
    
    new_loc = Location(
        name=data["custom_loc_name"],
        maps_url=custom_loc_address,
        is_approved=False,
        suggested_by=message.from_user.id
    )
    session.add(new_loc)
    await session.flush()
    
    await state.update_data(location_id=new_loc.id)
    await state.set_state(CreateMatchFSM.waiting_for_date)
    await session.commit()
    
    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text="✅ Pista guardada (pendiente de moderación).\n\n"
                 "📅 <b>¿Qué día se jugará?</b>\n\n"
                 "Selecciona una de las siguientes fechas:",
            reply_markup=build_dates_keyboard()
        )
    
# ==========================================
# 3. SELECCIÓN DE FECHA
# ==========================================
@router.callback_query(CreateMatchFSM.waiting_for_date, F.data.startswith("date_"))
async def process_date(callback: CallbackQuery, state: FSMContext):
    # El callback data llega como "date_YYYY-MM-DD"
    date_str = callback.data.split("_")[1]
    selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    await state.update_data(date=selected_date)
    await state.set_state(CreateMatchFSM.waiting_for_hour)
    
    await callback.message.edit_text(
        "⏰ <b>¿A qué hora empieza?</b>\n"
        "Selecciona primero la hora:",
        reply_markup=build_hours_keyboard(selected_date)
    )
    await callback.answer()

# ==========================================
# 4. SELECCIÓN DE HORA Y MINUTOS
# ==========================================
@router.callback_query(CreateMatchFSM.waiting_for_hour, F.data.startswith("hour_"))
async def process_hour(callback: CallbackQuery, state: FSMContext):
    selected_hour = int(callback.data.split("_")[1])
    data = await state.get_data()
    selected_date = data["date"]
    
    await state.update_data(hour=selected_hour)
    await state.set_state(CreateMatchFSM.waiting_for_minute)
    
    await callback.message.edit_text(
        f"⏰ Has elegido las <b>{selected_hour:02d}h</b>.\n"
        "Ahora selecciona los minutos:",
        reply_markup=build_minutes_keyboard(selected_hour, selected_date)
    )
    await callback.answer()


@router.callback_query(CreateMatchFSM.waiting_for_minute, F.data.startswith("time_"))
async def process_minute(callback: CallbackQuery, state: FSMContext):
    time_str = callback.data.split("_")[1]
    data = await state.get_data()
    selected_date = data["date"]
    
    time_obj = datetime.strptime(time_str, "%H:%M").time()
    final_datetime = datetime.combine(selected_date, time_obj)
    
    await state.update_data(datetime=final_datetime)
    
    await state.set_state(CreateMatchFSM.waiting_for_level_type)
    await callback.message.edit_text(
        "📊 <b>¿Qué nivel de juego se busca?</b>\n\n"
        "Elige un rango predefinido o personalízalo:",
        reply_markup=build_level_types_keyboard()
    )
    await callback.answer()

# ==========================================
# 5. BOTONES DE NAVEGACIÓN "VOLVER ATRÁS"
# ==========================================
@router.callback_query(F.data == "back_to_location")
async def nav_back_to_location(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Vuelve de Fecha a Ubicación"""
    stmt = select(Location).order_by(Location.name)
    result = await session.execute(stmt)
    locations = list(result.scalars().all())
    
    await state.set_state(CreateMatchFSM.waiting_for_location)
    await callback.message.edit_text(
        "🎾 <b>NUEVA CONVOCATORIA</b>\n\n¿Dónde se jugará el partido?",
        reply_markup=build_locations_keyboard(locations)
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_date")
async def nav_back_to_date(callback: CallbackQuery, state: FSMContext):
    """Vuelve de Hora a Fecha"""
    await state.set_state(CreateMatchFSM.waiting_for_date)
    await callback.message.edit_text(
        "📅 <b>¿Qué día se jugará?</b>\n\nSelecciona una de las siguientes fechas:",
        reply_markup=build_dates_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_hours")
async def nav_back_to_hours(callback: CallbackQuery, state: FSMContext):
    """Vuelve de Minutos a Hora"""
    data = await state.get_data()
    selected_date = data["date"]
    
    await state.set_state(CreateMatchFSM.waiting_for_hour)
    await callback.message.edit_text(
        "⏰ <b>¿A qué hora empieza?</b>\nSelecciona primero la hora:",
        reply_markup=build_hours_keyboard(selected_date)
    )
    await callback.answer()

# ==========================================
# 6. GESTIÓN DEL NIVEL Y SUS RETROCESOS
# ==========================================
@router.callback_query(CreateMatchFSM.waiting_for_level_type, F.data.startswith("lvl_"))
async def process_level_type(callback: CallbackQuery, state: FSMContext):
    level_data = callback.data.split("_", 1)[1] # Extrae "0.0_6.0" o "custom"
    
    if level_data == "custom":
        # Nivel personalizado en 2 pasos
        await state.set_state(CreateMatchFSM.waiting_for_min_level)
        await callback.message.edit_text(
            "✏️ <b>Nivel Personalizado (Paso 1/2)</b>\n\n"
            "Escribe el nivel <b>MÍNIMO</b> aceptado (ej. 2.5):",
            reply_markup=build_back_to_levels_keyboard()
        )
    else:
        # Si elige un bloque predefinido, guardamos los valores y saltamos a Reserva
        min_lvl, max_lvl = map(float, level_data.split("_"))
        await state.update_data(min_level=min_lvl, max_level=max_lvl)
        
        await state.set_state(CreateMatchFSM.waiting_for_court_status)
        await callback.message.edit_text(
            "✅ Nivel configurado.\n\n"
            "🎾 <b>¿Tienes ya la pista reservada en el club?</b>",
            reply_markup=court_booking_status_kb() # Asumiendo que importaste esto de inline.py
        )
    await callback.answer()


@router.message(CreateMatchFSM.waiting_for_min_level)
async def process_custom_min_level(message: Message, state: FSMContext, bot: Bot):
    """Captura el nivel mínimo, borra el texto y actualiza la tarjeta"""
    try:
        await message.delete()
    except Exception:
        pass
        
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    
    try:
        min_lvl = float(message.text.replace(",", "."))
        if not (0.0 <= min_lvl <= 6.0):
            raise ValueError
            
        await state.update_data(min_level=min_lvl)
        await state.set_state(CreateMatchFSM.waiting_for_max_level)
        
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text="✏️ <b>Nivel Personalizado (Paso 2/2)</b>\n\n"
                 f"Nivel mínimo: {min_lvl}\n"
                 "Ahora escribe el nivel <b>MÁXIMO</b> aceptado (ej. 4.0):",
            reply_markup=build_back_to_min_level_keyboard() # <--- AÑADIDO EL TECLADO
        )
    except ValueError:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text="⛔ <b>Formato inválido.</b>\n"
                 "Por favor, introduce un número válido entre 0.0 y 6.0 (ej. 2.5):",
            reply_markup=build_back_to_levels_keyboard()
        )


@router.message(CreateMatchFSM.waiting_for_max_level)
async def process_custom_max_level(message: Message, state: FSMContext, bot: Bot):
    """Captura el nivel máximo, valida contra el mínimo y avanza a reserva"""
    try:
        await message.delete()
    except Exception:
        pass
        
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    min_lvl = data.get("min_level", 0.0)
    
    try:
        max_lvl = float(message.text.replace(",", "."))
        if not (0.0 <= max_lvl <= 6.0) or max_lvl < min_lvl:
            raise ValueError
            
        await state.update_data(max_level=max_lvl)
        await state.set_state(CreateMatchFSM.waiting_for_court_status)
        
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text="✅ Nivel configurado correctamente.\n\n"
                 "🎾 <b>¿Tienes ya la pista reservada en el club?</b>",
            reply_markup=court_booking_status_kb()
        )
    except ValueError:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text=f"⛔ <b>Error.</b> El máximo debe ser un número entre {min_lvl} y 6.0.\n\n"
                 "Vuelve a escribir el nivel <b>MÁXIMO</b> aceptado:",
            reply_markup=build_back_to_min_level_keyboard() # <--- AÑADIDO EL TECLADO PARA QUE NO SE QUEDE ATRAPADO
        )

# ==========================================
# ENTRADA DE NÚMERO DE PISTA Y PUBLICACIÓN
# ==========================================
@router.message(CreateMatchFSM.waiting_for_court_number)
async def process_court_number(message: Message, state: FSMContext, bot: Bot):
    """Captura la pista, borra el mensaje y finaliza la creación"""
    try:
        await message.delete()
    except Exception:
        pass
        
    court_num = message.text.strip()
    await state.update_data(court_number=court_num)
    
    # Pasamos el objeto message para extraer chat.id, pero usaremos el prompt original
    await finalize_match_creation(message, state, message.from_user.id, bot)


async def finalize_match_creation(message: Message, state: FSMContext, user_id: int, bot: Bot):
    """Inserta el partido, limpia estado y convierte el prompt en la Tarjeta Interactiva"""
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    
    async with AsyncSessionLocal() as session:
        new_match = Match(
            manager_id=user_id,
            location_id=data["location_id"],
            datetime=data["datetime"],
            min_level=data.get("min_level", 0.0),
            max_level=data.get("max_level", 6.0),
            is_court_booked=data["is_court_booked"],
            court_number=data.get("court_number"),
            booked_by=user_id if data["is_court_booked"] else None,
            status="OPEN"
        )
        session.add(new_match)
        await session.flush() 
        
        creator_player = MatchPlayer(
            match_id=new_match.id,
            user_id=user_id,
            team=1
        )
        session.add(creator_player)
        loc = await session.get(Location, new_match.location_id)
        await session.commit()
        
    await state.clear()
    
    court_info = f"🟢 Pista reservada ({new_match.court_number})" if new_match.is_court_booked else "🟡 Pista pendiente de reserva"
    
    text = (
        f"🎾 <b>CONVOCATORIA PÁDEL #{new_match.id}</b>\n\n"
        f"📍 <b>Lugar:</b> {loc.name}\n"
        f"📅 <b>Fecha:</b> {new_match.datetime.strftime('%d/%m/%Y %H:%M')}\n"
        f"📊 <b>Nivel:</b> {new_match.min_level:.1f} - {new_match.max_level:.1f}\n"
        f"📌 <b>Estado:</b> {court_info}\n\n"
        f"👥 <b>Pareja 1:</b>\n"
        f"  1. 👤 Creador\n"
        f"  2. [Libre]\n\n"
        f"👥 <b>Pareja 2:</b>\n"
        f"  1. [Libre]\n"
        f"  2. [Libre]\n"
    )
    
    kb = match_card_kb(new_match.id, new_match.is_court_booked, loc.maps_url if loc else None)
    
    # Transformamos definitivamente el mensaje inicial en la tarjeta pública
    if prompt_message_id:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text=text,
            reply_markup=kb
        )
    else:
        await message.answer(text, reply_markup=kb)


# ==========================================
# 7. NUEVOS BOTONES DE NAVEGACIÓN (ATRÁS Y CANCELAR)
# ==========================================
@router.callback_query(F.data == "cancel_creation")
async def cancel_creation_flow(callback: CallbackQuery, state: FSMContext):
    """Cancela completamente la creación desde el paso 1."""
    await state.clear()
    await callback.message.edit_text("❌ Creación de convocatoria cancelada.")
    await callback.answer()


@router.callback_query(F.data == "back_to_minutes")
async def nav_back_to_minutes(callback: CallbackQuery, state: FSMContext):
    """Vuelve de la selección de Nivel a la selección de Minutos."""
    data = await state.get_data()
    selected_hour = data["hour"]
    selected_date = data["date"]
    
    await state.set_state(CreateMatchFSM.waiting_for_minute)
    await callback.message.edit_text(
        f"⏰ Has elegido las <b>{selected_hour:02d}h</b>.\n"
        "Ahora selecciona los minutos:",
        reply_markup=build_minutes_keyboard(selected_hour, selected_date)
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_levels")
async def nav_back_to_levels(callback: CallbackQuery, state: FSMContext):
    """Vuelve del paso 1 de nivel personalizado a los bloques de Nivel."""
    await state.set_state(CreateMatchFSM.waiting_for_level_type)
    await callback.message.edit_text(
        "📊 <b>¿Qué nivel de juego se busca?</b>\n\n"
        "Elige un rango predefinido o personalízalo:",
        reply_markup=build_level_types_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_min_level")
async def nav_back_to_min_level(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Vuelve del paso 2 (máximo) al paso 1 (mínimo) del nivel personalizado."""
    await state.set_state(CreateMatchFSM.waiting_for_min_level)
    
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    
    if prompt_message_id:
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=prompt_message_id,
            text="✏️ <b>Nivel Personalizado (Paso 1/2)</b>\n\n"
                 "Escribe el nivel <b>MÍNIMO</b> aceptado (ej. 2.5):",
            reply_markup=build_back_to_levels_keyboard()
        )
    await callback.answer()