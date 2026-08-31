from aiogram.fsm.state import State, StatesGroup

class CreateMatchFSM(StatesGroup):
    """Flujo paso a paso para crear una convocatoria pública"""
    waiting_for_location = State()
    waiting_for_custom_location_name = State()
    waiting_for_custom_location_address = State()
    
    waiting_for_date = State()
    
    # Nuevos estados en dos pasos para el tiempo
    waiting_for_hour = State()
    waiting_for_minute = State()
    
    waiting_for_level_type = State()
    waiting_for_min_level = State()
    waiting_for_max_level = State()
    
    waiting_for_court_status = State()
    waiting_for_court_number = State()