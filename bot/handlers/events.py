from aiogram import Router, F
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.types import ChatMemberUpdated, Message
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import GroupChat

router = Router()

@router.my_chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_bot_added_to_group(event: ChatMemberUpdated, session: AsyncSession):
    """Guarda o reactiva el grupo cuando añaden al bot."""
    group = await session.get(GroupChat, event.chat.id)
    if not group:
        group = GroupChat(chat_id=event.chat.id, title=event.chat.title)
        session.add(group)
    else:
        group.title = event.chat.title
        group.is_active = True
    await session.commit()

@router.my_chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION))
async def on_bot_removed_from_group(event: ChatMemberUpdated, session: AsyncSession):
    """Desactiva el grupo si expulsan al bot."""
    group = await session.get(GroupChat, event.chat.id)
    if group:
        group.is_active = False
        await session.commit()

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.startswith("/"))
async def auto_delete_group_commands(message: Message):
    """Elimina cualquier comando escrito manualmente en un grupo para evitar spam."""
    try:
        await message.delete()
    except Exception:
        pass