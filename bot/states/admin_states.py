from aiogram.fsm.state import State, StatesGroup

class AdminPanelFSM(StatesGroup):
    viewing_panel = State()
    waiting_for_new_name = State()
    waiting_for_new_url = State()