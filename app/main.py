from contextlib import asynccontextmanager
import asyncio
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from .gateway import start_servers
from .models import Alert, Driver, Geofence, Organization, Position, Trip, User, Vehicle
from .schemas import DriverIn, DriverOut, GeofenceIn, GeofenceOut, LoginIn, PositionOut, RegisterIn, TokenOut, TripIn, TripOut, VehicleIn, VehicleOut
from .security import current_user, hash_password, token_for, verify_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    servers = await start_servers()
    try: yield
    finally:
        for server in servers: server.close(); await server.wait_closed()


app = FastAPI(title="GPS Fleet Backend", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health(): return {"status": "ok", "gps_gateway": "custom_tcp", "traccar": False}


@app.post("/api/v1/auth/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email.lower()).first(): raise HTTPException(409, "Email already registered")
    org = Organization(name=body.organization_name); db.add(org); db.flush()
    user = User(organization_id=org.id, email=body.email.lower(), password_hash=hash_password(body.password), role="admin")
    db.add(user); db.commit(); db.refresh(user)
    return TokenOut(access_token=token_for(user))


@app.post("/api/v1/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash): raise HTTPException(401, "Invalid email or password")
    return TokenOut(access_token=token_for(user))


@app.post("/api/v1/vehicles", response_model=VehicleOut)
def create_vehicle(body: VehicleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id, Vehicle.imei == body.imei).first(): raise HTTPException(409, "IMEI already registered")
    vehicle = Vehicle(organization_id=user.organization_id, **body.model_dump()); db.add(vehicle); db.commit(); db.refresh(vehicle); return vehicle


@app.get("/api/v1/vehicles", response_model=list[VehicleOut])
def list_vehicles(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id).order_by(Vehicle.id.desc()).all()


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
