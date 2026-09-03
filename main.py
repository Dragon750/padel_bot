import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import config
from bot.database.base import AsyncSessionLocal
from bot.handlers import main_router
from bot.services.scheduler import check_cancellations, request_scores, auto_close_matches

# Configuración de logs para ver qué pasa en Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from aiogram.types import (
    BotCommand, 
    BotCommandScopeAllPrivateChats, 
    BotCommandScopeAllGroupChats
)

from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
    BotCommandScopeChat
)

async def set_bot_commands(bot: Bot):
    """Configura la visibilidad estricta de comandos según chat y privilegios."""
    
    # 1. ELIMINAR el catálogo global por defecto (para que nadie herede comandos)
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    
    # 2. ELIMINAR comandos de los GRUPOS (el menú '/' queda vacío en grupos)
    await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())

    # 3. Comandos para USUARIOS NORMALES en chat privado (SIN /panel)
    user_commands = [
        BotCommand(command="start", description="Ver mi perfil y nivel"),
        BotCommand(command="crear", description="Convocar partido público"),
        BotCommand(command="crear_privado", description="Registrar acta de partido privado"),
        BotCommand(command="sugerir_ubicacion", description="Proponer una nueva pista")
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeAllPrivateChats())

    # 4. Comandos EXCLUSIVOS para el ADMINISTRADOR (con /panel)
    if config.ADMIN_TELEGRAM_ID:
        admin_commands = user_commands + [
            BotCommand(command="panel", description="Panel de moderación de pistas")
        ]
        await bot.set_my_commands(
            admin_commands, 
            scope=BotCommandScopeChat(chat_id=config.ADMIN_TELEGRAM_ID)
        )

async def main():
    # Instanciamos el bot con parseo HTML por defecto
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Middleware: Inyecta la sesión de DB en cada clic o mensaje automáticamente
    @dp.update.middleware()
    async def db_session_middleware(handler, event, data):
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)

    # Conectamos todos los controladores
    dp.include_router(main_router)

    # ---------------------------------------------------------
    # CONFIGURACIÓN DEL PLANIFICADOR DE TAREAS (APScheduler)
    # ---------------------------------------------------------
    scheduler = AsyncIOScheduler(timezone=config.TZ)
    # 1. Busca partidos por cancelar cada 5 minutos
    scheduler.add_job(check_cancellations, 'interval', minutes=5, args=[bot])
    # 2. Busca partidos para pedir acta cada 30 minutos
    scheduler.add_job(request_scores, 'interval', minutes=30, args=[bot])
    # 3. Busca partidos para cerrar tácitamente cada 1 hora
    scheduler.add_job(auto_close_matches, 'interval', hours=1, args=[bot])
    
    scheduler.start()
    logger.info("⏰ Tareas programadas iniciadas correctamente.")

    # ---------------------------------------------------------
    # ARRANQUE DE TELEGRAM
    # ---------------------------------------------------------
    await set_bot_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True) # Ignora mensajes viejos al reiniciar
    
    logger.info("🎾 Bot de Pádel iniciado y escuchando...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())