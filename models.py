import datetime

from database import Base
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship


class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    firstname = Column(String)
    lastname = Column(String)
    phone = Column(String, nullable=True)
    hash_password = Column(String)
    is_active = Column(Boolean, default=True)
    role = Column(String, default="user", index=True)  # admin or user
    created_at = Column(DateTime, default=datetime.datetime.now, index=True)


class RefreshTokens(Base):
    """Refresh token rotate/revoke korar jonno DB te rakha hoy."""
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    expires_at = Column(DateTime)
    revoked = Column(Boolean, default=False)


class PasswordResets(Base):
    """Shudhu token er SHA-256 hash save hoy, raw token na."""
    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    token_hash = Column(String, unique=True, index=True)
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)


class Ambulances(Base):
    __tablename__ = "ambulances"

    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String, unique=True, index=True)
    driver_name = Column(String)
    driver_phone = Column(String)
    type = Column(String, default='basic', index=True)        
    status = Column(String, default='available', index=True)   
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now, index=True)


class Hospitals(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    city = Column(String, index=True)
    address = Column(String)
    phone = Column(String)
    available_beds = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.now, index=True)


class Emergencies(Base):
    __tablename__ = "emergencies"

    id = Column(Integer, primary_key=True, index=True)
    patient_name = Column(String, index=True)
    patient_phone = Column(String)
    address = Column(String)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    priority = Column(String, default='medium', index=True)  
    status = Column(String, default='pending', index=True)   

    requested_by = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    ambulance_id = Column(Integer, ForeignKey('ambulances.id'), nullable=True, index=True)
    hospital_id = Column(Integer, ForeignKey('hospitals.id'), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
    dispatched_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    ambulance = relationship("Ambulances", lazy="joined")
    hospital = relationship("Hospitals", lazy="joined")
