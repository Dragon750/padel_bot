from aiogram.fsm.state import State, StatesGroup

class MatchActionFSM(StatesGroup):
    waiting_for_collab_court = State()