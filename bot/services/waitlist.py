from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import MatchWaitlist, User

def calculate_reliability_ratio(late_cancellations: int, matches_played: int) -> float:
    """Calcula proporcionalmente la penalización por bajas."""
    return late_cancellations / (matches_played + 1)


async def get_next_in_waitlist(match_id: int, session: AsyncSession) -> MatchWaitlist | None:
    """
    Devuelve el siguiente usuario en la cola de un partido, ordenado por:
    1. Mejor ratio de confiabilidad (Menor penalización ASC).
    2. Orden cronológico en el que se apuntó (joined_at ASC).
    """
    stmt = (
        select(MatchWaitlist)
        .join(User, MatchWaitlist.user_id == User.telegram_id)
        .where(MatchWaitlist.match_id == match_id)
        .order_by(
            # Ordenación por ratio calculado a nivel de base de datos
            (User.late_cancellations * 1.0 / (User.matches_played + 1)).asc(),
            MatchWaitlist.joined_at.asc()
        )
        .limit(1)
    )
    
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_waitlisted_users(match_id: int, session: AsyncSession) -> list[MatchWaitlist]:
    """
    Devuelve a todos los usuarios en lista de espera de un partido.
    Se utilizará para la Fase FCFS de Emergencia (envío de alertas push masivas).
    """
    stmt = select(MatchWaitlist).where(MatchWaitlist.match_id == match_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())