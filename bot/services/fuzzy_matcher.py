import unicodedata
import difflib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Location

def normalize_text(text: str) -> str:
    """Elimina tildes, signos y normaliza a minúsculas."""
    text = text.lower().strip()
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")

async def get_similar_locations(session: AsyncSession, name: str, threshold: float = 0.75) -> list[tuple[Location, float]]:
    """
    Busca todas las pistas con una similitud >= al umbral (75%).
    Devuelve una lista de tuplas (Location, porcentaje) ordenada de mayor a menor.
    """
    result = await session.execute(select(Location))
    all_locations = result.scalars().all()
    
    similar = []
    norm_name = normalize_text(name)
    
    for loc in all_locations:
        norm_loc = normalize_text(loc.name)
        # Algoritmo de similitud nativo de Python (Gestalt pattern matching)
        ratio = difflib.SequenceMatcher(None, norm_name, norm_loc).ratio()
        
        if ratio >= threshold:
            similar.append((loc, ratio))
            
    # Ordenar por el porcentaje más alto
    similar.sort(key=lambda x: x[1], reverse=True)
    return similar