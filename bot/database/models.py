from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from bot.database.base import Base

class GroupChat(Base):
    __tablename__ = "group_chats"

    chat_id: Mapped[int] = mapped_column(BigInt, primary_key=True)
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
    manager_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    location_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("locations.id"), nullable=True)
    
    datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    min_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # OPEN, FULL, VALIDATING, PLAYED, CANCELLED, DISPUTED
    status: Mapped[str] = mapped_column(String(20), default="OPEN") 
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Gestión de Reserva Colaborativa
    is_court_booked: Mapped[bool] = mapped_column(Boolean, default=False)
    court_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    booked_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    
    # Marcador (ej: "6-4 3-6 7-6") y motivos de cancelación (ej: "CLUB_CANCELLED")
    result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Referencias de mensaje interactivo en grupo
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MatchPlayer(Base):
    """Participantes de un partido (Usuarios registrados o invitados externos)"""
    __tablename__ = "match_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer, ForeignKey("matches.id", ondelete="CASCADE"))
    
    # Identificación y propiedad de plaza
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    guest_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registered_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    
    team: Mapped[int] = mapped_column(Integer)  # 1 (Pareja 1) o 2 (Pareja 2)
    has_confirmed_result: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MatchWaitlist(Base):
    """Lista de espera individual"""
    __tablename__ = "match_waitlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer, ForeignKey("matches.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())