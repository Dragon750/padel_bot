import logging
from datetime import datetime, timedelta
from aiogram import Bot
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.base import AsyncSessionLocal
from bot.database.models import Match, MatchPlayer, User
from bot.services.rating import update_team_ratings

logger = logging.getLogger(__name__)

async def check_cancellations(bot: Bot):
    """Vigilante 1: Elimina partidos a T-15min si no hay pista o faltan jugadores"""
    now = datetime.now()
    upper_limit = now + timedelta(minutes=25)
    lower_limit = now + timedelta(minutes=15)
    
    async with AsyncSessionLocal() as session:
        stmt = select(Match).where(
            Match.status.in_(["OPEN", "FULL"]),
            Match.datetime >= lower_limit,
            Match.datetime < upper_limit
        )
        matches = (await session.execute(stmt)).scalars().all()
        
        for match in matches:
            stmt_players = select(func.count()).select_from(MatchPlayer).where(MatchPlayer.match_id == match.id)
            players_count = await session.scalar(stmt_players)
            
            if not match.is_court_booked or players_count < 4:
                manager_id = match.manager_id
                match_id = match.id
                chat_id = match.chat_id
                message_id = match.message_id
                
                # 1. Borrar la tarjeta del grupo
                if chat_id and message_id:
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id, message_id=message_id,
                            text=f"❌ <b>CONVOCATORIA #{match_id} CANCELADA</b>\n\nLa convocatoria ha sido retirada porque no se completaron las 4 plazas o no se confirmó la pista a tiempo."
                        )
                    except Exception: pass
                
                # 2. Eliminar de BD para limpiar estadísticas
                await session.delete(match)
                await session.commit()
                
                # 3. Notificar al organizador
                try:
                    await bot.send_message(
                        manager_id,
                        f"❌ <b>PARTIDO #{match_id} CANCELADO</b>\n\nTu convocatoria fue eliminada del sistema porque no se llenaron las plazas o no hubo reserva a falta de 15 min."
                    )
                except Exception: pass


async def request_scores(bot: Bot):
    """Vigilante 2: Pide el acta al gestor 2.5h después de la hora de inicio"""
    now = datetime.now()
    upper_limit = now - timedelta(hours=2.4)
    lower_limit = now - timedelta(hours=3.0)

    async with AsyncSessionLocal() as session:
        stmt = select(Match).where(
            Match.status == "FULL",
            Match.datetime >= lower_limit,
            Match.datetime < upper_limit
        )
        matches = (await session.execute(stmt)).scalars().all()

        for match in matches:
            try:
                await bot.send_message(
                    chat_id=match.manager_id,
                    text=f"🔔 <b>RECORDATORIO DE ACTA</b>\n\n"
                         f"El partido #{match.id} debería haber finalizado.\n"
                         f"Por favor, registra el resultado enviando esto por aquí:\n\n"
                         f"<code>/marcador {match.id} 6-4 6-3</code>"
                )
            except Exception: pass


async def auto_close_matches(bot: Bot):
    """Vigilante 3: Cierra tácitamente partidos si pasan 24h en validación sin disputa"""
    now = datetime.now()
    limit = now - timedelta(hours=24)

    async with AsyncSessionLocal() as session:
        stmt = select(Match).where(
            Match.status == "VALIDATING",
            Match.datetime < limit
        )
        matches = (await session.execute(stmt)).scalars().all()

        for match in matches:
            # Tolerancia por si la columna se llama result_p1 o result en tu DB
            score_str = getattr(match, "result_p1", getattr(match, "result", None))
            if not score_str:
                continue

            t1_sets, t2_sets = 0, 0
            for s in score_str.split():
                g1, g2 = map(int, s.split("-"))
                if g1 > g2: t1_sets += 1
                elif g2 > g1: t2_sets += 1

            stmt_p = select(MatchPlayer, User).join(User).where(MatchPlayer.match_id == match.id)
            players_data = (await session.execute(stmt_p)).all()

            t1, t2 = [], []
            for mp, u in players_data:
                info = (u.telegram_id, u.level, u.matches_played)
                if mp.team == 1: t1.append(info)
                else: t2.append(info)

            # Matemáticas
            updated_ratings = update_team_ratings(t1, t2, t1_sets, t2_sets)

            for mp, u in players_data:
                u.level = updated_ratings.get(u.telegram_id, u.level)
                u.matches_played += 1
                mp.has_confirmed_result = True

            match.status = "PLAYED"
            await session.commit()
            
            # Avisos
            for mp, u in players_data:
                try:
                    await bot.send_message(u.telegram_id, f"✅ <b>PARTIDO #{match.id} CERRADO</b>\n\nHan pasado 24h sin disputas. El marcador {score_str} se validó tácitamente y los niveles fueron actualizados.")
                except Exception: pass