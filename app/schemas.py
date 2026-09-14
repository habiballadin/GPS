from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class RegisterIn(BaseModel):
    organization_name: str = Field(min_length=2, max_length=160)
    email: str
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None
    expires_in: int | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    password: str = Field(min_length=8)


class InvitationAccept(BaseModel):
    token: str
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    organization_id: int
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: Literal["admin", "manager", "operator", "viewer"] = "operator"


class UserRolePatch(BaseModel):
    role: Literal["admin", "manager", "operator", "viewer"]


class InvitationCreate(BaseModel):
    email: str
    role: Literal["admin", "manager", "operator", "viewer"] = "operator"


class VehicleIn(BaseModel):
    name: str
    imei: str = Field(min_length=8, max_length=32)
    license_plate: str | None = None
    protocol: str = "teltonika"


class VehicleOut(VehicleIn):
    id: int
    active: bool
    last_seen_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class VehiclePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    license_plate: str | None = None
    protocol: str | None = None
    active: bool | None = None


class AssignmentIn(BaseModel):
    driver_id: int


class AssignmentOut(AssignmentIn):
    id: int
    vehicle_id: int
    assigned_at: datetime
    ended_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class MaintenanceIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    status: str = "planned"
    description: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PositionOut(BaseModel):
    vehicle_id: int
    device_imei: str
    recorded_at: datetime
    latitude: float
    longitude: float
    speed_kph: float
    heading: float
    ignition: bool
    satellites: int
    model_config = ConfigDict(from_attributes=True)


class DriverIn(BaseModel):
    name: str
    phone: str | None = None
    license_number: str | None = None


class DriverOut(DriverIn):
    id: int
    active: bool
    model_config = ConfigDict(from_attributes=True)


class TripIn(BaseModel):
    reference: str
    vehicle_id: int | None = None
    driver_id: int | None = None
    origin: str | None = None
    destination: str | None = None
    scheduled_at: datetime | None = None


class TripOut(TripIn):
    id: int
    status: str
    model_config = ConfigDict(from_attributes=True)


class GeofenceIn(BaseModel):
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: float = Field(gt=0, le=1_000_000)


class GeofenceOut(GeofenceIn):
    id: int
    active: bool
    model_config = ConfigDict(from_attributes=True)


RESOURCE_TYPES = Literal[
    "trailers", "equipment", "devices", "orders", "routes", "stops", "teams", "shifts",
    "certifications", "availability", "work-orders", "service-plans", "inspections", "parts",
    "vendors", "events", "incidents", "driver-safety", "investigations", "corrective-actions",
    "fuel", "costs", "reports", "analytics", "exports", "documents", "integrations",
    "notifications", "organization", "users", "roles", "api-keys", "ai", "geofences",
    "dispatch", "maintenance", "safety", "finance", "settings", "telematics", "orders", "audit"
]


class ResourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    status: str = Field(default="active", max_length=40)
    description: str | None = Field(default=None, max_length=5000)
    details: dict[str, Any] = Field(default_factory=dict)


class ResourcePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    status: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=5000)
    details: dict[str, Any] | None = None


class ResourceOut(ResourceIn):
    id: int
    resource_type: str
    organization_id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
