from aiogram import Router
from . import start, admin, create_match, match_card, match_score

# Creamos un router principal que agrupa a todos los demás
main_router = Router()

main_router.include_router(start.router)
main_router.include_router(admin.router)
main_router.include_router(create_match.router)
main_router.include_router(match_card.router)
main_router.include_router(match_score.router)