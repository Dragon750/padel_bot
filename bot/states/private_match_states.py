from aiogram.fsm.state import State, StatesGroup

class PrivateMatchFSM(StatesGroup):
    """Flujo paso a paso para agendar o registrar partidos cerrados"""
    waiting_for_date = State()
    
    waiting_for_hour = State()
    waiting_for_minute = State()  
      
    # Asignación de integrantes
    waiting_for_p1_partner = State()
    waiting_for_p2_player1 = State()
    waiting_for_p2_player2 = State()
    
    # Exclusivo para partidos del pasado (< 24h)
    waiting_for_score = State()
    
    confirming_summary = State()