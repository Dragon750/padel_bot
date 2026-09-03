from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Location
from bot.states.admin_states import AdminPanelFSM
from bot.config import config

router = Router()

# ==========================================
# MOTOR DE RENDERIZADO DEL PANEL PAGINADO
# ==========================================
async def render_admin_panel(
    chat_id: int, 
    session: AsyncSession, 
    state: FSMContext, 
    bot: Bot, 
    index: int = 0, 
    message_id_to_edit: int | None = None
):
    """Genera la vista única paginada para las pistas pendientes de aprobación."""
    
    # Obtener todas las pistas no aprobadas
    stmt = select(Location).where(Location.is_approved == False).order_by(Location.id)
    pending_locations = (await session.execute(stmt)).scalars().all()
    
    if not pending_locations:
        text = "🎉 <b>¡Todo al día!</b>\n\nNo hay ninguna pista pendiente de moderación en este momento."
        if message_id_to_edit:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text=text)
        else:
            msg = await bot.send_message(chat_id=chat_id, text=text)
            await state.update_data(panel_msg_id=msg.message_id)
        await state.set_state(AdminPanelFSM.viewing_panel)
        return

    # Ajustes de seguridad para el índice de paginación
    if index >= len(pending_locations):
        index = len(pending_locations) - 1
    if index < 0:
        index = 0
        
    loc = pending_locations[index]
    
    # Guardamos el estado actual para saber qué pista estamos viendo y editando
    await state.update_data(current_admin_index=index, current_loc_id=loc.id)
    
    # Construcción visual de la tarjeta
    text = (
        f"🏢 <b>NUEVA PISTA SUGERIDA ({index + 1}/{len(pending_locations)})</b>\n\n"
        f"👤 <b>Propuesta por ID:</b> <code>{loc.suggested_by or 'Desconocido'}</code>\n"
        f"📍 <b>Nombre:</b> {loc.name}\n"
        f"🔗 <b>Enlace Maps:</b> {loc.maps_url or 'No proporcionado'}\n\n"
        "<i>¿Qué deseas hacer con esta solicitud?</i>"
    )
    
    # Construcción de la Botonera Interactiva
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Aprobar", callback_data=f"adm_ok_{loc.id}")
    builder.button(text="❌ Rechazar", callback_data=f"adm_ko_{loc.id}")
    builder.button(text="✏️ Editar Nombre", callback_data=f"adm_edit_name_{loc.id}")
    builder.button(text="✏️ Editar URL", callback_data=f"adm_edit_url_{loc.id}")
    
    # Fila de Paginación
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Anterior", callback_data=f"adm_nav_{index - 1}"))
    if index < len(pending_locations) - 1:
        nav_row.append(InlineKeyboardButton(text="Siguiente ➡️", callback_data=f"adm_nav_{index + 1}"))
        
    builder.adjust(2, 2)
    if nav_row:
        builder.row(*nav_row)
        
    kb = builder.as_markup()
    await state.set_state(AdminPanelFSM.viewing_panel)
    
    if message_id_to_edit:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text=text, reply_markup=kb)
    else:
        msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)
        await state.update_data(panel_msg_id=msg.message_id)

# ==========================================
# INVOCACIÓN DEL COMANDO
# ==========================================
@router.message(Command("panel"), F.from_user.id == config.ADMIN_TELEGRAM_ID)
async def cmd_admin_panel(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Abre la bandeja de entrada del administrador."""
    await message.delete() # Borramos el comando /panel para mantener limpio el chat
    await render_admin_panel(message.chat.id, session, state, bot, index=0)


# ==========================================
# ACCIONES DE BOTONES (Aprobar, Rechazar, Navegar)
# ==========================================
@router.callback_query(AdminPanelFSM.viewing_panel, F.data.startswith("adm_nav_"))
async def handle_admin_nav(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    """Paginación entre pistas."""
    target_index = int(callback.data.split("_")[2])
    await render_admin_panel(callback.message.chat.id, session, state, bot, index=target_index, message_id_to_edit=callback.message.message_id)
    await callback.answer()

@router.callback_query(AdminPanelFSM.viewing_panel, F.data.startswith("adm_ok_"))
async def handle_admin_approve(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    """Aprueba la pista y refresca el panel."""
    loc_id = int(callback.data.split("_")[2])
    loc = await session.get(Location, loc_id)
    
    if loc:
        loc.is_approved = True
        await session.commit()
        await callback.answer(f"✅ '{loc.name}' aprobada con éxito.", show_alert=True)
        
    data = await state.get_data()
    await render_admin_panel(callback.message.chat.id, session, state, bot, index=data.get("current_admin_index", 0), message_id_to_edit=callback.message.message_id)

@router.callback_query(AdminPanelFSM.viewing_panel, F.data.startswith("adm_ko_"))
async def handle_admin_reject(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    """Rechaza la pista (la elimina) y refresca el panel."""
    loc_id = int(callback.data.split("_")[2])
    loc = await session.get(Location, loc_id)
    
    if loc:
        await session.delete(loc)
        await session.commit()
        await callback.answer(f"❌ '{loc.name}' ha sido rechazada y eliminada.", show_alert=True)
        
    data = await state.get_data()
    # Al borrar un elemento, mantenemos el índice (o bajamos uno si era el último)
    await render_admin_panel(callback.message.chat.id, session, state, bot, index=data.get("current_admin_index", 0), message_id_to_edit=callback.message.message_id)


# ==========================================
# FLUJO DE EDICIÓN (Single-Bubble UX)
# ==========================================
@router.callback_query(AdminPanelFSM.viewing_panel, F.data.startswith("adm_edit_"))
async def handle_admin_edit_request(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Prepara el bot para escuchar el nuevo nombre o URL."""
    parts = callback.data.split("_")
    field_to_edit = parts[2] # "name" o "url"
    
    if field_to_edit == "name":
        await state.set_state(AdminPanelFSM.waiting_for_new_name)
        prompt = "✏️ <b>Editando Nombre:</b>\nEscribe el nuevo nombre para esta pista:"
    else:
        await state.set_state(AdminPanelFSM.waiting_for_new_url)
        prompt = "✏️ <b>Editando URL:</b>\nEscribe o pega el nuevo enlace de Google Maps:"
        
    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=prompt
    )
    await callback.answer()

@router.message(AdminPanelFSM.waiting_for_new_name)
async def process_admin_new_name(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Captura el nuevo nombre, borra el mensaje y vuelve al panel."""
    try: await message.delete()
    except Exception: pass
    
    data = await state.get_data()
    loc_id = data.get("current_loc_id")
    loc = await session.get(Location, loc_id)
    
    if loc:
        loc.name = message.text.strip()
        await session.commit()
        
    await render_admin_panel(message.chat.id, session, state, bot, index=data.get("current_admin_index", 0), message_id_to_edit=data.get("panel_msg_id"))

@router.message(AdminPanelFSM.waiting_for_new_url)
async def process_admin_new_url(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Captura la nueva URL, borra el mensaje y vuelve al panel."""
    try: await message.delete()
    except Exception: pass
    
    data = await state.get_data()
    loc_id = data.get("current_loc_id")
    loc = await session.get(Location, loc_id)
    
    if loc:
        loc.maps_url = message.text.strip()
        await session.commit()
        
    await render_admin_panel(message.chat.id, session, state, bot, index=data.get("current_admin_index", 0), message_id_to_edit=data.get("panel_msg_id"))