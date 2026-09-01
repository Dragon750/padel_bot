import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    BotCommand, 
    BotCommandScopeAllPrivateChats, 
    BotCommandScopeAllGroupChats
)

from bot.config import config
from bot.database.base import AsyncSessionLocal
from bot.handlers import main_router
from bot.services.scheduler import setup_scheduler
from bot.handlers import match_card

# Configuración de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def set_bot_commands(bot: Bot):
    """Registra los menús de comandos separados por tipo de chat"""
    
    # 1. Comandos EXCLUSIVOS para el CHAT PRIVADO
    private_commands = [
        BotCommand(command="start", description="Iniciar el bot y ver tu nivel"),
        BotCommand(command="crear_privado", description="Registrar un partido cerrado"),
        BotCommand(command="sugerir_ubicacion", description="Proponer una nueva pista")
    ]
    await bot.set_my_commands(
        private_commands, 
        scope=BotCommandScopeAllPrivateChats()
    )

    # 2. Comandos EXCLUSIVOS para GRUPOS (El pueblo)
    group_commands = [
        BotCommand(command="crear", description="Organizar una convocatoria pública")
    ]
    await bot.set_my_commands(
        group_commands, 
        scope=BotCommandScopeAllGroupChats()
    )

async def main():
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Middleware: Inyecta una sesión AsyncSession de SQLAlchemy en cada evento
    @dp.update.middleware()
    async def db_session_middleware(handler, event, data):
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)

    # Registrar el router principal con todos los módulos
    dp.include_router(main_router)
    dp.include_router(match_card.router)
    
    # Configurar menú de comandos y limpiar mensajes pendientes
    await set_bot_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("⏱️ Planificador de tareas en segundo plano iniciado.")

    logger.info("🎾 Bot de Pádel iniciado y escuchando...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())