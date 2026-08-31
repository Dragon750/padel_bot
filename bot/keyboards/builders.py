from datetime import datetime, date
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.database.models import Location

def build_locations_keyboard(locations: list[Location]) -> InlineKeyboardMarkup:
    """Genera botones con chincheta para aprobadas y exclamación para pendientes"""
    builder = InlineKeyboardBuilder()
    
    for loc in locations:
        icon = "📍" if loc.is_approved else "❓"
        builder.button(text=f"{icon} {loc.name}", callback_data=f"loc_{loc.id}")
        
    # Botón para entrada manual
    builder.button(text="➕ Otra ubicación (Escribir manual)", callback_data="loc_manual")
    builder.adjust(1) # 1 botón por fila
    return builder.as_markup()


def build_dates_keyboard() -> InlineKeyboardMarkup:
    """Genera botones para Hoy y los próximos 5 días"""
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    
    for i in range(6):
        date_obj = today + timedelta(days=i)
        
        if i == 0:
            label = "Hoy"
        elif i == 1:
            label = "Mañana"
        else:
            # Ej: Jueves 15
            dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            label = f"{dias[date_obj.weekday()]} {date_obj.day}"
            
        date_str = date_obj.strftime("%Y-%m-%d")
        builder.button(text=label, callback_data=f"date_{date_str}")
        
    builder.adjust(2) # 2 botones por fila
    return builder.as_markup()


def build_hours_keyboard(selected_date: date) -> InlineKeyboardMarkup:
    """Genera botones de hora desde las 07h hasta las 22h."""
    builder = InlineKeyboardBuilder()
    now = datetime.now()
    
    for h in range(7, 23):
        # Filtrar horas pasadas si el partido es para "Hoy"
        if selected_date == now.date():
            # Si es la hora actual, la mostramos solo si aún quedan minutos jugables (antes del :45)
            if h == now.hour and now.minute < 45:
                pass 
            elif h < now.hour or (h == now.hour and now.minute >= 45):
                continue
                
        builder.button(text=f"{h:02d}h", callback_data=f"hour_{h}")
        
    builder.adjust(4) # Muestra 4 botones por fila para hacer un bloque ordenado
    return builder.as_markup()


def build_minutes_keyboard(selected_hour: int, selected_date: date) -> InlineKeyboardMarkup:
    """Genera botones de 15 minutos (00, 15, 30, 45) para la hora elegida."""
    builder = InlineKeyboardBuilder()
    now = datetime.now()
    
    minutes = [0, 15, 30, 45]
    
    for m in minutes:
        # Filtrar minutos pasados si es "Hoy" y estamos en la hora actual
        if selected_date == now.date() and selected_hour == now.hour and m <= now.minute:
            continue
            
        time_str = f"{selected_hour:02d}:{m:02d}"
        builder.button(text=time_str, callback_data=f"time_{time_str}")
        
    # Botón extra por si el usuario se ha equivocado al elegir la hora principal
    builder.button(text="🔙 Volver a elegir hora", callback_data="back_to_hours")
    
    builder.adjust(2, 2, 1) # 2 filas de 2 minutos, y el botón de volver abajo
    return builder.as_markup()


def build_level_types_keyboard() -> InlineKeyboardMarkup:
    """Bloques fijos y opción de nivel personalizado"""
    builder = InlineKeyboardBuilder()
    builder.button(text="Abierto (0.0 - 6.0)", callback_data="lvl_0.0_6.0")
    builder.button(text="Iniciación (1.0 - 2.5)", callback_data="lvl_1.0_2.5")
    builder.button(text="Intermedio (2.5 - 4.0)", callback_data="lvl_2.5_4.0")
    builder.button(text="Avanzado (4.0 - 6.0)", callback_data="lvl_4.0_6.0")
    builder.button(text="✏️ Personalizado (En 2 pasos)", callback_data="lvl_custom")
    builder.adjust(1)
    return builder.as_markup()