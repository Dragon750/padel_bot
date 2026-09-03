from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import GroupChat

async def get_user_common_groups(bot: Bot, session: AsyncSession, user_id: int) -> list[GroupChat]:
    """Retorna solo los grupos donde tanto el bot como el usuario son miembros activos."""
    stmt = select(GroupChat).where(GroupChat.is_active == True)
    result = await session.execute(stmt)
    all_groups = result.scalars().all()

    valid_groups = []
    for g in all_groups:
        try:
            member = await bot.get_chat_member(chat_id=g.chat_id, user_id=user_id)
            # Solo si el usuario es miembro activo, admin o creador del grupo
            if member.status in ["creator", "administrator", "member"]:
                valid_groups.append(g)
        except Exception:
            # Si el usuario no pertenece o el bot perdió acceso
            continue

    return valid_groups