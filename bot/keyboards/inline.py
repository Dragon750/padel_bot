from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def court_booking_status_kb() -> InlineKeyboardMarkup:
    """Pregunta al final del FSM de creación de partido público"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Sí, ya está reservada", callback_data="book_yes")
    builder.button(text="⏳ No, reservar al llenarse", callback_data="book_no")
    builder.adjust(1)
    return builder.as_markup()

def match_card_kb(match_id: int, is_court_booked: bool, maps_url: str | None) -> InlineKeyboardMarkup:
    """Botonera interactiva principal para la tarjeta en el chat de grupo"""
    builder = InlineKeyboardBuilder()
    
    # Fila 1: Entrar a las parejas
    builder.button(text="🎾 Entrar P1", callback_data=f"join_{match_id}_1")
    builder.button(text="🎾 Entrar P2", callback_data=f"join_{match_id}_2")
    
    # Fila 2: Movilidad y Lista de Espera
    builder.button(text="🔄 Cambiar Pareja", callback_data=f"swap_{match_id}")
    builder.button(text="⏳ Lista de Espera", callback_data=f"waitlist_{match_id}")
    
    # Fila 3: Reserva Colaborativa (Solo si no está reservada aún)
    if not is_court_booked:
        builder.button(text="🎾 Ya tengo pista", callback_data=f"ihavecourt_{match_id}")
    
    # Fila 4: Enlace a Maps y Opción de salida
    if maps_url:
        builder.button(text="📍 Ver Ubicación", url=maps_url)
    builder.button(text="❌ Salirme", callback_data=f"leave_{match_id}")
    
    builder.adjust(2, 2, 1 if not is_court_booked else 0, 2 if maps_url else 1)
    return builder.as_markup()

def score_consensus_kb(match_id: int) -> InlineKeyboardMarkup:
    """Botones enviados por privado a la pareja rival para validar el acta"""
    builder = InlineKeyboardBuilder()
    builder.button(text="👍 Confirmar", callback_data=f"consensus_ok_{match_id}")
    builder.button(text="⚠️ Disputar", callback_data=f"consensus_ko_{match_id}")
    builder.adjust(2)
    return builder.as_markup()

def fcfs_alert_kb(match_id: int) -> InlineKeyboardMarkup:
    """Botón push para urgencias <= 60 minutos (Transacción atómica)"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⚡ Ocupar Plaza Libre", callback_data=f"fcfs_take_{match_id}")
    return builder.as_markup()