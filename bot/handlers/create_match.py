from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.match_states import CreateMatchFSM
from bot.database.models import Location
from bot.keyboards.builders import (
    build_locations_keyboard,
    build_dates_keyboard,
    build_hours_keyboard,
    build_minutes_keyboard,
    build_level_types_keyboard,
    build_back_to_levels_keyboard,      
    build_back_to_locations_keyboard    
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
    await message.answer(
        "🎾 <b>NUEVA CONVOCATORIA</b>\n\n"
        "¿Dónde se jugará el partido?\n"
        "<i>(📍 = Pistas verificadas | ❓ = Pendientes)</i>",
        reply_markup=build_locations_keyboard(locations)
    )

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
async def process_custom_min_level(message: Message, state: FSMContext):
    try:
        min_lvl = float(message.text.replace(",", "."))
        if not (0.0 <= min_lvl <= 6.0):
            raise ValueError
            
        await state.update_data(min_level=min_lvl)
        await state.set_state(CreateMatchFSM.waiting_for_max_level)
        
        await message.answer(
            "✏️ <b>Nivel Personalizado (Paso 2/2)</b>\n\n"
            f"Nivel mínimo: {min_lvl}\n"
            "Ahora escribe el nivel <b>MÁXIMO</b> aceptado (ej. 4.0):"
            # Aquí podrías añadir otro teclado para volver al paso 1 si lo deseas
        )
    except ValueError:
        await message.answer("⛔ Por favor, introduce un número válido entre 0.0 y 6.0 (ej. 2.5):")


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