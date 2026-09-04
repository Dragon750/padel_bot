import datetime as dt
from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from bot.database.base import Base

class GroupChat(Base):
    __tablename__ = "group_chats"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)

class User(Base):
    """Jugadores registrados en el bot con métricas para el ratio y rating"""
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128))
    level: Mapped[float] = mapped_column(Float, default=2.5)  # Rango 0.0 a 6.0
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    matches_played: Mapped[int] = mapped_column(Integer, default=0)
    late_cancellations: Mapped[int] = mapped_column(Integer, default=0)


class Location(Base):
    """Catálogo de pistas. Sin horarios fijos por flexibilidad"""
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    maps_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    suggested_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)


class Match(Base):
    """Convocatorias públicas y partidos privados"""
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manager_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("locations.id"), nullable=False)
    
    # Usamos dt.datetime para evitar colisión con el nombre del campo
    datetime: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    min_level: Mapped[float] = mapped_column(Float, default=0.0)
    max_level: Mapped[float] = mapped_column(Float, default=6.0)
    status: Mapped[str] = mapped_column(String(20), default="OPEN") 
    result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Gestión de pista
    is_court_booked: Mapped[bool] = mapped_column(Boolean, default=False)
    court_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    booked_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Referencias del mensaje en el grupo
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    
    # Timestamp generado por la base de datos
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

class MatchPlayer(Base):
    __tablename__ = "match_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    team: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 o 2
    has_confirmed_result: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("match_id", "user_id", name="uq_match_user"),
    )


class MatchWaitlist(Base):
    """Lista de espera individual"""
    __tablename__ = "match_waitlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer, ForeignKey("matches.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    joined_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())