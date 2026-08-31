import difflib
from bot.database.models import Location

def get_similar_locations(
    suggested_name: str, 
    existing_locations: list[Location], 
    threshold: float = 0.75
) -> list[Location]:
    """
    Compara el nombre sugerido con las pistas de la base de datos.
    Devuelve aquellas que tengan una similitud superior al umbral (75%).
    """
    similar = []
    suggested_lower = suggested_name.lower().strip()
    
    for loc in existing_locations:
        loc_lower = loc.name.lower().strip()
        
        # Algoritmo de similitud nativo de Python (Gestalt pattern matching)
        ratio = difflib.SequenceMatcher(None, suggested_lower, loc_lower).ratio()
        
        if ratio >= threshold:
            similar.append(loc)
            
    return similar