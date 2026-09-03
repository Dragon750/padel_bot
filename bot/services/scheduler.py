import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.database.base import AsyncSessionLocal
from bot.database.models import Match, MatchPlayer

logger = logging.getLogger(__name__)

async def check_cancellations(bot: Bot):
    """Vigilante: Elimina partidos a T-15min si no hay pista o faltan jugadores"""
    now = datetime.now()
    upper_limit = now + timedelta(minutes=25)
    lower_limit = now + timedelta(minutes=15)
    
    async with AsyncSessionLocal() as session:
        stmt = select(Match).where(
            Match.status.in_(["OPEN", "FULL"]),
            Match.datetime >= lower_limit,
            Match.datetime < upper_limit
        )
        result = await session.execute(stmt)
        matches = result.scalars().all()
        
        for match in matches:
            stmt_players = select(func.count()).select_from(MatchPlayer).where(MatchPlayer.match_id == match.id)
            players_count = await session.scalar(stmt_players)
            
            # Condición: no se completó o no hay pista confirmada
            if not match.is_court_booked or players_count < 4:
                manager_id = match.manager_id
                match_id = match.id
                chat_id = match.chat_id
                message_id = match.message_id
                
                # 1. Actualizar la tarjeta pública en el grupo
                if chat_id and message_id:
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=f"❌ <b>CONVOCATORIA #{match_id} CANCELADA</b>\n\n"
                                 f"La convocatoria ha sido cancelada y retirada porque no se completaron las 4 plazas o no se confirmó la pista física a tiempo."
                        )
                    except Exception:
                        pass
                
                # 2. Borrado físico en la base de datos para no ensuciar estadísticas
                await session.delete(match)
                await session.commit()
                
                # 3. Notificar al organizador
                try:
                    await bot.send_message(
                        manager_id,
                        f"❌ <b>PARTIDO #{match_id} CANCELADO</b>\n\n"
                        f"Tu convocatoria ha sido cancelada y eliminada del sistema porque no se llenaron las plazas o no se confirmó la reserva a falta de 15 minutos."
                    )
                except Exception as e:
                    logger.error(f"Error al notificar cancelación al manager: {e}")

                    
async def remind_scores(bot: Bot):
    """Cobrador: Avisa al gestor a T+1.5h (Instrucciones) y T+2.5h (Recordatorio)"""
    now = datetime.now()
    
    # 1. Ventana del Primer Aviso (T + 1.5h) - Instrucciones de fin de partido
    upper_limit_1 = now - timedelta(hours=1, minutes=30)
    lower_limit_1 = upper_limit_1 - timedelta(minutes=10)
    
    # 2. Ventana del Segundo Aviso (T + 2.5h) - Recordatorio anti-olvidos
    upper_limit_2 = now - timedelta(hours=2, minutes=30)
    lower_limit_2 = upper_limit_2 - timedelta(minutes=10)
    
    async with AsyncSessionLocal() as session:
        
        # ==========================================
        # PRIMER AVISO (Instrucciones)
        # ==========================================
        stmt_1 = select(Match).where(
            Match.status == "FULL", 
            Match.datetime <= upper_limit_1,
            Match.datetime > lower_limit_1
        )
        matches_1 = (await session.execute(stmt_1)).scalars().all()
        
        for match in matches_1:
            try:
                await bot.send_message(
                    match.manager_id,
                    f"🔔 <b>FIN DEL PARTIDO</b>\n\n"
                    f"¡Esperamos que el partido #{match.id} haya ido genial!\n"
                    f"Como gestor de la convocatoria, por favor introduce el resultado oficial por sets para actualizar los niveles.\n\n"
                    f"Copia, completa y envía este comando:\n"
                    f"<code>/marcador {match.id} 6-4 6-3</code>"
                )
            except Exception as e:
                logger.error(f"Error al enviar primer aviso de marcador (Match {match.id}): {e}")

        # ==========================================
        # SEGUNDO AVISO (Recordatorio tardío)
        # ==========================================
        stmt_2 = select(Match).where(
            Match.status == "FULL", 
            Match.datetime <= upper_limit_2,
            Match.datetime > lower_limit_2
        )
        matches_2 = (await session.execute(stmt_2)).scalars().all()
        
        for match in matches_2:
            try:
                await bot.send_message(
                    match.manager_id,
                    f"⚠️ <b>RECORDATORIO DE MARCADOR</b>\n\n"
                    f"Ha pasado una hora desde que finalizó el partido #{match.id} y aún no tenemos el acta.\n"
                    f"Por favor, no olvides subirlo para que podamos recalcular el nivel de los jugadores:\n\n"
                    f"<code>/marcador {match.id} 6-4 6-3</code>"
                )
            except Exception as e:
                logger.error(f"Error al enviar recordatorio tardío de marcador (Match {match.id}): {e}")


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Configura y devuelve el planificador con la zona horaria correcta"""
    # Usamos la zona horaria definida en el despliegue de Render/Railway
    scheduler = AsyncIOScheduler(timezone="Europe/Madrid") 
    
    # Ejecutamos las revisiones cada 10 minutos
    scheduler.add_job(check_cancellations, 'interval', minutes=10, args=[bot])
    scheduler.add_job(remind_scores, 'interval', minutes=10, args=[bot])
    
    return scheduler