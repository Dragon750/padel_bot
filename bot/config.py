from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    ADMIN_TELEGRAM_ID: int
    TZ: str = "Europe/Madrid"

    # Configuración para leer desde un archivo .env en local
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# Instancia global para importar en el resto del proyecto
config = Settings()