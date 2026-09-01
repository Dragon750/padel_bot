from datetime import datetime, timedelta, date
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.database.models import Location

def build_locations_keyboard(locations: list[Location]) -> InlineKeyboardMarkup:
    """Catálogo de pistas con opción de cancelar la creación."""
    builder = InlineKeyboardBuilder()
    
    for loc in locations:
        icon = "📍" if loc.is_approved else "❓"
        builder.button(text=f"{icon} {loc.name}", callback_data=f"loc_{loc.id}")
        
    builder.button(text="➕ Otra ubicación (Escribir manual)", callback_data="loc_manual")
    builder.button(text="❌ Cancelar", callback_data="cancel_creation") # NUEVO BOTÓN
    
    builder.adjust(1)
    return builder.as_markup()


def build_dates_keyboard() -> InlineKeyboardMarkup:
    """Genera 6 botones: Hoy, Mañana y los 4 días siguientes."""
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    
    for i in range(6):
        date_obj = today + timedelta(days=i)
        
        if i == 0:
            label = "Hoy"
        elif i == 1:
            label = "Mañana"
        else:
            dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            label = f"{dias[date_obj.weekday()]} {date_obj.day}"
            
        date_str = date_obj.strftime("%Y-%m-%d")
        builder.button(text=label, callback_data=f"date_{date_str}")
        
    # Botón para volver al paso anterior (Ubicación)
    builder.button(text="🔙 Volver a Ubicación", callback_data="back_to_location")
    
    # Ajustamos: 2 botones por fila para las fechas, y el de volver en su propia fila
    builder.adjust(2, 2, 2, 1) 
    return builder.as_markup()


def build_hours_keyboard(selected_date: date) -> InlineKeyboardMarkup:
    """Genera botones de hora desde las 07h hasta las 22h."""
    builder = InlineKeyboardBuilder()
    now = datetime.now()
    
    for h in range(7, 23):
        if selected_date == now.date():
            if h == now.hour and now.minute < 45:
                pass 
            elif h < now.hour or (h == now.hour and now.minute >= 45):
                continue
                
        builder.button(text=f"{h:02d}h", callback_data=f"hour_{h}")
        
    # Botón para volver al paso anterior (Fecha)
    builder.button(text="🔙 Volver a Fecha", callback_data="back_to_date")
    
    # Ajustamos para que las horas salgan de 4 en 4, pero protegiendo el último botón
    builder.adjust(4) 
    return builder.as_markup()


def build_minutes_keyboard(selected_hour: int, selected_date: date) -> InlineKeyboardMarkup:
    """Genera botones de 15 minutos (00, 15, 30, 45)."""
    builder = InlineKeyboardBuilder()
    now = datetime.now()
    
    minutes = [0, 15, 30, 45]
    
    for m in minutes:
        if selected_date == now.date() and selected_hour == now.hour and m <= now.minute:
            continue
            
        time_str = f"{selected_hour:02d}:{m:02d}"
        builder.button(text=time_str, callback_data=f"time_{time_str}")
        
    builder.button(text="🔙 Volver a elegir hora", callback_data="back_to_hours")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def build_level_types_keyboard() -> InlineKeyboardMarkup:
    """Bloques fijos y opción de nivel personalizado con botón de retroceso."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Abierto (0.0 - 6.0)", callback_data="lvl_0.0_6.0")
    builder.button(text="Iniciación (1.0 - 2.5)", callback_data="lvl_1.0_2.5")
    builder.button(text="Intermedio (2.5 - 4.0)", callback_data="lvl_2.5_4.0")
    builder.button(text="Avanzado (4.0 - 6.0)", callback_data="lvl_4.0_6.0")
    builder.button(text="✏️ Personalizado (En 2 pasos)", callback_data="lvl_custom")
    builder.button(text="🔙 Volver a Minutos", callback_data="back_to_minutes") # NUEVO BOTÓN
    builder.adjust(1)
    return builder.as_markup()

def build_back_to_locations_keyboard() -> InlineKeyboardMarkup:
    """Para cuando el usuario está escribiendo una pista manual."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Volver a Ubicaciones", callback_data="back_to_location")
    return builder.as_markup()

def build_back_to_levels_keyboard() -> InlineKeyboardMarkup:
    """Para el paso 1 del nivel personalizado (mínimo)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Volver a Niveles", callback_data="back_to_levels")
    return builder.as_markup()

def build_address_keyboard() -> InlineKeyboardMarkup:
    """Teclado para pedir la dirección con opción de omitir."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏩ Omitir enlace (Añadir más tarde)", callback_data="skip_address")
    builder.button(text="🔙 Volver a Ubicaciones", callback_data="back_to_location")
    builder.adjust(1)
    return builder.as_markup()

def build_back_to_min_level_keyboard() -> InlineKeyboardMarkup:
    """Teclado para volver al paso 1 del nivel personalizado (mínimo)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Volver a Nivel Mínimo", callback_data="back_to_min_level")
    return builder.as_markup()

def build_court_status_keyboard() -> InlineKeyboardMarkup:
    """Teclado para confirmar si la pista está reservada, con opción de volver."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Sí, ya está reservada", callback_data="book_yes")
    builder.button(text="⏳ No, reservar al llenarse", callback_data="book_no")
    
    # Este callback_data conectará mágicamente con la función nav_back_to_levels que ya tienes
    builder.button(text="🔙 Volver a Niveles", callback_data="back_to_levels") 
    
    builder.adjust(1) # Pone los botones uno debajo de otro
    return builder.as_markup()