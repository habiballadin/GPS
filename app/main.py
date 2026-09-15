from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from .gateway import start_servers, send_device_command
from .models import Alert, Driver, Geofence, OneTimeToken, Organization, Position, RefreshSession, ResourceRecord, Trip, User, Vehicle, VehicleAssignment
from .schemas import AssignmentIn, AssignmentOut, DriverIn, DriverOut, GeofenceIn, GeofenceOut, InvitationAccept, InvitationCreate, LoginIn, MaintenanceIn, PasswordResetConfirm, PasswordResetRequest, PositionOut, RefreshIn, RegisterIn, ResourceIn, ResourceOut, ResourcePatch, RESOURCE_TYPES, TokenOut, TripIn, TripOut, UserCreate, UserOut, UserRolePatch, VehicleIn, VehicleOut, VehiclePatch
from .security import current_user, hash_password, random_token, require_roles, token_for, token_hash, verify_password
from .mailer import send_email


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    servers = await start_servers()
    try: yield
    finally:
        for server in servers: server.close(); await server.wait_closed()


app = FastAPI(title="GPS Fleet Backend", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SUPPORTED_RESOURCES = set(RESOURCE_TYPES.__args__)


def resource_or_400(resource_type: str) -> str:
    if resource_type not in SUPPORTED_RESOURCES:
        raise HTTPException(400, f"Unsupported resource type: {resource_type}")
    return resource_type


@app.get("/health")
def health(): return {"status": "ok", "gps_gateway": "custom_tcp", "traccar": False}


def issue_tokens(user: User, db: Session) -> TokenOut:
    refresh = random_token()
    db.add(RefreshSession(user_id=user.id, token_hash=token_hash(refresh), expires_at=datetime.now(timezone.utc) + timedelta(days=30)))
    db.commit()
    return TokenOut(access_token=token_for(user, 60), refresh_token=refresh, expires_in=3600)


@app.post("/api/v1/auth/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email.lower()).first(): raise HTTPException(409, "Email already registered")
    org = Organization(name=body.organization_name); db.add(org); db.flush()
    user = User(organization_id=org.id, email=body.email.lower(), password_hash=hash_password(body.password), role="admin")
    db.add(user); db.commit(); db.refresh(user)
    return issue_tokens(user, db)


@app.post("/api/v1/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash): raise HTTPException(401, "Invalid email or password")
    return issue_tokens(user, db)


@app.post("/api/v1/auth/refresh", response_model=TokenOut)
def refresh_tokens(body: RefreshIn, db: Session = Depends(get_db)):
    session = db.query(RefreshSession).filter(RefreshSession.token_hash == token_hash(body.refresh_token), RefreshSession.revoked_at.is_(None)).first()
    if not session or session.expires_at <= datetime.now(timezone.utc): raise HTTPException(401, "Refresh token expired")
    user = db.get(User, session.user_id)
    if not user: raise HTTPException(401, "User not found")
    session.revoked_at = datetime.now(timezone.utc)
    return issue_tokens(user, db)


@app.post("/api/v1/auth/password-reset/request")
def request_password_reset(body: PasswordResetRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user:
        raw = random_token()
        db.add(OneTimeToken(kind="password_reset", user_id=user.id, email=user.email, token_hash=token_hash(raw), expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)))
        db.commit()
        from .config import settings
        send_email(user.email, "Reset your GPS Fleet password", f"Reset your password: {settings.app_base_url}/reset-password?token={raw}")
    return {"message": "If the account exists, recovery instructions have been sent."}


@app.post("/api/v1/auth/password-reset/confirm")
def confirm_password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    item = db.query(OneTimeToken).filter(OneTimeToken.kind == "password_reset", OneTimeToken.token_hash == token_hash(body.token), OneTimeToken.used_at.is_(None)).first()
    if not item or item.expires_at <= datetime.now(timezone.utc): raise HTTPException(400, "Invalid or expired reset token")
    user = db.get(User, item.user_id)
    if not user: raise HTTPException(400, "Invalid reset token")
    user.password_hash = hash_password(body.password); item.used_at = datetime.now(timezone.utc); db.commit()
    return {"message": "Password updated"}


@app.post("/api/v1/auth/invitations/accept", response_model=TokenOut)
def accept_invitation(body: InvitationAccept, db: Session = Depends(get_db)):
    item = db.query(OneTimeToken).filter(OneTimeToken.kind == "invitation", OneTimeToken.token_hash == token_hash(body.token), OneTimeToken.used_at.is_(None)).first()
    if not item or item.expires_at <= datetime.now(timezone.utc): raise HTTPException(400, "Invalid or expired invitation")
    if db.query(User).filter(User.email == item.email).first(): raise HTTPException(409, "Email already registered")
    user = User(organization_id=item.organization_id, email=item.email, password_hash=hash_password(body.password), role=item.role or "operator")
    db.add(user); item.used_at = datetime.now(timezone.utc); db.commit(); db.refresh(user)
    return issue_tokens(user, db)


@app.get("/api/v1/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@app.get("/api/v1/users", response_model=list[UserOut])
def list_users(user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    return db.query(User).filter(User.organization_id == user.organization_id).order_by(User.id).all()


@app.post("/api/v1/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "Email already registered")
    member = User(organization_id=user.organization_id, email=email, password_hash=hash_password(body.password), role=body.role)
    db.add(member); db.commit(); db.refresh(member)
    return member


@app.post("/api/v1/users/invite")
def invite_user(body: InvitationCreate, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first(): raise HTTPException(409, "Email already registered")
    raw = random_token()
    db.add(OneTimeToken(kind="invitation", email=email, organization_id=user.organization_id, role=body.role, token_hash=token_hash(raw), expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
    db.commit()
    from .config import settings
    delivered = send_email(email, "You are invited to GPS Fleet", f"Accept your invitation: {settings.app_base_url}/accept-invitation?token={raw}")
    return {"message": "Invitation created", "email_delivered": delivered}


@app.patch("/api/v1/users/{user_id}/role", response_model=UserOut)
def update_user_role(user_id: int, body: UserRolePatch, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    member = db.query(User).filter(User.id == user_id, User.organization_id == user.organization_id).first()
    if not member: raise HTTPException(404, "User not found")
    if member.id == user.id and body.role != "admin": raise HTTPException(400, "You cannot remove your own admin role")
    member.role = body.role; db.commit(); db.refresh(member)
    return member


@app.post("/api/v1/vehicles", response_model=VehicleOut)
def create_vehicle(body: VehicleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id, Vehicle.imei == body.imei).first(): raise HTTPException(409, "IMEI already registered")
    vehicle = Vehicle(organization_id=user.organization_id, **body.model_dump()); db.add(vehicle); db.commit(); db.refresh(vehicle); return vehicle


@app.get("/api/v1/vehicles", response_model=list[VehicleOut])
def list_vehicles(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id).order_by(Vehicle.id.desc()).all()


@app.get("/api/v1/vehicles/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    return vehicle


@app.get("/api/v1/vehicles/{vehicle_id}/history", response_model=list[PositionOut])
def vehicle_history(vehicle_id: int, since: datetime | None = None, until: datetime | None = None, limit: int = Query(1000, ge=1, le=10000), user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    query = db.query(Position).filter(Position.vehicle_id == vehicle_id, Position.organization_id == user.organization_id)
    if since: query = query.filter(Position.recorded_at >= since)
    if until: query = query.filter(Position.recorded_at <= until)
    return query.order_by(Position.recorded_at.asc()).limit(limit).all()


@app.get("/api/v1/vehicles/{vehicle_id}/assignments", response_model=list[AssignmentOut])
def vehicle_assignments(vehicle_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(VehicleAssignment).filter(VehicleAssignment.vehicle_id == vehicle_id, VehicleAssignment.organization_id == user.organization_id).order_by(VehicleAssignment.assigned_at.desc()).all()


@app.post("/api/v1/vehicles/{vehicle_id}/assignments", response_model=AssignmentOut, status_code=201)
def assign_vehicle(vehicle_id: int, body: AssignmentIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first(); driver = db.query(Driver).filter(Driver.id == body.driver_id, Driver.organization_id == user.organization_id, Driver.active.is_(True)).first()
    if not vehicle or not driver: raise HTTPException(404, "Vehicle or driver not found")
    active = db.query(VehicleAssignment).filter(VehicleAssignment.vehicle_id == vehicle_id, VehicleAssignment.organization_id == user.organization_id, VehicleAssignment.ended_at.is_(None)).all()
    for item in active: item.ended_at = datetime.now(timezone.utc)
    assignment = VehicleAssignment(organization_id=user.organization_id, vehicle_id=vehicle_id, driver_id=body.driver_id); db.add(assignment); db.commit(); db.refresh(assignment); return assignment


@app.get("/api/v1/vehicles/{vehicle_id}/maintenance", response_model=list[ResourceOut])
def vehicle_maintenance(vehicle_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(ResourceRecord).filter(ResourceRecord.organization_id == user.organization_id, ResourceRecord.resource_type == "maintenance", ResourceRecord.details["vehicle_id"].as_integer() == vehicle_id).order_by(ResourceRecord.updated_at.desc()).all()


@app.post("/api/v1/vehicles/{vehicle_id}/maintenance", response_model=ResourceOut, status_code=201)
def add_vehicle_maintenance(vehicle_id: int, body: MaintenanceIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    details = {**body.details, "vehicle_id": vehicle_id}; record = ResourceRecord(organization_id=user.organization_id, resource_type="maintenance", name=body.name, status=body.status, description=body.description, details=details); db.add(record); db.commit(); db.refresh(record); return record


@app.patch("/api/v1/vehicles/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: int, body: VehiclePatch, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    for field, value in body.model_dump(exclude_unset=True).items(): setattr(vehicle, field, value)
    db.commit(); db.refresh(vehicle)
    return vehicle


@app.post("/api/v1/vehicles/{vehicle_id}/command")
async def send_command(vehicle_id: int, body: dict, user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    if vehicle.protocol != "teltonika": raise HTTPException(400, "Commands only supported for Teltonika devices")
    command = body.get("command", "").strip()
    if not command: raise HTTPException(400, "command is required")
    result = await send_device_command(vehicle.imei, command)
    if result is None: raise HTTPException(503, "Device not connected")
    return {"imei": vehicle.imei, "command": command, "response": result}


@app.delete("/api/v1/vehicles/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int, user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    vehicle.active = False; db.commit()


@app.get("/api/v1/vehicles/{vehicle_id}/positions", response_model=list[PositionOut])
def positions(vehicle_id: int, limit: int = Query(100, ge=1, le=1000), user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    return db.query(Position).filter(Position.vehicle_id == vehicle_id).order_by(Position.recorded_at.desc()).limit(limit).all()


@app.get("/api/v1/dashboard/summary")
def summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicles = db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id).all()
    cutoff = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).timestamp() - 900
    active = sum(1 for v in vehicles if v.last_seen_at and v.last_seen_at.timestamp() >= cutoff)
    alerts = db.query(func.count(Alert.id)).filter(Alert.organization_id == user.organization_id, Alert.acknowledged.is_(False)).scalar() or 0
    return {"total_vehicles": len(vehicles), "online_vehicles": active, "offline_vehicles": len(vehicles) - active, "open_alerts": alerts}


@app.get("/api/v1/analytics/overview")
def analytics_overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicles = db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id).all()
    positions = db.query(Position).filter(Position.organization_id == user.organization_id).count()
    alerts = db.query(Alert).filter(Alert.organization_id == user.organization_id).count()
    trips = db.query(Trip).filter(Trip.organization_id == user.organization_id).count()
    return {"vehicles": len(vehicles), "active_vehicles": sum(1 for v in vehicles if v.active), "positions": positions, "alerts": alerts, "trips": trips, "protocols": {protocol: sum(1 for v in vehicles if v.protocol == protocol) for protocol in {v.protocol for v in vehicles}}}


@app.get("/api/v1/reports/fleet.csv")
def fleet_report_csv(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = ["vehicle_id,name,imei,protocol,active,last_seen_at"]
    for vehicle in db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id).order_by(Vehicle.id).all():
        rows.append(",".join(str(value or "") for value in [vehicle.id, vehicle.name, vehicle.imei, vehicle.protocol, vehicle.active, vehicle.last_seen_at]))
    return Response("\n".join(rows), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=fleet-report.csv"})


@app.get("/api/v1/notifications", response_model=list[ResourceOut])
def list_notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(ResourceRecord).filter(ResourceRecord.organization_id == user.organization_id, ResourceRecord.resource_type == "notifications").order_by(ResourceRecord.updated_at.desc()).limit(200).all()


@app.post("/api/v1/notifications/preferences", response_model=ResourceOut)
def save_notification_preferences(body: ResourceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    existing = db.query(ResourceRecord).filter(ResourceRecord.organization_id == user.organization_id, ResourceRecord.resource_type == "notification_preferences", ResourceRecord.name == body.name).first()
    if existing:
        existing.status = body.status; existing.details = body.details; existing.description = body.description; db.commit(); db.refresh(existing); return existing
    record = ResourceRecord(organization_id=user.organization_id, resource_type="notification_preferences", **body.model_dump()); db.add(record); db.commit(); db.refresh(record); return record


@app.get("/api/v1/alerts")
def alerts(limit: int = Query(100, ge=1, le=500), user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Alert).filter(Alert.organization_id == user.organization_id).order_by(Alert.created_at.desc()).limit(limit).all()


@app.post("/api/v1/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.organization_id == user.organization_id).first()
    if not alert: raise HTTPException(404, "Alert not found")
    alert.acknowledged = True; db.commit(); return {"id": alert.id, "acknowledged": True}


@app.post("/api/v1/drivers", response_model=DriverOut)
def create_driver(body: DriverIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    driver = Driver(organization_id=user.organization_id, **body.model_dump()); db.add(driver); db.commit(); db.refresh(driver); return driver


@app.get("/api/v1/drivers", response_model=list[DriverOut])
def list_drivers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Driver).filter(Driver.organization_id == user.organization_id, Driver.active.is_(True)).all()


@app.post("/api/v1/trips", response_model=TripOut)
def create_trip(body: TripIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.vehicle_id and not db.query(Vehicle).filter(Vehicle.id == body.vehicle_id, Vehicle.organization_id == user.organization_id).first(): raise HTTPException(404, "Vehicle not found")
    if body.driver_id and not db.query(Driver).filter(Driver.id == body.driver_id, Driver.organization_id == user.organization_id).first(): raise HTTPException(404, "Driver not found")
    trip = Trip(organization_id=user.organization_id, **body.model_dump()); db.add(trip); db.commit(); db.refresh(trip); return trip


@app.get("/api/v1/trips", response_model=list[TripOut])
def list_trips(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Trip).filter(Trip.organization_id == user.organization_id).order_by(Trip.id.desc()).limit(500).all()


@app.post("/api/v1/geofences", response_model=GeofenceOut)
def create_geofence(body: GeofenceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    fence = Geofence(organization_id=user.organization_id, **body.model_dump()); db.add(fence); db.commit(); db.refresh(fence); return fence


@app.get("/api/v1/geofences", response_model=list[GeofenceOut])
def list_geofences(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Geofence).filter(Geofence.organization_id == user.organization_id, Geofence.active.is_(True)).all()


@app.get("/api/v1/resources/{resource_type}", response_model=list[ResourceOut])
def list_resources(resource_type: str, limit: int = Query(100, ge=1, le=500), user: User = Depends(current_user), db: Session = Depends(get_db)):
    kind = resource_or_400(resource_type)
    return db.query(ResourceRecord).filter(ResourceRecord.organization_id == user.organization_id, ResourceRecord.resource_type == kind).order_by(ResourceRecord.updated_at.desc()).limit(limit).all()


@app.post("/api/v1/resources/{resource_type}", response_model=ResourceOut, status_code=201)
def create_resource(resource_type: str, body: ResourceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kind = resource_or_400(resource_type)
    record = ResourceRecord(resource_type=kind, organization_id=user.organization_id, **body.model_dump())
    db.add(record); db.commit(); db.refresh(record)
    return record


@app.get("/api/v1/resources/{resource_type}/{resource_id}", response_model=ResourceOut)
def get_resource(resource_type: str, resource_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kind = resource_or_400(resource_type)
    record = db.query(ResourceRecord).filter(ResourceRecord.id == resource_id, ResourceRecord.resource_type == kind, ResourceRecord.organization_id == user.organization_id).first()
    if not record: raise HTTPException(404, "Resource not found")
    return record


@app.patch("/api/v1/resources/{resource_type}/{resource_id}", response_model=ResourceOut)
def update_resource(resource_type: str, resource_id: int, body: ResourcePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kind = resource_or_400(resource_type)
    record = db.query(ResourceRecord).filter(ResourceRecord.id == resource_id, ResourceRecord.resource_type == kind, ResourceRecord.organization_id == user.organization_id).first()
    if not record: raise HTTPException(404, "Resource not found")
    for field, value in body.model_dump(exclude_unset=True).items(): setattr(record, field, value)
    db.commit(); db.refresh(record)
    return record


@app.delete("/api/v1/resources/{resource_type}/{resource_id}", status_code=204)
def delete_resource(resource_type: str, resource_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kind = resource_or_400(resource_type)
    record = db.query(ResourceRecord).filter(ResourceRecord.id == resource_id, ResourceRecord.resource_type == kind, ResourceRecord.organization_id == user.organization_id).first()
    if not record: raise HTTPException(404, "Resource not found")
    db.delete(record); db.commit()


@app.websocket("/api/v1/ws/live")
async def live_positions(websocket: WebSocket, token: str):
    await websocket.accept()
    try:
        import jwt
        from .config import settings
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        org_id = int(claims["org"])
        while True:
            db = next(get_db())
            try:
                rows = db.query(Position).filter(Position.organization_id == org_id).order_by(Position.recorded_at.desc()).limit(100).all()
                latest = {}
                for row in rows: latest.setdefault(row.vehicle_id, row)
                await websocket.send_json({"type": "positions", "data": [PositionOut.model_validate(row).model_dump(mode="json") for row in latest.values()]})
            finally: db.close()
            await asyncio.sleep(3)
    except (WebSocketDisconnect, Exception):
        try: await websocket.close()
        except RuntimeError: pass
