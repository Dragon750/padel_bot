from aiogram import Router
from bot.handlers import start, admin, create_match, match_card, private_match, score, events

main_router = Router()

main_router.include_router(start.router)
main_router.include_router(admin.router)
main_router.include_router(events.router)
main_router.include_router(create_match.router)
main_router.include_router(match_card.router)
main_router.include_router(private_match.router)
main_router.include_router(score.router)