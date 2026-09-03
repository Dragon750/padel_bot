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
from bot.services.fuzzy_matcher import get_similar_locations
from bot.keyboards.builders import build_fuzzy_locations_keyboard
from bot.services.group_service import get_user_common_groups
from bot.handlers.match_card import render_match_card

from bot.keyboards.builders import (
    build_groups_keyboard,
    build_summary_confirmation_kb,
    build_locations_keyboard,
    build_dates_keyboard,
    build_hours_keyboard,
    build_minutes_keyboard,
    build_level_types_keyboard,
    build_back_to_levels_keyboard,      
    build_back_to_locations_keyboard,
    build_address_keyboard,
    build_back_to_min_level_keyboard,
    build_court_status_keyboard
)
from bot.keyboards.inline import match_card_kb

router = Router()

# ==========================================
# 1. INICIO: SELECCIÓN DE GRUPO (Chat Privado)
# ==========================================
@router.message(Command("crear"), F.chat.type == "private")
async def cmd_crear_privado(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.clear()
    
    # 1. Obtener grupos donde el bot y el usuario coexisten
    common_groups = await get_user_common_groups(bot, session, message.from_user.id)
    if not common_groups:
        await message.answer(
            "⚠️ <b>No tienes grupos comunes disponibles.</b>\n\n"
            "Asegúrate de que el bot está añadido como administrador en tu grupo de pádel y de que formas parte de él."
        )
        return

    await state.set_state(CreateMatchFSM.waiting_for_group)
    msg = await message.answer(
        "🎾 <b>NUEVA CONVOCATORIA</b>\n\n"
        "Selecciona el grupo donde publicarás el partido:",
        reply_markup=build_groups_keyboard(common_groups)
    )
    await state.update_data(prompt_message_id=msg.message_id)

@router.callback_query(CreateMatchFSM.waiting_for_group, F.data.startswith("target_group_"))
async def process_target_group(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    target_chat_id = int(callback.data.split("_")[2])
    
    # Guardamos el ID y el título para el resumen final
    chat = await bot.get_chat(target_chat_id)
    await state.update_data(target_chat_id=target_chat_id, target_chat_title=chat.title)

    data = await state.get_data()
    # Retorno rápido si estamos editando desde el resumen
    if data.get("editing_field"):
        await state.update_data(editing_field=False)
        await show_summary_confirmation(callback.message, state, bot, session)
        await callback.answer()
        return

    # Flujo normal: Avanzar a Ubicación
    stmt = select(Location).order_by(Location.name)
    locations = list((await session.execute(stmt)).scalars().all())

    await state.set_state(CreateMatchFSM.waiting_for_location)
    await callback.message.edit_text(
        "🎾 <b>NUEVA CONVOCATORIA</b>\n\n¿Dónde se jugará el partido?",
        reply_markup=build_locations_keyboard(locations)
    )
    await callback.answer()

# ==========================================
# 2. SELECCIÓN DE UBICACIÓN
# ==========================================
@router.callback_query(CreateMatchFSM.waiting_for_location, F.data.startswith("loc_"))
async def process_location(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    location_data = callback.data.split("_")[1]
    
    if location_data == "manual":
        await state.set_state(CreateMatchFSM.waiting_for_custom_location_name)
        await callback.message.edit_text(
            "Escribe el <b>nombre</b> del club o lugar:",
            reply_markup=build_back_to_locations_keyboard()
        )
    else:
        await state.update_data(location_id=int(location_data))
        
        data = await state.get_data()
        if data.get("editing_field"):
            await state.update_data(editing_field=False)
            await show_summary_confirmation(callback.message, state, bot, session)
            await callback.answer()
            return
            
        await state.set_state(CreateMatchFSM.waiting_for_date)
        await callback.message.edit_text(
            "📅 <b>¿Qué día se jugará?</b>\n\n"
            "Selecciona una de las siguientes fechas:",
            reply_markup=build_dates_keyboard()
        )
    await callback.answer()


# 2B. ENTRADA MANUAL DE PISTA Y FUZZY MATCHING

@router.message(CreateMatchFSM.waiting_for_custom_location_name)
async def process_custom_location_name(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Captura el nombre, consulta el algoritmo de duplicados (>75%) y edita la tarjeta"""
    try: 
        await message.delete()
    except Exception: 
        pass 
        
    custom_loc_name = message.text.strip()
    await state.update_data(custom_loc_name=custom_loc_name)
    
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    
    # 1. Ejecutamos la búsqueda de similitud (>75%)
    similar_locs = await get_similar_locations(session, custom_loc_name, threshold=0.75)
    
    if similar_locs and prompt_message_id:
        # 2A. Hay coincidencias: Mostramos la lista ordenada de mayor a menor
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text=f"🔍 <b>Hemos encontrado pistas similares.</b>\n\n"
                 f"Has escrito <i>'{custom_loc_name}'</i>.\n"
                 f"¿Te refieres a alguna de estas o es una pista completamente nueva?",
            reply_markup=build_fuzzy_locations_keyboard(similar_locs)
        )
    else:
        # 2B. No hay coincidencias: Saltamos directo a pedir la dirección de Maps
        await state.set_state(CreateMatchFSM.waiting_for_custom_location_address)
        if prompt_message_id:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=prompt_message_id,
                text="📍 Ahora escribe la <b>dirección aproximada o el enlace de Google Maps</b>:\n\n"
                     "<i>(Si no lo tienes a mano, pulsa en Omitir)</i>.",
                reply_markup=build_address_keyboard()
            )


@router.callback_query(F.data.startswith("fuzzymatch_"))
async def process_fuzzy_resolution(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    """Gestiona la elección del usuario en la lista de posibles duplicados."""
    action = callback.data.split("_")[1]
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    
    if action == "none":
        # Continúa como si no estuviese registrada
        await state.set_state(CreateMatchFSM.waiting_for_custom_location_address)
        if prompt_message_id:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=prompt_message_id,
                text="📍 Ahora escribe la <b>dirección aproximada o el enlace de Google Maps</b>:\n\n"
                     "<i>(Si no lo tienes a mano, pulsa en Omitir)</i>.",
                reply_markup=build_address_keyboard()
            )
    else:
        # Recicla la pista sugerida por el bot
        loc_id = int(action)
        await state.update_data(location_id=loc_id)
        
        # Lógica de redirección inteligente: ¿Viene del resumen final o es creación nueva?
        if data.get("editing_field"):
            await state.update_data(editing_field=False)
            await show_summary_confirmation(callback.message, state, bot, session)
        else:
            await state.set_state(CreateMatchFSM.waiting_for_date)
            if prompt_message_id:
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=prompt_message_id,
                    text="✅ Pista seleccionada correctamente.\n\n"
                         "📅 <b>¿Qué día se jugará?</b>\n\n"
                         "Selecciona una fecha:",
                    reply_markup=build_dates_keyboard()
                )
                
    await callback.answer()


@router.callback_query(CreateMatchFSM.waiting_for_custom_location_address, F.data == "skip_address")
async def skip_custom_location_address(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    custom_loc_name = data["custom_loc_name"]
    
    new_loc = Location(name=custom_loc_name, maps_url=None, is_approved=False, suggested_by=callback.from_user.id)
    session.add(new_loc)
    await session.flush()
    
    await state.update_data(location_id=new_loc.id)
    await session.commit()
    
    if data.get("editing_field"):
        await state.update_data(editing_field=False)
        await show_summary_confirmation(callback.message, state, bot, session)
        await callback.answer()
        return

    await state.set_state(CreateMatchFSM.waiting_for_date)
    await callback.message.edit_text(
        "✅ Pista guardada.\n\n📅 <b>¿Qué día se jugará?</b>\n\nSelecciona una fecha:",
        reply_markup=build_dates_keyboard()
    )
    await callback.answer()

@router.message(CreateMatchFSM.waiting_for_custom_location_address)
async def process_custom_location_address(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    try: await message.delete()
    except Exception: pass
        
    custom_loc_address = message.text.strip()
    data = await state.get_data()
    
    new_loc = Location(name=data["custom_loc_name"], maps_url=custom_loc_address, is_approved=False, suggested_by=message.from_user.id)
    session.add(new_loc)
    await session.flush()
    
    await state.update_data(location_id=new_loc.id)
    await session.commit()
    
    if data.get("editing_field"):
        await state.update_data(editing_field=False)
        await show_summary_confirmation(message, state, bot, session) # Pasamos message
        return
        
    await state.set_state(CreateMatchFSM.waiting_for_date)
    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text="✅ Pista guardada.\n\n📅 <b>¿Qué día se jugará?</b>\n\nSelecciona una fecha:",
            reply_markup=build_dates_keyboard()
        )
    
# ==========================================
# 3. SELECCIÓN DE FECHA
# ==========================================
@router.callback_query(CreateMatchFSM.waiting_for_date, F.data.startswith("date_"))
async def process_date(callback: CallbackQuery, state: FSMContext, bot: Bot, session: AsyncSession):
    date_str = callback.data.split("_")[1]
    selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    await state.update_data(date=selected_date)
    
    data = await state.get_data()
    if data.get("editing_field"):
        # Al cambiar fecha, la hora antigua podría ser inválida, así que forzamos a pedir hora nueva
        pass 
        
    await state.set_state(CreateMatchFSM.waiting_for_hour)
    await callback.message.edit_text(
        "⏰ <b>¿A qué hora empieza?</b>\nSelecciona primero la hora:",
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
    selected_date = data.get("date")
    
    if not selected_date:
        await state.clear()
        await callback.message.edit_text("⏳ Sesión expirada. Escribe /crear de nuevo.")
        return
        
    await state.update_data(hour=selected_hour)
    await state.set_state(CreateMatchFSM.waiting_for_minute)
    await callback.message.edit_text(
        f"⏰ Has elegido las <b>{selected_hour:02d}h</b>.\nAhora selecciona los minutos:",
        reply_markup=build_minutes_keyboard(selected_hour, selected_date)
    )
    await callback.answer()

@router.callback_query(CreateMatchFSM.waiting_for_minute, F.data.startswith("time_"))
async def process_minute(callback: CallbackQuery, state: FSMContext, bot: Bot, session: AsyncSession):
    time_str = callback.data.split("_")[1]
    data = await state.get_data()
    selected_date = data.get("date")
    
    if not selected_date:
        await state.clear()
        await callback.message.edit_text("⏳ Sesión expirada. Escribe /crear de nuevo.")
        return
        
    time_obj = datetime.strptime(time_str, "%H:%M").time()
    final_datetime = datetime.combine(selected_date, time_obj)
    await state.update_data(datetime=final_datetime)
    
    if data.get("editing_field"):
        await state.update_data(editing_field=False)
        await show_summary_confirmation(callback.message, state, bot, session)
        await callback.answer()
        return
    
    await state.set_state(CreateMatchFSM.waiting_for_level_type)
    await callback.message.edit_text(
        "📊 <b>¿Qué nivel de juego se busca?</b>\n\nElige un rango predefinido o personalízalo:",
        reply_markup=build_level_types_keyboard()
    )
    await callback.answer()

# ==========================================
# 5. GESTIÓN DEL NIVEL
# ==========================================
@router.callback_query(CreateMatchFSM.waiting_for_level_type, F.data.startswith("lvl_"))
async def process_level_type(callback: CallbackQuery, state: FSMContext, bot: Bot, session: AsyncSession):
    level_data = callback.data.split("_", 1)[1]
    
    if level_data == "custom":
        await state.set_state(CreateMatchFSM.waiting_for_min_level)
        await callback.message.edit_text(
            "✏️ <b>Nivel Personalizado (Paso 1/2)</b>\n\nEscribe el nivel <b>MÍNIMO</b> aceptado (ej. 2.5):",
            reply_markup=build_back_to_levels_keyboard()
        )
    else:
        min_lvl, max_lvl = map(float, level_data.split("_"))
        await state.update_data(min_level=min_lvl, max_level=max_lvl)
        
        data = await state.get_data()
        if data.get("editing_field"):
            await state.update_data(editing_field=False)
            await show_summary_confirmation(callback.message, state, bot, session)
            await callback.answer()
            return
            
        await state.set_state(CreateMatchFSM.waiting_for_court_status)
        await callback.message.edit_text(
            "🎾 <b>¿Tienes ya la pista reservada en el club?</b>",
            reply_markup=build_court_status_keyboard()
        )
    await callback.answer()

@router.message(CreateMatchFSM.waiting_for_min_level)
async def process_custom_min_level(message: Message, state: FSMContext, bot: Bot):
    try: await message.delete()
    except Exception: pass
        
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    
    try:
        min_lvl = float(message.text.replace(",", "."))
        if not (0.0 <= min_lvl <= 6.0): raise ValueError
            
        await state.update_data(min_level=min_lvl)
        await state.set_state(CreateMatchFSM.waiting_for_max_level)
        
        await bot.edit_message_text(
            chat_id=message.chat.id, message_id=prompt_message_id,
            text=f"✏️ <b>Nivel Personalizado (Paso 2/2)</b>\n\nNivel mínimo: {min_lvl}\nAhora escribe el nivel <b>MÁXIMO</b> aceptado:",
            reply_markup=build_back_to_min_level_keyboard()
        )
    except ValueError:
        await bot.edit_message_text(
            chat_id=message.chat.id, message_id=prompt_message_id,
            text="⛔ <b>Formato inválido.</b>\nIntroduce un número válido entre 0.0 y 6.0 (ej. 2.5):",
            reply_markup=build_back_to_levels_keyboard()
        )

@router.message(CreateMatchFSM.waiting_for_max_level)
async def process_custom_max_level(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    try: await message.delete()
    except Exception: pass
        
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    min_lvl = data.get("min_level", 0.0)
    
    try:
        max_lvl = float(message.text.replace(",", "."))
        if not (0.0 <= max_lvl <= 6.0) or max_lvl < min_lvl: raise ValueError
            
        await state.update_data(max_level=max_lvl)
        
        if data.get("editing_field"):
            await state.update_data(editing_field=False)
            await show_summary_confirmation(message, state, bot, session) # Pasamos message
            return
            
        await state.set_state(CreateMatchFSM.waiting_for_court_status)
        await bot.edit_message_text(
            chat_id=message.chat.id, message_id=prompt_message_id,
            text="✅ Nivel configurado.\n\n🎾 <b>¿Tienes ya la pista reservada en el club?</b>",
            reply_markup=build_court_status_keyboard()
        )
    except ValueError:
        await bot.edit_message_text(
            chat_id=message.chat.id, message_id=prompt_message_id,
            text=f"⛔ <b>Error.</b> El máximo debe ser un número entre {min_lvl} y 6.0.\n\nVuelve a escribir el nivel <b>MÁXIMO</b>:",
            reply_markup=build_back_to_min_level_keyboard()
        )

# ==========================================
# 6. ESTADO DE RESERVA DE PISTA
# ==========================================
@router.callback_query(CreateMatchFSM.waiting_for_court_status, F.data.startswith("book_"))
async def process_court_status(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    has_court = (callback.data == "book_yes")
    await state.update_data(is_court_booked=has_court)
    
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    
    if has_court:
        await state.set_state(CreateMatchFSM.waiting_for_court_number)
        if prompt_message_id:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id, message_id=prompt_message_id,
                text="🎾 Introduce el <b>número o nombre de la pista</b> (ej. <i>Pista 3</i>):"
            )
    else:
        await state.update_data(court_number=None)
        if data.get("editing_field"):
            await state.update_data(editing_field=False)
            await show_summary_confirmation(callback.message, state, bot, session)
        else:
            await show_summary_confirmation(callback.message, state, bot, session)
            
    await callback.answer()

@router.message(CreateMatchFSM.waiting_for_court_number)
async def process_court_number(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    try: await message.delete()
    except Exception: pass
        
    await state.update_data(court_number=message.text.strip())
    
    data = await state.get_data()
    if data.get("editing_field"):
        await state.update_data(editing_field=False)
        
    await show_summary_confirmation(message, state, bot, session)

# ==========================================
# 7. RESUMEN FINAL Y EDICIÓN GRANULAR
# ==========================================
async def show_summary_confirmation(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    """Muestra la tarjeta de confirmación con edición de cada parámetro antes de publicar."""
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")

    loc = await session.get(Location, data["location_id"])
    dt = data["datetime"].strftime("%d/%m/%Y a las %H:%M")
    pista_desc = f"Pista {data.get('court_number')}" if data.get("is_court_booked") else "Pendiente de reserva comunitaria"

    text = (
        "🔍 <b>REVISIÓN DE CONVOCATORIA</b>\n\n"
        f"👥 <b>Grupo destino:</b> {data.get('target_chat_title')}\n"
        f"📍 <b>Lugar:</b> {loc.name}\n"
        f"📅 <b>Fecha y Hora:</b> {dt}\n"
        f"📊 <b>Nivel:</b> {data.get('min_level'):.1f} - {data.get('max_level'):.1f}\n"
        f"🎾 <b>Pista:</b> {pista_desc}\n\n"
        "<i>Pulsa en Publicar o modifica cualquier dato erróneo:</i>"
    )

    await state.set_state(CreateMatchFSM.confirming_summary)
    
    if prompt_message_id:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=prompt_message_id,
                text=text,
                reply_markup=build_summary_confirmation_kb()
            )
        except Exception:
            pass

@router.callback_query(CreateMatchFSM.confirming_summary, F.data.startswith("edit_field_"))
async def route_edit_field(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    """Activa la bandera de edición y redirige al paso correspondiente."""
    field = callback.data.split("edit_field_")[1]
    await state.update_data(editing_field=True) 

    if field == "group":
        common_groups = await get_user_common_groups(bot, session, callback.from_user.id)
        await state.set_state(CreateMatchFSM.waiting_for_group)
        await callback.message.edit_text("👥 Selecciona el nuevo grupo:", reply_markup=build_groups_keyboard(common_groups))

    elif field == "location":
        stmt = select(Location).order_by(Location.name)
        locations = list((await session.execute(stmt)).scalars().all())
        await state.set_state(CreateMatchFSM.waiting_for_location)
        await callback.message.edit_text("📍 Selecciona la nueva ubicación:", reply_markup=build_locations_keyboard(locations))

    elif field == "date":
        await state.set_state(CreateMatchFSM.waiting_for_date)
        await callback.message.edit_text("📅 Selecciona la nueva fecha:", reply_markup=build_dates_keyboard())

    elif field == "hour":
        data = await state.get_data()
        await state.set_state(CreateMatchFSM.waiting_for_hour)
        await callback.message.edit_text("⏰ Selecciona la nueva hora:", reply_markup=build_hours_keyboard(data["date"]))

    elif field == "level":
        await state.set_state(CreateMatchFSM.waiting_for_level_type)
        await callback.message.edit_text("📊 Selecciona el nuevo rango de nivel:", reply_markup=build_level_types_keyboard())

    elif field == "court":
        await state.set_state(CreateMatchFSM.waiting_for_court_status)
        await callback.message.edit_text("🎾 ¿Tienes ya la pista reservada?", reply_markup=build_court_status_keyboard())

    await callback.answer()

# ==========================================
# 8. PUBLICACIÓN FINAL EN EL GRUPO
# ==========================================
@router.callback_query(CreateMatchFSM.confirming_summary, F.data == "publish_match")
async def process_publish_match(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    target_chat_id = data["target_chat_id"]
    user_id = callback.from_user.id

    async with AsyncSessionLocal() as db_session:
        # 1. Crear el partido en BBDD
        new_match = Match(
            manager_id=user_id,
            location_id=data["location_id"],
            datetime=data["datetime"],
            min_level=data.get("min_level", 0.0),
            max_level=data.get("max_level", 6.0),
            is_court_booked=data["is_court_booked"],
            court_number=data.get("court_number"),
            booked_by=user_id if data["is_court_booked"] else None,
            status="OPEN",
            chat_id=target_chat_id
        )
        db_session.add(new_match)
        await db_session.flush()

        # 2. Inscribir al creador
        creator_player = MatchPlayer(match_id=new_match.id, user_id=user_id, team=1)
        db_session.add(creator_player)
        await db_session.commit()

        # 3. Renderizar y publicar en el Grupo
        text, maps_url, is_booked = await render_match_card(new_match.id, db_session)
        kb = match_card_kb(new_match.id, is_booked, maps_url)
        
        group_msg = await bot.send_message(chat_id=target_chat_id, text=text, reply_markup=kb)
        
        # 4. Guardar ID del mensaje público para ediciones futuras
        new_match.message_id = group_msg.message_id
        await db_session.commit()

    await state.clear()

    # 5. Confirmar en privado
    await callback.message.edit_text(
        f"✅ <b>¡Convocatoria publicada!</b>\n\n"
        f"La tarjeta interactiva ya está disponible en <b>{data.get('target_chat_title')}</b>."
    )
    await callback.answer()

# ==========================================
# 9. BOTONES DE NAVEGACIÓN Y CANCELACIÓN
# ==========================================
@router.callback_query(F.data == "cancel_creation")
async def cancel_creation_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Creación de convocatoria cancelada.")
    await callback.answer()

@router.callback_query(F.data == "back_to_location")
async def nav_back_to_location(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    stmt = select(Location).order_by(Location.name)
    locations = list((await session.execute(stmt)).scalars().all())
    await state.set_state(CreateMatchFSM.waiting_for_location)
    await callback.message.edit_text("🎾 <b>NUEVA CONVOCATORIA</b>\n\n¿Dónde se jugará?", reply_markup=build_locations_keyboard(locations))
    await callback.answer()

@router.callback_query(F.data == "back_to_date")
async def nav_back_to_date(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateMatchFSM.waiting_for_date)
    await callback.message.edit_text("📅 <b>¿Qué día se jugará?</b>\n\nSelecciona una fecha:", reply_markup=build_dates_keyboard())
    await callback.answer()

@router.callback_query(F.data == "back_to_hours")
async def nav_back_to_hours(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_date = data.get("date")
    if not selected_date:
        await state.clear()
        return await callback.message.edit_text("⏳ Sesión expirada. Empieza de nuevo con /crear.")
        
    await state.set_state(CreateMatchFSM.waiting_for_hour)
    await callback.message.edit_text("⏰ <b>¿A qué hora empieza?</b>\nSelecciona la hora:", reply_markup=build_hours_keyboard(selected_date))
    await callback.answer()

@router.callback_query(F.data == "back_to_minutes")
async def nav_back_to_minutes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_hour, selected_date = data.get("hour"), data.get("date")
    if selected_hour is None or selected_date is None:
        await state.clear()
        return await callback.message.edit_text("⏳ Sesión expirada. Empieza de nuevo con /crear.")
        
    await state.set_state(CreateMatchFSM.waiting_for_minute)
    await callback.message.edit_text(f"⏰ Has elegido las <b>{selected_hour:02d}h</b>.\nSelecciona los minutos:", reply_markup=build_minutes_keyboard(selected_hour, selected_date))
    await callback.answer()

@router.callback_query(F.data == "back_to_levels")
async def nav_back_to_levels(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateMatchFSM.waiting_for_level_type)
    await callback.message.edit_text("📊 <b>¿Qué nivel se busca?</b>\n\nElige un rango predefinido o personalízalo:", reply_markup=build_level_types_keyboard())
    await callback.answer()

@router.callback_query(F.data == "back_to_min_level")
async def nav_back_to_min_level(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("prompt_message_id"):
        await state.clear()
        return await callback.message.edit_text("⏳ Sesión expirada.")

    await state.set_state(CreateMatchFSM.waiting_for_min_level)
    await callback.message.edit_text("✏️ <b>Nivel Personalizado (Paso 1/2)</b>\n\nEscribe el nivel <b>MÍNIMO</b> aceptado (ej. 2.5):", reply_markup=build_back_to_levels_keyboard())
    await callback.answer()