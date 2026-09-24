"""Backend form validation (Pydantic). Frontend e-o ekoi rule follow korbe."""
from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Role = Literal["admin", "user"]
AmbulanceType = Literal["basic", "advanced", "icu"]
AmbulanceStatus = Literal["available", "dispatched", "maintenance"]
Priority = Literal["low", "medium", "high", "critical"]
EmergencyStatus = Literal["pending", "dispatched", "en_route", "completed", "cancelled"]

Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?\d{7,15}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=50)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_.]+$")]
Plate = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=3, max_length=20)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=255)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


def check_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes")
    if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        raise ValueError("Password must contain at least one letter and one number")
    return value


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class Message(BaseModel):
    message: str
    reset_token: str | None = None 


class SignupRequest(BaseModel):
    username: Username
    email: EmailStr
    firstname: Name
    lastname: Name
    phone: Phone | None = None
    password: str

    _pw = field_validator("password")(check_password)


class UserCreate(SignupRequest):
    role: Role = "user"


class UserUpdate(BaseModel):
    firstname: Name | None = None
    lastname: Name | None = None
    phone: Phone | None = None
    role: Role | None = None
    is_active: bool | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str

    _pw = field_validator("new_password")(check_password)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    username: str
    firstname: str
    lastname: str
    phone: str | None
    role: str
    is_active: bool
    created_at: datetime


class AmbulanceCreate(BaseModel):
    plate_number: Plate
    driver_name: Name
    driver_phone: Phone
    type: AmbulanceType = "basic"
    status: AmbulanceStatus = "available"
    latitude: Latitude | None = None
    longitude: Longitude | None = None


class AmbulanceUpdate(BaseModel):
    plate_number: Plate | None = None
    driver_name: Name | None = None
    driver_phone: Phone | None = None
    type: AmbulanceType | None = None
    status: AmbulanceStatus | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None


class AmbulanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    plate_number: str
    driver_name: str
    driver_phone: str
    type: str
    status: str
    latitude: float | None
    longitude: float | None
    created_at: datetime


class HospitalCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]
    city: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    address: Address
    phone: Phone
    available_beds: int = Field(0, ge=0, le=10000)


class HospitalUpdate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)] | None = None
    city: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)] | None = None
    address: Address | None = None
    phone: Phone | None = None
    available_beds: int | None = Field(None, ge=0, le=10000)


class HospitalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    city: str
    address: str
    phone: str
    available_beds: int
    created_at: datetime


class EmergencyCreate(BaseModel):
    patient_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    patient_phone: Phone
    address: Address
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    description: Description | None = None
    priority: Priority = "medium"


class EmergencyUpdate(BaseModel):
    patient_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)] | None = None
    patient_phone: Phone | None = None
    address: Address | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    description: Description | None = None
    priority: Priority | None = None


class DispatchRequest(BaseModel):
    ambulance_id: int = Field(gt=0)
    hospital_id: int | None = Field(None, gt=0)


class StatusUpdate(BaseModel):
    status: Literal["en_route", "completed", "cancelled"]


class EmergencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_name: str
    patient_phone: str
    address: str
    latitude: float | None
    longitude: float | None
    description: str | None
    priority: str
    status: str
    requested_by: int | None
    ambulance_id: int | None
    hospital_id: int | None
    ambulance: AmbulanceOut | None
    hospital: HospitalOut | None
    created_at: datetime
    updated_at: datetime
    dispatched_at: datetime | None
    completed_at: datetime | None
