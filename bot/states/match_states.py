from aiogram.fsm.state import State, StatesGroup

class CreateMatchFSM(StatesGroup):
    waiting_for_group = State()
    waiting_for_location = State()
    waiting_for_custom_location_name = State()
    waiting_for_custom_location_address = State()
    waiting_for_date = State()
    waiting_for_hour = State()
    waiting_for_minute = State()
    waiting_for_level_type = State()
    waiting_for_min_level = State()
    waiting_for_max_level = State()
    waiting_for_court_status = State()
    waiting_for_court_number = State()
    confirming_summary = State()