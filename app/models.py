from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean, UniqueConstraint, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def now():
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    users = relationship("User", back_populates="organization")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40), default="admin")
    organization = relationship("Organization", back_populates="users")


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OneTimeToken(Base):
    __tablename__ = "one_time_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (UniqueConstraint("organization_id", "imei"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    license_plate: Mapped[str | None] = mapped_column(String(40), nullable=True)
    imei: Mapped[str] = mapped_column(String(32), index=True)
    protocol: Mapped[str] = mapped_column(String(30), default="teltonika")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_profile: Mapped[str] = mapped_column(String(40), default="standard")
    device_profile_config: Mapped[dict] = mapped_column(JSON, default=dict)
    # Configurable alert thresholds (stored in JSON for flexibility)
    overspeed_kph: Mapped[int] = mapped_column(Integer, default=120)
    idle_alert_minutes: Mapped[int] = mapped_column(Integer, default=10)
    # Scheduled immobilizer: "HH:MM-HH:MM" e.g. "22:00-06:00" means cut outside those hours
    immobilizer_schedule: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vehicle_type: Mapped[str] = mapped_column(String(30), default="car")


class FleetAsset(Base):
    """Non-vehicle fleet assets such as trailers and powered equipment."""
    __tablename__ = "fleet_assets"
    __table_args__ = (UniqueConstraint("organization_id", "asset_tag"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    asset_tag: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(180))
    asset_type: Mapped[str] = mapped_column(String(40), default="equipment")
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vin: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ownership: Mapped[str] = mapped_column(String(30), default="owned")
    status: Mapped[str] = mapped_column(String(30), default="active")
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acquisition_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    disposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AssetAttachment(Base):
    __tablename__ = "asset_attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("fleet_assets.id"), index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    detached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("organization_id", "imei"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    imei: Mapped[str] = mapped_column(String(32), index=True)
    protocol: Mapped[str] = mapped_column(String(30), default="teltonika")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SIMCard(Base):
    __tablename__ = "sim_cards"
    __table_args__ = (UniqueConstraint("organization_id", "iccid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True, index=True)
    iccid: Mapped[str] = mapped_column(String(32), index=True)
    imsi: Mapped[str | None] = mapped_column(String(32), nullable=True)
    msisdn: Mapped[str | None] = mapped_column(String(40), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(120), nullable=True)
    apn: Mapped[str | None] = mapped_column(String(120), nullable=True)
    plan_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    data_limit_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_used_mb: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="active")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DeviceBinding(Base):
    __tablename__ = "device_bindings"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    unbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceCommand(Base):
    __tablename__ = "device_commands"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    command: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VehicleAssignment(Base):
    __tablename__ = "vehicle_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Driver(Base):
    __tablename__ = "drivers"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    license_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DriverCertification(Base):
    __tablename__ = "driver_certifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    certificate_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="valid")


class DriverAvailability(Base):
    __tablename__ = "driver_availability"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    available_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="available")


class DriverCoaching(Base):
    __tablename__ = "driver_coaching"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="planned")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Trip(Base):
    __tablename__ = "trips"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    reference: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="planned")
    origin: Mapped[str | None] = mapped_column(String(255), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    contact_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DeliveryOrder(Base):
    """A customer delivery job assigned by a dispatcher and executed through ordered stops."""
    __tablename__ = "delivery_orders"
    __table_args__ = (UniqueConstraint("organization_id", "reference"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True, index=True)
    dispatcher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reference: Mapped[str] = mapped_column(String(100))
    cargo_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cargo_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    status: Mapped[str] = mapped_column(String(30), default="unassigned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DeliveryStop(Base):
    __tablename__ = "delivery_stops"
    __table_args__ = (UniqueConstraint("order_id", "sequence"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("delivery_orders.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    address: Mapped[str] = mapped_column(String(500))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    proof_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeliveryException(Base):
    """An operational exception produced during delivery execution."""
    __tablename__ = "delivery_exceptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("delivery_orders.id"), index=True)
    stop_id: Mapped[int | None] = mapped_column(ForeignKey("delivery_stops.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    message: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Geofence(Base):
    __tablename__ = "geofences"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[float] = mapped_column(Float)
    geofence_type: Mapped[str] = mapped_column(String(20), default="circle")
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    corridor_width_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("device_imei", "event_id"),
        Index("ix_positions_vehicle_recorded", "organization_id", "vehicle_id", "recorded_at"),
        Index("ix_positions_device_recorded", "device_imei", "recorded_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    device_imei: Mapped[str] = mapped_column(String(32), index=True)
    event_id: Mapped[str] = mapped_column(String(120))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    altitude: Mapped[float] = mapped_column(Float, default=0)
    speed_kph: Mapped[float] = mapped_column(Float, default=0)
    heading: Mapped[float] = mapped_column(Float, default=0)
    ignition: Mapped[bool] = mapped_column(Boolean, default=False)
    satellites: Mapped[int] = mapped_column(Integer, default=0)
    raw_packet_id: Mapped[int | None] = mapped_column(ForeignKey("raw_packets.id"), nullable=True)
    # IO telemetry
    harsh_braking: Mapped[bool] = mapped_column(Boolean, default=False)
    harsh_acceleration: Mapped[bool] = mapped_column(Boolean, default=False)
    harsh_cornering: Mapped[bool] = mapped_column(Boolean, default=False)
    towing: Mapped[bool] = mapped_column(Boolean, default=False)
    jamming: Mapped[bool] = mapped_column(Boolean, default=False)
    sos: Mapped[bool] = mapped_column(Boolean, default=False)
    crash: Mapped[bool] = mapped_column(Boolean, default=False)
    door_open: Mapped[bool] = mapped_column(Boolean, default=False)
    ext_voltage_mv: Mapped[int] = mapped_column(Integer, default=0)
    battery_mv: Mapped[int] = mapped_column(Integer, default=0)
    fuel_level: Mapped[int] = mapped_column(Integer, default=0)
    odometer_m: Mapped[int] = mapped_column(Integer, default=0)


class RawPacket(Base):
    __tablename__ = "raw_packets"
    id: Mapped[int] = mapped_column(primary_key=True)
    imei: Mapped[str] = mapped_column(String(32), index=True)
    protocol: Mapped[str] = mapped_column(String(30))
    payload_hex: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TelemetryEvent(Base):
    """Provider-neutral event envelope emitted by every protocol adapter."""
    __tablename__ = "telemetry_events"
    __table_args__ = (UniqueConstraint("organization_id", "source_protocol", "device_imei", "event_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    device_imei: Mapped[str] = mapped_column(String(32), index=True)
    source_protocol: Mapped[str] = mapped_column(String(30), index=True)
    event_key: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResourceRecord(Base):
    """Tenant-scoped persistence boundary for the modular fleet domains."""
    __tablename__ = "resource_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    resource_type: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(40), default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AutoTrip(Base):
    """Auto-detected trip from ignition on/off transitions."""
    __tablename__ = "auto_trips"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_lat: Mapped[float] = mapped_column(Float, default=0)
    start_lon: Mapped[float] = mapped_column(Float, default=0)
    end_lat: Mapped[float] = mapped_column(Float, default=0)
    end_lon: Mapped[float] = mapped_column(Float, default=0)
    distance_m: Mapped[float] = mapped_column(Float, default=0)
    max_speed_kph: Mapped[float] = mapped_column(Float, default=0)
    harsh_events: Mapped[int] = mapped_column(Integer, default=0)
    idle_seconds: Mapped[int] = mapped_column(Integer, default=0)
    driver_score: Mapped[float] = mapped_column(Float, default=100.0)


class MaintenanceReminder(Base):
    """Trigger a maintenance alert when odometer or engine hours threshold is reached."""
    __tablename__ = "maintenance_reminders"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    odometer_threshold_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    engine_hours_threshold_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Inspection(Base):
    """A submitted vehicle inspection; defects are persisted separately for follow-up."""
    __tablename__ = "inspections"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    inspector_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True, index=True)
    inspection_type: Mapped[str] = mapped_column(String(30), default="pre_trip")
    template_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_templates.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist_results: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    evidence_file_ids: Mapped[list] = mapped_column(JSON, default=list)
    signature_file_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_files.id"), nullable=True)
    signature_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InspectionTemplate(Base):
    __tablename__ = "inspection_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    inspection_type: Mapped[str] = mapped_column(String(30), default="pre_trip")
    items: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Defect(Base):
    """A defect found during an inspection and optionally resolved by a work order."""
    __tablename__ = "defects"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    inspection_id: Mapped[int | None] = mapped_column(ForeignKey("inspections.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="minor")
    status: Mapped[str] = mapped_column(String(30), default="open")
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ServicePlan(Base):
    """Recurring vehicle service based on distance, engine hours, or both."""
    __tablename__ = "service_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_engine_hours_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_service_distance_m: Mapped[float] = mapped_column(Float, default=0)
    last_service_engine_hours_s: Mapped[float] = mapped_column(Float, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_serviced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Part(Base):
    """Tenant-owned inventory available to maintenance work orders."""
    __tablename__ = "parts"
    __table_args__ = (UniqueConstraint("organization_id", "sku"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    sku: Mapped[str] = mapped_column(String(80))
    quantity_on_hand: Mapped[float] = mapped_column(Float, default=0)
    reorder_level: Mapped[float] = mapped_column(Float, default=0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Vendor(Base):
    """An internal or external maintenance provider."""
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    contact_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WorkOrder(Base):
    """Maintenance work with attributable labor, parts, and external costs."""
    __tablename__ = "work_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    defect_id: Mapped[int | None] = mapped_column(ForeignKey("defects.id"), nullable=True, index=True)
    service_plan_id: Mapped[int | None] = mapped_column(ForeignKey("service_plans.id"), nullable=True, index=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    labor_cost: Mapped[float] = mapped_column(Float, default=0)
    parts_cost: Mapped[float] = mapped_column(Float, default=0)
    external_cost: Mapped[float] = mapped_column(Float, default=0)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    downtime_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    downtime_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def total_cost(self) -> float:
        return self.labor_cost + self.parts_cost + self.external_cost


class WorkOrderPart(Base):
    """A part planned for a work order; stock is consumed when the order is completed."""
    __tablename__ = "work_order_parts"
    __table_args__ = (UniqueConstraint("work_order_id", "part_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    unit_cost: Mapped[float] = mapped_column(Float)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VehicleOdometer(Base):
    """Cumulative odometer and engine hours per vehicle."""
    __tablename__ = "vehicle_odometers"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), unique=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    total_distance_m: Mapped[float] = mapped_column(Float, default=0)
    engine_hours_s: Mapped[float] = mapped_column(Float, default=0)
    last_position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class FuelTransaction(Base):
    __tablename__ = "fuel_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    liters: Mapped[float] = mapped_column(Float)
    total_cost: Mapped[float] = mapped_column(Float)
    odometer_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    card_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    anomaly: Mapped[bool] = mapped_column(Boolean, default=False)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    kind: Mapped[str] = mapped_column(String(50), index=True)
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class SafetyIncident(Base):
    __tablename__ = "safety_incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="open")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    evidence_file_ids: Mapped[list] = mapped_column(JSON, default=list)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("safety_incidents.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvidenceFile(Base):
    """Private organization-scoped evidence; bytes never live in public URLs."""
    __tablename__ = "evidence_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(40), default="evidence")
    original_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str] = mapped_column(String(80), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class DriverDutyLog(Base):
    """Immutable duty segments used for hours-of-service calculations."""
    __tablename__ = "driver_duty_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="driving")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReportSchedule(Base):
    __tablename__ = "report_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    report_type: Mapped[str] = mapped_column(String(60), default="fleet-kpis")
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    cron: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ExternalImportJob(Base):
    __tablename__ = "external_import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    resource_type: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
