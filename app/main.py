from contextlib import asynccontextmanager
import asyncio
import hashlib
import os
import httpx
import csv
import io
from pathlib import Path
from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session
from .db import Base, engine, get_db, SessionLocal
from .gateway import start_servers, send_device_command
from .models import Alert, AssetAttachment, AutoTrip, AuditLog, CorrectiveAction, Customer, Defect, DeliveryException, DeliveryOrder, DeliveryStop, Device, DeviceBinding, DeviceCommand, Driver, DriverAvailability, DriverCertification, DriverCoaching, DriverDutyLog, EvidenceFile, ExternalImportJob, FleetAsset, FuelTransaction, Geofence, Inspection, InspectionTemplate, MaintenanceReminder, OneTimeToken, Organization, Part, Position, RefreshSession, ReportSchedule, ResourceRecord, SafetyIncident, ServicePlan, SIMCard, TelemetryEvent, Trip, User, Vehicle, VehicleAssignment, VehicleOdometer, Vendor, WorkOrder, WorkOrderPart
from .schemas import AIFleetInsightOut, AssetAttachmentOut, AssignmentIn, AssignmentOut, AutoTripOut, CorrectiveActionIn, CorrectiveActionOut, CustomerIn, CustomerOut, DefectOut, DeliveryDeviationOut, DeliveryExceptionOut, DeliveryOrderAssign, DeliveryOrderIn, DeliveryOrderOut, DeliveryRouteOptimizeOut, DeliveryRouteSummaryOut, DeliveryStopComplete, DeliveryStopIn, DeliveryStopOut, DeviceBindingOut, DeviceCommandIn, DeviceCommandOut, DeviceHealthOut, DeviceIn, DeviceOut, DriverAvailabilityIn, DriverAvailabilityOut, DriverCertificationIn, DriverCertificationOut, DriverCoachingIn, DriverCoachingOut, DriverDutyLogIn, DriverDutyLogOut, DriverHoursOut, EvidenceFileOut, ExternalImportIn, ExternalImportOut, FleetExceptionOut, DriverIn, DriverOut, DriverSafetyOut, ETARequest, FleetAssetIn, FleetAssetOut, FleetKpiOut, FuelSummaryOut, FuelTransactionIn, FuelTransactionOut, GeofenceIn, GeofenceOut, IncidentIn, IncidentOut, IncidentPatch, InspectionIn, InspectionOut, InspectionTemplateIn, InspectionTemplateOut, InvitationAccept, InvitationCreate, LoginIn, MaintenanceIn, MaintenanceReminderIn, MaintenanceReminderOut, MaintenancePredictionOut, OdometerOut, PartIn, PartOut, PasswordResetConfirm, PasswordResetRequest, PositionOut, RefreshIn, RegisterIn, ReportScheduleIn, ReportScheduleOut, ResourceIn, ResourceOut, ResourcePatch, RESOURCE_TYPES, ServicePlanIn, ServicePlanOut, SIMCardIn, SIMCardOut, TelemetryEventOut, TokenOut, TripIn, TripOut, UserCreate, UserOut, UserRolePatch, VehicleCostRollupOut, VehicleIn, VehicleOut, VehiclePatch, VehicleProfileIn, VehicleProfileOut, VehicleThresholdPatch, VendorIn, VendorOut, WorkOrderIn, WorkOrderOut, WorkOrderPartIn, WorkOrderPartOut, WorkOrderPatch
from .security import current_user, hash_password, random_token, require_roles, token_for, token_hash, verify_password
from .mailer import send_email
from .config import settings
from .gateway import start_servers, send_device_command, _subscribe_alerts, _unsubscribe_alerts, subscribe_telemetry, unsubscribe_telemetry
from .protocols import supported_protocols
from .live_state import get_vehicle_states
from .routing import optimize_points, route_metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
    servers = await start_servers()
    scheduler_task = asyncio.create_task(report_scheduler())
    try: yield
    finally:
        scheduler_task.cancel()
        try: await scheduler_task
        except asyncio.CancelledError: pass
        for server in servers: server.close(); await server.wait_closed()


app = FastAPI(title="GPS Fleet Backend", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def _schedule_interval(cron: str) -> timedelta:
    """Safe built-in schedule subset; full cron remains deployable via a worker."""
    return {"@hourly": timedelta(hours=1), "@daily": timedelta(days=1), "@weekly": timedelta(days=7)}.get(cron, timedelta(hours=1))


async def report_scheduler():
    while True:
        db = SessionLocal()
        try:
            now_utc = datetime.now(timezone.utc)
            due = db.query(ReportSchedule).filter(ReportSchedule.active.is_(True), ReportSchedule.next_run_at.is_not(None), ReportSchedule.next_run_at <= now_utc).limit(50).all()
            for schedule in due:
                recipients = [email for email in schedule.recipients if "@" in email]
                if recipients:
                    body = f"Scheduled {schedule.report_type} report for organization {schedule.organization_id}. Generated at {now_utc.isoformat()}."
                    for recipient in recipients: send_email(recipient, f"GPS Fleet report: {schedule.name}", body)
                schedule.last_run_at = now_utc
                schedule.next_run_at = now_utc + _schedule_interval(schedule.cron)
                db.add(AuditLog(organization_id=schedule.organization_id, actor_id=schedule.created_by, action="report.schedule.executed", resource_type="report_schedule", resource_id=str(schedule.id), metadata_json={"recipients": len(recipients)}))
            if due: db.commit()
        finally:
            db.close()
        await asyncio.sleep(max(5, settings.scheduler_poll_seconds))

SUPPORTED_RESOURCES = set(RESOURCE_TYPES.__args__)


def resource_or_400(resource_type: str) -> str:
    if resource_type not in SUPPORTED_RESOURCES:
        raise HTTPException(400, f"Unsupported resource type: {resource_type}")
    return resource_type


@app.get("/health")
def health(): return {"status": "ok", "gps_gateway": "custom_tcp", "traccar": False}


@app.get("/api/v1/maps/geocode")
async def geocode(q: str = Query(..., min_length=2, max_length=300), user: User = Depends(current_user)):
    """Provider-neutral geocoding seam; credentials remain server-side."""
    if not settings.map_provider_url:
        raise HTTPException(503, "Map provider is not configured")
    headers = {"Accept": "application/json", "User-Agent": "gps-fleet/1.0"}
    if settings.map_provider_api_key: headers["Authorization"] = f"Bearer {settings.map_provider_api_key}"
    params = {"q": q, "format": "json", "limit": 5}
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get(settings.map_provider_url, params=params, headers=headers)
    if response.status_code >= 400: raise HTTPException(502, "Map provider request failed")
    return response.json()


@app.get("/api/v1/report-schedules", response_model=list[ReportScheduleOut])
def list_report_schedules(user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    return db.query(ReportSchedule).filter(ReportSchedule.organization_id == user.organization_id).order_by(ReportSchedule.created_at.desc()).all()


@app.post("/api/v1/report-schedules", response_model=ReportScheduleOut, status_code=201)
def create_report_schedule(body: ReportScheduleIn, user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    if any("@" not in recipient for recipient in body.recipients): raise HTTPException(400, "Recipients must be email addresses")
    values = body.model_dump(); item = ReportSchedule(organization_id=user.organization_id, created_by=user.id, next_run_at=datetime.now(timezone.utc) + _schedule_interval(body.cron), **values); db.add(item); db.flush(); record_audit(db, user, "report.schedule.created", "report_schedule", item.id); db.commit(); db.refresh(item); return item


@app.get("/api/v1/imports", response_model=list[ExternalImportOut])
def list_imports(user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    return db.query(ExternalImportJob).filter(ExternalImportJob.organization_id == user.organization_id).order_by(ExternalImportJob.created_at.desc()).limit(100).all()


@app.post("/api/v1/imports", response_model=ExternalImportOut, status_code=202)
def queue_import(body: ExternalImportIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    item = ExternalImportJob(organization_id=user.organization_id, created_by=user.id, **body.model_dump()); db.add(item); db.flush(); record_audit(db, user, "external_import.queued", "external_import", item.id, {"provider": body.provider, "resource_type": body.resource_type}); db.commit(); db.refresh(item); return item


@app.post("/api/v1/imports/{import_id}/fuel-csv", response_model=ExternalImportOut)
async def import_fuel_csv(import_id: int, file: UploadFile = File(...), user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    job = db.query(ExternalImportJob).filter(ExternalImportJob.id == import_id, ExternalImportJob.organization_id == user.organization_id, ExternalImportJob.provider == "fuel-card", ExternalImportJob.resource_type == "fuel").first()
    if not job: raise HTTPException(404, "Fuel import job not found")
    if file.content_type not in ("text/csv", "application/csv", "application/vnd.ms-excel"): raise HTTPException(415, "Upload a CSV file")
    content = await file.read()
    if len(content) > settings.max_evidence_bytes: raise HTTPException(413, "Import file is too large")
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    required = {"vehicle_id", "liters", "total_cost"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)): raise HTTPException(400, "CSV requires vehicle_id, liters, and total_cost columns")
    imported = 0
    try:
        for row in reader:
            vehicle_id = int(row["vehicle_id"])
            if not db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first(): raise ValueError(f"Vehicle {vehicle_id} not found")
            occurred = datetime.fromisoformat(row["occurred_at"]) if row.get("occurred_at") else datetime.now(timezone.utc)
            db.add(FuelTransaction(organization_id=user.organization_id, vehicle_id=vehicle_id, driver_id=int(row["driver_id"]) if row.get("driver_id") else None, occurred_at=occurred, liters=float(row["liters"]), total_cost=float(row["total_cost"]), odometer_m=float(row["odometer_m"]) if row.get("odometer_m") else None, provider=row.get("provider") or "fuel-card", card_reference=row.get("card_reference")))
            imported += 1
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback(); job.status = "failed"; job.error_message = str(exc); db.commit(); raise HTTPException(400, f"Invalid CSV row: {exc}")
    job.status = "completed"; job.rows_imported = imported; job.completed_at = datetime.now(timezone.utc); record_audit(db, user, "external_import.completed", "external_import", job.id, {"rows": imported}); db.commit(); db.refresh(job); return job


def record_audit(db: Session, user: User | None, action: str, resource_type: str, resource_id: int | str | None = None, metadata: dict | None = None):
    db.add(AuditLog(organization_id=user.organization_id if user else 0, actor_id=user.id if user else None, action=action, resource_type=resource_type, resource_id=str(resource_id) if resource_id is not None else None, metadata_json=metadata or {}))


@app.post("/api/v1/files", response_model=EvidenceFileOut, status_code=201)
async def upload_evidence(file: UploadFile = File(...), purpose: str = Query("evidence", pattern="^(evidence|signature|document)$"), user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    allowed = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
    if file.content_type not in allowed:
        raise HTTPException(415, "Only JPEG, PNG, WebP, and PDF files are supported")
    root = Path(settings.evidence_storage_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    storage_key = f"{user.organization_id}/{random_token()}"
    destination = root / storage_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(); total = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_evidence_bytes:
                    raise HTTPException(413, "Evidence file is too large")
                digest.update(chunk); output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    item = EvidenceFile(organization_id=user.organization_id, uploaded_by=user.id, purpose=purpose, original_name=os.path.basename(file.filename or "upload"), storage_key=storage_key, content_type=file.content_type, size_bytes=total, sha256=digest.hexdigest())
    db.add(item); record_audit(db, user, "file.uploaded", "evidence_file", None, {"purpose": purpose, "sha256": item.sha256}); db.commit(); db.refresh(item)
    return item


@app.get("/api/v1/files/{file_id}", response_model=EvidenceFileOut)
def get_file_metadata(file_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.query(EvidenceFile).filter(EvidenceFile.id == file_id, EvidenceFile.organization_id == user.organization_id).first()
    if not item: raise HTTPException(404, "File not found")
    return item


@app.get("/api/v1/files/{file_id}/download")
def download_file(file_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.query(EvidenceFile).filter(EvidenceFile.id == file_id, EvidenceFile.organization_id == user.organization_id).first()
    if not item: raise HTTPException(404, "File not found")
    path = (Path(settings.evidence_storage_path).resolve() / item.storage_key).resolve()
    if Path(settings.evidence_storage_path).resolve() not in path.parents or not path.is_file(): raise HTTPException(404, "File content unavailable")
    return FileResponse(path, media_type=item.content_type, filename=item.original_name)


@app.get("/api/v1/audit", response_model=list[dict])
def list_audit(limit: int = Query(100, ge=1, le=500), user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    rows = db.query(AuditLog).filter(AuditLog.organization_id == user.organization_id).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [{"id": row.id, "actor_id": row.actor_id, "action": row.action, "resource_type": row.resource_type, "resource_id": row.resource_id, "metadata": row.metadata_json, "created_at": row.created_at} for row in rows]


@app.get("/api/v1/reports/fleet-kpis", response_model=FleetKpiOut)
def fleet_kpis(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    vehicles = db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id).all()
    devices = db.query(Device).filter(Device.organization_id == user.organization_id).all()
    offline = sum(1 for device in devices if not device.last_seen_at or (device.last_seen_at.replace(tzinfo=timezone.utc) if device.last_seen_at.tzinfo is None else device.last_seen_at) < cutoff)
    fuel_cost = db.query(func.coalesce(func.sum(FuelTransaction.total_cost), 0)).filter(FuelTransaction.organization_id == user.organization_id).scalar() or 0
    maintenance_cost = sum(order.total_cost for order in db.query(WorkOrder).filter(WorkOrder.organization_id == user.organization_id).all())
    distance = sum((db.query(VehicleOdometer).filter(VehicleOdometer.vehicle_id == vehicle.id).first().total_distance_m if db.query(VehicleOdometer).filter(VehicleOdometer.vehicle_id == vehicle.id).first() else 0) for vehicle in vehicles)
    return FleetKpiOut(vehicles_total=len(vehicles), vehicles_active=sum(1 for vehicle in vehicles if vehicle.active), drivers_active=db.query(Driver).filter(Driver.organization_id == user.organization_id, Driver.active.is_(True)).count(), devices_offline=offline, open_alerts=db.query(Alert).filter(Alert.organization_id == user.organization_id, Alert.acknowledged.is_(False)).count(), open_incidents=db.query(SafetyIncident).filter(SafetyIncident.organization_id == user.organization_id, SafetyIncident.status.in_(("open", "investigating"))).count(), open_maintenance_orders=db.query(WorkOrder).filter(WorkOrder.organization_id == user.organization_id, WorkOrder.status.in_(("open", "in_progress", "on_hold"))).count(), delivery_orders_in_progress=db.query(DeliveryOrder).filter(DeliveryOrder.organization_id == user.organization_id, DeliveryOrder.status.in_(("assigned", "in_progress"))).count(), fuel_cost=round(float(fuel_cost), 2), maintenance_cost=round(maintenance_cost, 2), distance_m=round(distance, 2))


@app.get("/api/v1/ai/fleet-insights", response_model=list[AIFleetInsightOut])
def ai_fleet_insights(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Explainable fleet risk scoring from first-party telemetry and operations data."""
    now_utc = datetime.now(timezone.utc); recent = now_utc - timedelta(days=7); insights = []
    for vehicle in db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id, Vehicle.active.is_(True)).all():
        score = 0; factors: list[str] = []; actions: list[str] = []
        alerts = db.query(Alert).filter(Alert.organization_id == user.organization_id, Alert.vehicle_id == vehicle.id, Alert.created_at >= recent).count()
        if alerts: score += min(30, alerts * 5); factors.append(f"{alerts} alert(s) in the last 7 days"); actions.append("Review unresolved alerts and event evidence")
        open_orders = db.query(WorkOrder).filter(WorkOrder.organization_id == user.organization_id, WorkOrder.vehicle_id == vehicle.id, WorkOrder.status.in_(("open", "in_progress", "on_hold"))).count()
        if open_orders: score += min(25, open_orders * 10); factors.append(f"{open_orders} open maintenance work order(s)"); actions.append("Schedule or approve outstanding maintenance")
        anomalies = db.query(FuelTransaction).filter(FuelTransaction.organization_id == user.organization_id, FuelTransaction.vehicle_id == vehicle.id, FuelTransaction.anomaly.is_(True), FuelTransaction.occurred_at >= recent).count()
        if anomalies: score += min(20, anomalies * 10); factors.append(f"{anomalies} anomalous fuel transaction(s)"); actions.append("Validate fuel-card transaction and odometer")
        harsh = db.query(func.coalesce(func.sum(AutoTrip.harsh_events), 0)).filter(AutoTrip.organization_id == user.organization_id, AutoTrip.vehicle_id == vehicle.id, AutoTrip.started_at >= recent).scalar() or 0
        if harsh: score += min(15, int(harsh) * 2); factors.append(f"{int(harsh)} harsh driving event(s)"); actions.append("Coach assigned driver on harsh-event pattern")
        last_seen = vehicle.last_seen_at.replace(tzinfo=timezone.utc) if vehicle.last_seen_at and vehicle.last_seen_at.tzinfo is None else vehicle.last_seen_at
        if not last_seen or last_seen < now_utc - timedelta(minutes=30): score += 20; factors.append("Vehicle telemetry is offline"); actions.append("Check device power, binding, and network connectivity")
        score = min(100, score); level = "critical" if score >= 75 else "high" if score >= 50 else "medium" if score >= 25 else "low"
        insights.append(AIFleetInsightOut(vehicle_id=vehicle.id, vehicle_name=vehicle.name, risk_score=score, risk_level=level, confidence=0.85 if factors else 0.55, factors=factors or ["No elevated risk signals detected"], recommended_actions=actions or ["Continue normal monitoring"], generated_at=now_utc))
    return sorted(insights, key=lambda item: item.risk_score, reverse=True)


@app.get("/api/v1/maintenance/predictions", response_model=list[MaintenancePredictionOut])
def maintenance_predictions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Explainable maintenance risk forecast; replaceable by an ML worker later."""
    now_utc = datetime.now(timezone.utc); recent = now_utc - timedelta(days=30); predictions = []
    for vehicle in db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id, Vehicle.active.is_(True)).all():
        score = 0; factors: list[str] = []; actions: list[str] = []
        plans = db.query(ServicePlan).filter(ServicePlan.organization_id == user.organization_id, ServicePlan.vehicle_id == vehicle.id, ServicePlan.active.is_(True)).all()
        due_plans = [plan for plan in plans if service_plan_out(plan, db).due]
        if due_plans:
            score += min(40, 25 + (len(due_plans) - 1) * 10); factors.append(f"{len(due_plans)} service plan(s) are due"); actions.append("Create or approve the due service work order")
        defects = db.query(Defect).filter(Defect.organization_id == user.organization_id, Defect.vehicle_id == vehicle.id, Defect.status == "open").all()
        critical = sum(1 for defect in defects if defect.severity == "critical"); major = sum(1 for defect in defects if defect.severity == "major")
        if critical or major:
            score += min(35, critical * 25 + major * 12); factors.append(f"{critical + major} major/critical open defect(s)"); actions.append("Inspect defects and take the vehicle out of service if safety-critical")
        orders = db.query(WorkOrder).filter(WorkOrder.organization_id == user.organization_id, WorkOrder.vehicle_id == vehicle.id, WorkOrder.status.in_(("open", "in_progress", "on_hold"))).count()
        if orders:
            score += min(20, orders * 8); factors.append(f"{orders} open maintenance work order(s)"); actions.append("Review parts, vendor, and downtime readiness")
        events = db.query(TelemetryEvent).filter(TelemetryEvent.organization_id == user.organization_id, TelemetryEvent.vehicle_id == vehicle.id, TelemetryEvent.recorded_at >= recent, TelemetryEvent.event_type.in_(("engine_fault", "dtc", "maintenance", "low_battery"))).count()
        if events:
            score += min(25, events * 5); factors.append(f"{events} maintenance-related telemetry event(s) in 30 days"); actions.append("Review diagnostic codes and device health")
        data_points = db.query(Position).filter(Position.organization_id == user.organization_id, Position.vehicle_id == vehicle.id, Position.recorded_at >= recent).count()
        if data_points < 10: factors.append("Limited recent telemetry for a confident forecast")
        score = min(100, score); level = "critical" if score >= 75 else "high" if score >= 50 else "medium" if score >= 25 else "low"; window = 7 if score >= 75 else 14 if score >= 50 else 30 if score >= 25 else None
        predictions.append(MaintenancePredictionOut(vehicle_id=vehicle.id, vehicle_name=vehicle.name, risk_score=score, risk_level=level, predicted_failure_window_days=window, maintenance_due=bool(due_plans), factors=factors or ["No maintenance risk signals detected"], recommended_actions=actions or ["Continue scheduled maintenance monitoring"], data_points=data_points, generated_at=now_utc))
    return sorted(predictions, key=lambda item: item.risk_score, reverse=True)


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


@app.get("/api/v1/assets", response_model=list[FleetAssetOut])
def list_assets(asset_type: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(FleetAsset).filter(FleetAsset.organization_id == user.organization_id)
    if asset_type: query = query.filter(FleetAsset.asset_type == asset_type)
    return query.order_by(FleetAsset.name).all()


@app.post("/api/v1/assets", response_model=FleetAssetOut, status_code=201)
def create_asset(body: FleetAssetIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    if db.query(FleetAsset).filter(FleetAsset.organization_id == user.organization_id, FleetAsset.asset_tag == body.asset_tag).first(): raise HTTPException(409, "Asset tag already exists")
    asset = FleetAsset(organization_id=user.organization_id, **body.model_dump()); db.add(asset); db.commit(); db.refresh(asset); return asset


@app.get("/api/v1/assets/{asset_id}/attachments", response_model=list[AssetAttachmentOut])
def list_asset_attachments(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    asset = db.query(FleetAsset).filter(FleetAsset.id == asset_id, FleetAsset.organization_id == user.organization_id).first()
    if not asset: raise HTTPException(404, "Asset not found")
    return db.query(AssetAttachment).filter(AssetAttachment.asset_id == asset_id, AssetAttachment.organization_id == user.organization_id).order_by(AssetAttachment.attached_at.desc()).all()


@app.post("/api/v1/assets/{asset_id}/attach/{vehicle_id}", response_model=AssetAttachmentOut, status_code=201)
def attach_asset(asset_id: int, vehicle_id: int, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    asset = db.query(FleetAsset).filter(FleetAsset.id == asset_id, FleetAsset.organization_id == user.organization_id, FleetAsset.status == "active").first(); vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id, Vehicle.active.is_(True)).first()
    if not asset or not vehicle: raise HTTPException(404, "Active asset or vehicle not found")
    active = db.query(AssetAttachment).filter(AssetAttachment.asset_id == asset_id, AssetAttachment.detached_at.is_(None)).first()
    if active: raise HTTPException(409, "Asset is already attached")
    item = AssetAttachment(organization_id=user.organization_id, asset_id=asset_id, vehicle_id=vehicle_id); db.add(item); db.commit(); db.refresh(item); return item


@app.post("/api/v1/assets/{asset_id}/detach", response_model=AssetAttachmentOut)
def detach_asset(asset_id: int, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    item = db.query(AssetAttachment).filter(AssetAttachment.asset_id == asset_id, AssetAttachment.organization_id == user.organization_id, AssetAttachment.detached_at.is_(None)).first()
    if not item: raise HTTPException(404, "Active attachment not found")
    item.detached_at = datetime.now(timezone.utc); db.commit(); db.refresh(item); return item


def device_response(device: Device, db: Session) -> DeviceOut:
    binding = db.query(DeviceBinding).filter(DeviceBinding.device_id == device.id, DeviceBinding.unbound_at.is_(None)).first()
    return DeviceOut.model_validate(device, from_attributes=True).model_copy(update={"vehicle_id": binding.vehicle_id if binding else None})


@app.get("/api/v1/devices", response_model=list[DeviceOut])
def list_devices(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [device_response(item, db) for item in db.query(Device).filter(Device.organization_id == user.organization_id).order_by(Device.created_at.desc()).all()]


@app.get("/api/v1/devices/protocols")
def list_device_protocols(user: User = Depends(current_user)):
    return [{"key": key, "label": "Teltonika Codec 8/8E" if key == "teltonika" else "GT06 / Concox"} for key in supported_protocols()]


@app.get("/api/v1/sims", response_model=list[SIMCardOut])
def list_sims(status: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(SIMCard).filter(SIMCard.organization_id == user.organization_id)
    if status: query = query.filter(SIMCard.status == status)
    return query.order_by(SIMCard.created_at.desc()).all()


@app.post("/api/v1/sims", response_model=SIMCardOut, status_code=201)
def create_sim(body: SIMCardIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    if db.query(SIMCard).filter(SIMCard.organization_id == user.organization_id, SIMCard.iccid == body.iccid).first(): raise HTTPException(409, "ICCID already registered")
    item = SIMCard(organization_id=user.organization_id, **body.model_dump()); db.add(item); db.flush(); record_audit(db, user, "sim.created", "sim_card", item.id, {"operator": item.operator}); db.commit(); db.refresh(item); return item


@app.post("/api/v1/sims/{sim_id}/bind/{device_id}", response_model=SIMCardOut)
def bind_sim(sim_id: int, device_id: int, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    item = db.query(SIMCard).filter(SIMCard.id == sim_id, SIMCard.organization_id == user.organization_id).first(); device = db.query(Device).filter(Device.id == device_id, Device.organization_id == user.organization_id).first()
    if not item or not device: raise HTTPException(404, "SIM or device not found")
    if db.query(SIMCard).filter(SIMCard.device_id == device_id, SIMCard.id != sim_id, SIMCard.organization_id == user.organization_id).first(): raise HTTPException(409, "Device already has a SIM")
    item.device_id = device_id; record_audit(db, user, "sim.bound", "sim_card", item.id, {"device_id": device_id}); db.commit(); db.refresh(item); return item


@app.patch("/api/v1/sims/{sim_id}", response_model=SIMCardOut)
def update_sim(sim_id: int, body: SIMCardIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    item = db.query(SIMCard).filter(SIMCard.id == sim_id, SIMCard.organization_id == user.organization_id).first()
    if not item: raise HTTPException(404, "SIM not found")
    for field, value in body.model_dump().items(): setattr(item, field, value)
    record_audit(db, user, "sim.updated", "sim_card", item.id, {"status": item.status, "data_used_mb": item.data_used_mb}); db.commit(); db.refresh(item); return item


@app.post("/api/v1/devices", response_model=DeviceOut, status_code=201)
def create_device(body: DeviceIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    if db.query(Device).filter(Device.organization_id == user.organization_id, Device.imei == body.imei).first(): raise HTTPException(409, "IMEI already registered as a device")
    device = Device(organization_id=user.organization_id, **body.model_dump()); db.add(device); db.commit(); db.refresh(device); return device_response(device, db)


@app.get("/api/v1/devices/health", response_model=list[DeviceHealthOut])
def device_health(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now_utc = datetime.now(timezone.utc); output = []
    for device in db.query(Device).filter(Device.organization_id == user.organization_id).all():
        binding = db.query(DeviceBinding).filter(DeviceBinding.device_id == device.id, DeviceBinding.unbound_at.is_(None)).first()
        seen_at = device.last_seen_at.replace(tzinfo=timezone.utc) if device.last_seen_at and device.last_seen_at.tzinfo is None else device.last_seen_at
        age = (now_utc - seen_at).total_seconds() if seen_at else None
        health = "never_seen" if age is None else "online" if age <= 300 else "stale" if age <= 1800 else "offline"
        output.append(DeviceHealthOut(device_id=device.id, imei=device.imei, status=device.status, last_seen_at=device.last_seen_at, freshness_seconds=age, health=health, vehicle_id=binding.vehicle_id if binding else None))
    return output


@app.get("/api/v1/devices/{device_id}/commands", response_model=list[DeviceCommandOut])
def list_device_commands(device_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id, Device.organization_id == user.organization_id).first()
    if not device: raise HTTPException(404, "Device not found")
    return db.query(DeviceCommand).filter(DeviceCommand.device_id == device_id, DeviceCommand.organization_id == user.organization_id).order_by(DeviceCommand.created_at.desc()).limit(100).all()


@app.post("/api/v1/devices/{device_id}/commands", response_model=DeviceCommandOut, status_code=201)
async def issue_device_command(device_id: int, body: DeviceCommandIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id, Device.organization_id == user.organization_id).first()
    if not device: raise HTTPException(404, "Device not found")
    item = DeviceCommand(organization_id=user.organization_id, device_id=device_id, command=body.command, status="sent")
    db.add(item); db.commit(); db.refresh(item)
    response = await send_device_command(device.imei, body.command)
    item.response = response
    item.status = "acknowledged" if response else "timeout"
    item.acknowledged_at = datetime.now(timezone.utc) if response else None
    db.commit(); db.refresh(item); return item


@app.get("/api/v1/devices/{device_id}/bindings", response_model=list[DeviceBindingOut])
def list_device_bindings(device_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id, Device.organization_id == user.organization_id).first()
    if not device: raise HTTPException(404, "Device not found")
    return db.query(DeviceBinding).filter(DeviceBinding.device_id == device_id, DeviceBinding.organization_id == user.organization_id).order_by(DeviceBinding.bound_at.desc()).all()


@app.post("/api/v1/devices/{device_id}/bind/{vehicle_id}", response_model=DeviceOut)
def bind_device(device_id: int, vehicle_id: int, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id, Device.organization_id == user.organization_id, Device.status == "active").first(); vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id, Vehicle.active.is_(True)).first()
    if not device or not vehicle: raise HTTPException(404, "Active device or vehicle not found")
    active = db.query(DeviceBinding).filter(DeviceBinding.device_id == device_id, DeviceBinding.unbound_at.is_(None)).first()
    if active: active.unbound_at = datetime.now(timezone.utc)
    other = db.query(DeviceBinding).filter(DeviceBinding.vehicle_id == vehicle_id, DeviceBinding.unbound_at.is_(None)).first()
    if other: other.unbound_at = datetime.now(timezone.utc)
    db.add(DeviceBinding(organization_id=user.organization_id, device_id=device_id, vehicle_id=vehicle_id)); db.commit(); db.refresh(device); return device_response(device, db)


@app.get("/api/v1/vehicles/{vehicle_id}/profile", response_model=VehicleProfileOut)
def get_vehicle_profile(vehicle_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    return VehicleProfileOut(vehicle_id=vehicle.id, profile=vehicle.device_profile or "standard", config=vehicle.device_profile_config or {})


@app.post("/api/v1/vehicles/{vehicle_id}/profile", response_model=VehicleProfileOut)
def save_vehicle_profile(vehicle_id: int, body: VehicleProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    vehicle.device_profile = body.profile
    vehicle.device_profile_config = body.config or {}
    db.commit(); db.refresh(vehicle)
    return VehicleProfileOut(vehicle_id=vehicle.id, profile=vehicle.device_profile, config=vehicle.device_profile_config or {})


@app.delete("/api/v1/vehicles/{vehicle_id}/profile")
def delete_vehicle_profile(vehicle_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    vehicle.device_profile = "standard"
    vehicle.device_profile_config = {}
    db.commit()
    return {"message": "Vehicle profile reset"}


@app.get("/api/v1/vehicles/{vehicle_id}/history", response_model=list[PositionOut])
def vehicle_history(vehicle_id: int, since: datetime | None = None, until: datetime | None = None, limit: int = Query(1000, ge=1, le=10000), user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    query = db.query(Position).filter(Position.vehicle_id == vehicle_id, Position.organization_id == user.organization_id)
    if since: query = query.filter(Position.recorded_at >= since)
    if until: query = query.filter(Position.recorded_at <= until)
    return query.order_by(Position.recorded_at.asc()).limit(limit).all()


@app.get("/api/v1/vehicles/{vehicle_id}/activity", response_model=list[dict])
def vehicle_activity(vehicle_id: int, limit: int = Query(100, ge=1, le=500), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first(): raise HTTPException(404, "Vehicle not found")
    events: list[dict] = []
    for item in db.query(Alert).filter(Alert.vehicle_id == vehicle_id, Alert.organization_id == user.organization_id).order_by(Alert.created_at.desc()).limit(limit).all():
        events.append({"id": f"alert-{item.id}", "type": "alert", "title": item.kind.replace("_", " ").title(), "status": "acknowledged" if item.acknowledged else "open", "occurred_at": item.created_at, "detail": item.message})
    for item in db.query(WorkOrder).filter(WorkOrder.vehicle_id == vehicle_id, WorkOrder.organization_id == user.organization_id).order_by(WorkOrder.opened_at.desc()).limit(limit).all():
        events.append({"id": f"work-order-{item.id}", "type": "maintenance", "title": item.title, "status": item.status, "occurred_at": item.opened_at, "detail": f"Priority {item.priority} · cost {item.total_cost:.2f}"})
    for item in db.query(Inspection).filter(Inspection.vehicle_id == vehicle_id, Inspection.organization_id == user.organization_id).order_by(Inspection.submitted_at.desc()).limit(limit).all():
        events.append({"id": f"inspection-{item.id}", "type": "inspection", "title": f"{item.inspection_type.replace('_', ' ').title()} inspection", "status": item.status, "occurred_at": item.submitted_at, "detail": "Signed" if item.signature_file_id or item.signature_name else "Unsigned"})
    for item in db.query(FuelTransaction).filter(FuelTransaction.vehicle_id == vehicle_id, FuelTransaction.organization_id == user.organization_id).order_by(FuelTransaction.occurred_at.desc()).limit(limit).all():
        events.append({"id": f"fuel-{item.id}", "type": "fuel", "title": "Fuel transaction", "status": "anomaly" if item.anomaly else "recorded", "occurred_at": item.occurred_at, "detail": f"{item.liters:.1f} L · {item.total_cost:.2f}"})
    return sorted(events, key=lambda item: item["occurred_at"], reverse=True)[:limit]


@app.get("/api/v1/vehicles/{vehicle_id}/assignments", response_model=list[AssignmentOut])
def vehicle_assignments(vehicle_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(VehicleAssignment).filter(VehicleAssignment.vehicle_id == vehicle_id, VehicleAssignment.organization_id == user.organization_id).order_by(VehicleAssignment.assigned_at.desc()).all()


@app.post("/api/v1/vehicles/{vehicle_id}/assignments", response_model=AssignmentOut, status_code=201)
def assign_vehicle(vehicle_id: int, body: AssignmentIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first(); driver = db.query(Driver).filter(Driver.id == body.driver_id, Driver.organization_id == user.organization_id, Driver.active.is_(True)).first()
    if not vehicle or not driver: raise HTTPException(404, "Vehicle or driver not found")
    if not driver_is_assignable(body.driver_id, user.organization_id, db): raise HTTPException(409, "Driver is unavailable or has an expired certification")
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


@app.patch("/api/v1/vehicles/{vehicle_id}/thresholds", response_model=VehicleOut)
def update_thresholds(vehicle_id: int, body: VehicleThresholdPatch, user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    for field, value in body.model_dump(exclude_unset=True).items(): setattr(vehicle, field, value)
    db.commit(); db.refresh(vehicle)
    return vehicle


@app.get("/api/v1/vehicles/{vehicle_id}/reminders", response_model=list[MaintenanceReminderOut])
def list_reminders(vehicle_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    return db.query(MaintenanceReminder).filter(MaintenanceReminder.vehicle_id == vehicle_id).order_by(MaintenanceReminder.id.desc()).all()


@app.post("/api/v1/vehicles/{vehicle_id}/reminders", response_model=MaintenanceReminderOut, status_code=201)
def create_reminder(vehicle_id: int, body: MaintenanceReminderIn, user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    rem = MaintenanceReminder(organization_id=vehicle.organization_id, vehicle_id=vehicle_id, **body.model_dump())
    db.add(rem); db.commit(); db.refresh(rem)
    return rem


@app.delete("/api/v1/vehicles/{vehicle_id}/reminders/{reminder_id}", status_code=204)
def delete_reminder(vehicle_id: int, reminder_id: int, user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    rem = db.query(MaintenanceReminder).filter(MaintenanceReminder.id == reminder_id, MaintenanceReminder.vehicle_id == vehicle_id, MaintenanceReminder.organization_id == user.organization_id).first()
    if not rem: raise HTTPException(404, "Reminder not found")
    db.delete(rem); db.commit()


def service_plan_out(plan: ServicePlan, db: Session) -> ServicePlanOut:
    odo = db.query(VehicleOdometer).filter(VehicleOdometer.vehicle_id == plan.vehicle_id).first()
    distance = odo.total_distance_m if odo else 0
    engine_hours = odo.engine_hours_s if odo else 0
    reasons = []
    if plan.interval_distance_m and distance >= plan.last_service_distance_m + plan.interval_distance_m:
        reasons.append("distance")
    if plan.interval_engine_hours_s and engine_hours >= plan.last_service_engine_hours_s + plan.interval_engine_hours_s:
        reasons.append("engine hours")
    return ServicePlanOut.model_validate(plan, from_attributes=True).model_copy(update={"due": bool(reasons), "due_reason": " and ".join(reasons) or None})


@app.get("/api/v1/service-plans", response_model=list[ServicePlanOut])
def list_service_plans(vehicle_id: int | None = None, due_only: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(ServicePlan).filter(ServicePlan.organization_id == user.organization_id, ServicePlan.active.is_(True))
    if vehicle_id is not None:
        query = query.filter(ServicePlan.vehicle_id == vehicle_id)
    plans = [service_plan_out(plan, db) for plan in query.order_by(ServicePlan.name).all()]
    return [plan for plan in plans if plan.due] if due_only else plans


@app.post("/api/v1/service-plans", response_model=ServicePlanOut, status_code=201)
def create_service_plan(body: ServicePlanIn, user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == body.vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")
    odo = db.query(VehicleOdometer).filter(VehicleOdometer.vehicle_id == body.vehicle_id).first()
    plan = ServicePlan(organization_id=user.organization_id, **body.model_dump(), last_service_distance_m=odo.total_distance_m if odo else 0, last_service_engine_hours_s=odo.engine_hours_s if odo else 0)
    db.add(plan); db.commit(); db.refresh(plan)
    return service_plan_out(plan, db)


@app.post("/api/v1/service-plans/{plan_id}/work-orders", response_model=WorkOrderOut, status_code=201)
def create_due_work_order(plan_id: int, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    plan = db.query(ServicePlan).filter(ServicePlan.id == plan_id, ServicePlan.organization_id == user.organization_id, ServicePlan.active.is_(True)).first()
    if not plan:
        raise HTTPException(404, "Service plan not found")
    if not service_plan_out(plan, db).due:
        raise HTTPException(409, "Service plan is not due")
    existing = db.query(WorkOrder).filter(WorkOrder.service_plan_id == plan.id, WorkOrder.status.in_(("open", "in_progress", "on_hold"))).first()
    if existing:
        raise HTTPException(409, "An open work order already exists for this service plan")
    order = WorkOrder(organization_id=user.organization_id, vehicle_id=plan.vehicle_id, service_plan_id=plan.id, title=f"Service: {plan.name}", description=plan.description, priority="medium")
    db.add(order); db.commit(); db.refresh(order)
    return order


def part_out(part: Part) -> PartOut:
    return PartOut.model_validate(part, from_attributes=True).model_copy(update={"low_stock": part.quantity_on_hand <= part.reorder_level})


@app.get("/api/v1/parts", response_model=list[PartOut])
def list_parts(low_stock_only: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    parts = db.query(Part).filter(Part.organization_id == user.organization_id, Part.active.is_(True)).order_by(Part.name).all()
    result = [part_out(part) for part in parts]
    return [part for part in result if part.low_stock] if low_stock_only else result


@app.post("/api/v1/parts", response_model=PartOut, status_code=201)
def create_part(body: PartIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    if db.query(Part).filter(Part.organization_id == user.organization_id, Part.sku == body.sku).first():
        raise HTTPException(409, "A part with this SKU already exists")
    part = Part(organization_id=user.organization_id, **body.model_dump())
    db.add(part); db.commit(); db.refresh(part)
    return part_out(part)


@app.get("/api/v1/vendors", response_model=list[VendorOut])
def list_vendors(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Vendor).filter(Vendor.organization_id == user.organization_id, Vendor.active.is_(True)).order_by(Vendor.name).all()


@app.post("/api/v1/vendors", response_model=VendorOut, status_code=201)
def create_vendor(body: VendorIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    vendor = Vendor(organization_id=user.organization_id, **body.model_dump())
    db.add(vendor); db.commit(); db.refresh(vendor)
    return vendor


@app.get("/api/v1/work-orders/{work_order_id}/parts", response_model=list[WorkOrderPartOut])
def list_work_order_parts(work_order_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id, WorkOrder.organization_id == user.organization_id).first()
    if not order:
        raise HTTPException(404, "Work order not found")
    return db.query(WorkOrderPart).filter(WorkOrderPart.work_order_id == order.id).order_by(WorkOrderPart.id).all()


@app.post("/api/v1/work-orders/{work_order_id}/parts", response_model=WorkOrderPartOut, status_code=201)
def add_work_order_part(work_order_id: int, body: WorkOrderPartIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id, WorkOrder.organization_id == user.organization_id).first()
    part = db.query(Part).filter(Part.id == body.part_id, Part.organization_id == user.organization_id, Part.active.is_(True)).first()
    if not order or not part:
        raise HTTPException(404, "Work order or part not found")
    if order.status in ("completed", "cancelled"):
        raise HTTPException(409, "Parts cannot be changed on a closed work order")
    existing = db.query(WorkOrderPart).filter(WorkOrderPart.work_order_id == order.id, WorkOrderPart.part_id == part.id).first()
    reserved = db.query(func.coalesce(func.sum(WorkOrderPart.quantity), 0)).join(WorkOrder).filter(WorkOrderPart.part_id == part.id, WorkOrderPart.consumed_at.is_(None), WorkOrder.status.in_(("open", "in_progress", "on_hold")), WorkOrder.id != order.id).scalar() or 0
    requested_total = (existing.quantity if existing else 0) + body.quantity
    if reserved + requested_total > part.quantity_on_hand:
        raise HTTPException(409, f"Insufficient stock for {part.name}")
    if existing:
        existing.quantity = requested_total
        line = existing
    else:
        line = WorkOrderPart(work_order_id=order.id, part_id=part.id, quantity=body.quantity, unit_cost=part.unit_cost)
        db.add(line)
    db.flush()
    order.parts_cost = db.query(func.coalesce(func.sum(WorkOrderPart.quantity * WorkOrderPart.unit_cost), 0)).filter(WorkOrderPart.work_order_id == order.id).scalar() or 0
    db.commit(); db.refresh(line)
    return line


@app.get("/api/v1/inspections", response_model=list[InspectionOut])
def list_inspections(vehicle_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(Inspection).filter(Inspection.organization_id == user.organization_id)
    if vehicle_id is not None:
        query = query.filter(Inspection.vehicle_id == vehicle_id)
    return query.order_by(Inspection.submitted_at.desc()).limit(500).all()


@app.get("/api/v1/inspection-templates", response_model=list[InspectionTemplateOut])
def list_inspection_templates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(InspectionTemplate).filter(InspectionTemplate.organization_id == user.organization_id, InspectionTemplate.active.is_(True)).order_by(InspectionTemplate.name).all()


@app.post("/api/v1/inspection-templates", response_model=InspectionTemplateOut, status_code=201)
def create_inspection_template(body: InspectionTemplateIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    template = InspectionTemplate(organization_id=user.organization_id, **body.model_dump()); db.add(template); db.commit(); db.refresh(template); return template


@app.post("/api/v1/inspections", response_model=InspectionOut, status_code=201)
def create_inspection(body: InspectionIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == body.vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")
    if body.inspector_id and not db.query(Driver).filter(Driver.id == body.inspector_id, Driver.organization_id == user.organization_id).first():
        raise HTTPException(404, "Inspector not found")
    if body.template_id and not db.query(InspectionTemplate).filter(InspectionTemplate.id == body.template_id, InspectionTemplate.organization_id == user.organization_id, InspectionTemplate.active.is_(True)).first():
        raise HTTPException(404, "Inspection template not found")
    file_ids = set(body.evidence_file_ids + ([body.signature_file_id] if body.signature_file_id else []))
    if file_ids and db.query(EvidenceFile).filter(EvidenceFile.organization_id == user.organization_id, EvidenceFile.id.in_(file_ids)).count() != len(file_ids):
        raise HTTPException(404, "One or more evidence files not found")
    if body.signature_file_id and not db.query(EvidenceFile).filter(EvidenceFile.id == body.signature_file_id, EvidenceFile.organization_id == user.organization_id, EvidenceFile.purpose == "signature").first():
        raise HTTPException(400, "Signature file must be uploaded with purpose=signature")
    signed_at = datetime.now(timezone.utc) if body.signature_name else None
    signed_at = datetime.now(timezone.utc) if body.signature_file_id else signed_at
    inspection = Inspection(organization_id=user.organization_id, vehicle_id=body.vehicle_id, inspector_id=body.inspector_id, template_id=body.template_id, inspection_type=body.inspection_type, notes=body.notes, checklist_results=body.checklist_results, evidence_urls=body.evidence_urls, evidence_file_ids=body.evidence_file_ids, signature_file_id=body.signature_file_id, signature_name=body.signature_name, signed_at=signed_at)
    db.add(inspection); db.flush()
    for defect in body.defects:
        created_defect = Defect(organization_id=user.organization_id, vehicle_id=body.vehicle_id, inspection_id=inspection.id, **defect.model_dump()); db.add(created_defect); db.flush()
        if defect.severity == "critical":
            db.add(WorkOrder(organization_id=user.organization_id, vehicle_id=body.vehicle_id, defect_id=created_defect.id, title=f"Corrective action: {defect.title}", description=defect.description, priority="critical"))
    record_audit(db, user, "inspection.created", "inspection", inspection.id, {"defects": len(body.defects), "signed": bool(body.signature_file_id or body.signature_name)})
    db.commit(); db.refresh(inspection)
    return inspection


@app.get("/api/v1/defects", response_model=list[DefectOut])
def list_defects(status: str | None = None, vehicle_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(Defect).filter(Defect.organization_id == user.organization_id)
    if status:
        query = query.filter(Defect.status == status)
    if vehicle_id is not None:
        query = query.filter(Defect.vehicle_id == vehicle_id)
    return query.order_by(Defect.reported_at.desc()).limit(500).all()


@app.get("/api/v1/work-orders", response_model=list[WorkOrderOut])
def list_work_orders(status: str | None = None, vehicle_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(WorkOrder).filter(WorkOrder.organization_id == user.organization_id)
    if status:
        query = query.filter(WorkOrder.status == status)
    if vehicle_id is not None:
        query = query.filter(WorkOrder.vehicle_id == vehicle_id)
    return query.order_by(WorkOrder.opened_at.desc()).limit(500).all()


@app.post("/api/v1/work-orders", response_model=WorkOrderOut, status_code=201)
def create_work_order(body: WorkOrderIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == body.vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")
    if body.vendor_id is not None and not db.query(Vendor).filter(Vendor.id == body.vendor_id, Vendor.organization_id == user.organization_id, Vendor.active.is_(True)).first():
        raise HTTPException(404, "Vendor not found")
    defect = None
    if body.defect_id is not None:
        defect = db.query(Defect).filter(Defect.id == body.defect_id, Defect.organization_id == user.organization_id, Defect.vehicle_id == body.vehicle_id).first()
        if not defect:
            raise HTTPException(404, "Defect not found for this vehicle")
        if defect.status == "resolved":
            raise HTTPException(409, "Resolved defects cannot be assigned to a work order")
        defect.status = "in_progress"
    order = WorkOrder(organization_id=user.organization_id, **body.model_dump())
    db.add(order); db.commit(); db.refresh(order)
    return order


@app.patch("/api/v1/work-orders/{work_order_id}", response_model=WorkOrderOut)
def update_work_order(work_order_id: int, body: WorkOrderPatch, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id, WorkOrder.organization_id == user.organization_id).first()
    if not order:
        raise HTTPException(404, "Work order not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("vendor_id") is not None and not db.query(Vendor).filter(Vendor.id == changes["vendor_id"], Vendor.organization_id == user.organization_id, Vendor.active.is_(True)).first():
        raise HTTPException(404, "Vendor not found")
    for field, value in changes.items():
        setattr(order, field, value)
    if changes.get("status") == "completed":
        order.completed_at = datetime.now(timezone.utc)
        if order.downtime_started_at and not order.downtime_ended_at:
            order.downtime_ended_at = order.completed_at
        lines = db.query(WorkOrderPart).filter(WorkOrderPart.work_order_id == order.id, WorkOrderPart.consumed_at.is_(None)).all()
        for line in lines:
            part = db.query(Part).filter(Part.id == line.part_id, Part.organization_id == user.organization_id).first()
            if not part or part.quantity_on_hand < line.quantity:
                raise HTTPException(409, "Part stock changed; refresh the work order before completing it")
            part.quantity_on_hand -= line.quantity
            line.consumed_at = order.completed_at
        if order.defect_id:
            defect = db.query(Defect).filter(Defect.id == order.defect_id, Defect.organization_id == user.organization_id).first()
            if defect:
                defect.status = "resolved"; defect.resolved_at = order.completed_at
        if order.service_plan_id:
            plan = db.query(ServicePlan).filter(ServicePlan.id == order.service_plan_id, ServicePlan.organization_id == user.organization_id).first()
            if plan:
                odo = db.query(VehicleOdometer).filter(VehicleOdometer.vehicle_id == order.vehicle_id).first()
                plan.last_service_distance_m = odo.total_distance_m if odo else 0
                plan.last_service_engine_hours_s = odo.engine_hours_s if odo else 0
                plan.last_serviced_at = order.completed_at
    elif "status" in changes and changes["status"] != "completed":
        order.completed_at = None
    db.commit(); db.refresh(order)
    return order


@app.post("/api/v1/work-orders/{work_order_id}/downtime/start", response_model=WorkOrderOut)
def start_work_order_downtime(work_order_id: int, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id, WorkOrder.organization_id == user.organization_id).first()
    if not order:
        raise HTTPException(404, "Work order not found")
    if order.status in ("completed", "cancelled"):
        raise HTTPException(409, "Cannot start downtime for a closed work order")
    if not order.downtime_started_at:
        order.downtime_started_at = datetime.now(timezone.utc)
        order.downtime_ended_at = None
        db.commit(); db.refresh(order)
    return order


@app.post("/api/v1/work-orders/{work_order_id}/downtime/stop", response_model=WorkOrderOut)
def stop_work_order_downtime(work_order_id: int, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id, WorkOrder.organization_id == user.organization_id).first()
    if not order:
        raise HTTPException(404, "Work order not found")
    if not order.downtime_started_at:
        raise HTTPException(409, "Downtime has not been started")
    if not order.downtime_ended_at:
        order.downtime_ended_at = datetime.now(timezone.utc)
        db.commit(); db.refresh(order)
    return order


@app.post("/api/v1/vehicles/{vehicle_id}/eta")
def calculate_eta(vehicle_id: int, body: ETARequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    last = db.query(Position).filter(Position.vehicle_id == vehicle_id).order_by(Position.recorded_at.desc()).first()
    if not last: raise HTTPException(404, "No position data")
    metrics = route_metrics([(last.latitude, last.longitude), (body.dest_lat, body.dest_lon)], last.speed_kph if last.speed_kph > 5 else 40.0)
    dist_m = metrics["distance_m"]
    speed = last.speed_kph if last.speed_kph > 5 else 40.0  # fallback 40 km/h if stopped
    return {"vehicle_id": vehicle_id, "current_lat": last.latitude, "current_lon": last.longitude, "dest_lat": body.dest_lat, "dest_lon": body.dest_lon, "distance_m": round(dist_m), "speed_kph": speed, "eta_minutes": round(metrics["estimated_minutes"], 1), "provider": metrics["provider"], "traffic_aware": metrics["traffic_aware"], "traffic_factor": metrics["traffic_factor"]}


@app.get("/api/v1/vehicles/{vehicle_id}/trail", response_model=list[PositionOut])
def vehicle_trail(vehicle_id: int, limit: int = Query(50, ge=5, le=500), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Last N positions for live map trail."""
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    return db.query(Position).filter(Position.vehicle_id == vehicle_id).order_by(Position.recorded_at.desc()).limit(limit).all()


@app.get("/api/v1/vehicles/{vehicle_id}/odometer", response_model=OdometerOut)
def get_odometer(vehicle_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    odo = db.query(VehicleOdometer).filter(VehicleOdometer.vehicle_id == vehicle_id).first()
    return OdometerOut(vehicle_id=vehicle_id, total_distance_m=odo.total_distance_m if odo else 0, engine_hours_s=odo.engine_hours_s if odo else 0)


@app.get("/api/v1/fuel/transactions", response_model=list[FuelTransactionOut])
def list_fuel_transactions(vehicle_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(FuelTransaction).filter(FuelTransaction.organization_id == user.organization_id)
    if vehicle_id is not None: query = query.filter(FuelTransaction.vehicle_id == vehicle_id)
    return query.order_by(FuelTransaction.occurred_at.desc()).limit(500).all()


@app.post("/api/v1/fuel/transactions", response_model=FuelTransactionOut, status_code=201)
def create_fuel_transaction(body: FuelTransactionIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == body.vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    if body.driver_id and not db.query(Driver).filter(Driver.id == body.driver_id, Driver.organization_id == user.organization_id).first(): raise HTTPException(404, "Driver not found")
    previous = db.query(FuelTransaction).filter(FuelTransaction.vehicle_id == body.vehicle_id, FuelTransaction.organization_id == user.organization_id, FuelTransaction.odometer_m.is_not(None)).order_by(FuelTransaction.odometer_m.desc()).first()
    cost_per_liter = body.total_cost / body.liters
    distance = body.odometer_m - previous.odometer_m if previous and body.odometer_m is not None and previous.odometer_m is not None else 0
    anomaly = cost_per_liter > 300 or (distance > 0 and body.liters / distance * 100_000 > 40)
    item = FuelTransaction(organization_id=user.organization_id, occurred_at=body.occurred_at or datetime.now(timezone.utc), anomaly=anomaly, **{k: v for k, v in body.model_dump().items() if k != "occurred_at"})
    db.add(item); db.commit(); db.refresh(item); return item


@app.get("/api/v1/fuel/summary", response_model=list[FuelSummaryOut])
def fuel_summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicles = db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id).all(); result = []
    for vehicle in vehicles:
        rows = db.query(FuelTransaction).filter(FuelTransaction.vehicle_id == vehicle.id, FuelTransaction.organization_id == user.organization_id).order_by(FuelTransaction.odometer_m.asc()).all()
        if not rows: continue
        liters = sum(row.liters for row in rows); cost = sum(row.total_cost for row in rows); meters = [row.odometer_m for row in rows if row.odometer_m is not None]
        distance = max(meters) - min(meters) if len(meters) > 1 else 0
        result.append(FuelSummaryOut(vehicle_id=vehicle.id, transactions=len(rows), liters=round(liters, 2), total_cost=round(cost, 2), cost_per_liter=round(cost / liters, 2), distance_m=round(distance, 2), liters_per_100km=round(liters / distance * 100_000, 2) if distance > 0 else None, anomaly_count=sum(1 for row in rows if row.anomaly)))
    return result


@app.get("/api/v1/finance/vehicle-rollups", response_model=list[VehicleCostRollupOut])
def vehicle_cost_rollups(user: User = Depends(current_user), db: Session = Depends(get_db)):
    result = []
    for vehicle in db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id).all():
        odo = db.query(VehicleOdometer).filter(VehicleOdometer.vehicle_id == vehicle.id).first()
        distance = odo.total_distance_m if odo else 0
        fuel_cost = db.query(func.coalesce(func.sum(FuelTransaction.total_cost), 0)).filter(FuelTransaction.vehicle_id == vehicle.id, FuelTransaction.organization_id == user.organization_id).scalar() or 0
        orders = db.query(WorkOrder).filter(WorkOrder.vehicle_id == vehicle.id, WorkOrder.organization_id == user.organization_id).all()
        maintenance = sum(order.total_cost for order in orders)
        downtime = sum(((order.downtime_ended_at or datetime.now(timezone.utc)) - order.downtime_started_at).total_seconds() for order in orders if order.downtime_started_at)
        total = float(fuel_cost) + maintenance
        result.append(VehicleCostRollupOut(vehicle_id=vehicle.id, distance_m=distance, fuel_cost=round(float(fuel_cost), 2), maintenance_cost=round(maintenance, 2), downtime_seconds=round(downtime, 2), total_cost=round(total, 2), cost_per_km=round(total / distance * 1000, 2) if distance > 0 else None, utilization_percent=round(min((odo.engine_hours_s / 3600) / 720 * 100, 100), 2) if odo else 0))
    return result


@app.get("/api/v1/vehicles/{vehicle_id}/auto-trips", response_model=list[AutoTripOut])
def list_auto_trips(vehicle_id: int, limit: int = Query(100, ge=1, le=500), user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    return db.query(AutoTrip).filter(AutoTrip.vehicle_id == vehicle_id).order_by(AutoTrip.id.desc()).limit(limit).all()


@app.get("/api/v1/vehicles/{vehicle_id}/telematics")
def get_telematics(vehicle_id: int, limit: int = Query(200, ge=1, le=1000), user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    rows = db.query(Position).filter(
        Position.vehicle_id == vehicle_id,
        (Position.harsh_braking.is_(True) | Position.harsh_acceleration.is_(True) | Position.harsh_cornering.is_(True) | Position.towing.is_(True) | Position.jamming.is_(True) | Position.sos.is_(True))
    ).order_by(Position.recorded_at.desc()).limit(limit).all()
    events = []
    for r in rows:
        for kind in ("harsh_braking", "harsh_acceleration", "harsh_cornering", "towing", "jamming", "sos"):
            if getattr(r, kind):
                events.append({"kind": kind, "recorded_at": r.recorded_at, "latitude": r.latitude, "longitude": r.longitude, "speed_kph": r.speed_kph})
    odo = db.query(VehicleOdometer).filter(VehicleOdometer.vehicle_id == vehicle_id).first()
    trips = db.query(AutoTrip).filter(AutoTrip.vehicle_id == vehicle_id, AutoTrip.ended_at.isnot(None)).all()
    avg_score = round(sum(t.driver_score for t in trips) / len(trips), 1) if trips else 100.0
    return {"vehicle_id": vehicle_id, "events": events, "total_distance_m": odo.total_distance_m if odo else 0, "engine_hours_s": odo.engine_hours_s if odo else 0, "avg_driver_score": avg_score, "total_trips": len(trips)}


@app.post("/api/v1/vehicles/{vehicle_id}/immobilizer")
async def toggle_immobilizer(vehicle_id: int, body: dict, user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.organization_id == user.organization_id).first()
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    if vehicle.protocol != "teltonika": raise HTTPException(400, "Immobilizer only supported for Teltonika devices")
    enable = bool(body.get("enable", True))
    cmd = "setdigout 1 1" if enable else "setdigout 1 0"
    result = await send_device_command(vehicle.imei, cmd)
    if result is None: raise HTTPException(503, "Device not connected")
    return {"imei": vehicle.imei, "immobilized": enable, "response": result}


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


@app.get("/api/v1/telemetry/events", response_model=list[TelemetryEventOut])
def telemetry_events(vehicle_id: int | None = None, event_type: str | None = None, limit: int = Query(100, ge=1, le=1000), user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(TelemetryEvent).filter(TelemetryEvent.organization_id == user.organization_id)
    if vehicle_id is not None: query = query.filter(TelemetryEvent.vehicle_id == vehicle_id)
    if event_type: query = query.filter(TelemetryEvent.event_type == event_type)
    return query.order_by(TelemetryEvent.recorded_at.desc()).limit(limit).all()


@app.get("/api/v1/telemetry/series", response_model=list[PositionOut])
def telemetry_series(vehicle_id: int, since: datetime | None = None, until: datetime | None = None, max_points: int = Query(1000, ge=10, le=10000), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Return a bounded, chronologically ordered series for charts and replay."""
    query = db.query(Position).filter(Position.vehicle_id == vehicle_id, Position.organization_id == user.organization_id)
    if since: query = query.filter(Position.recorded_at >= since)
    if until: query = query.filter(Position.recorded_at <= until)
    rows = query.order_by(Position.recorded_at.asc()).all()
    if len(rows) > max_points:
        stride = max(1, len(rows) // max_points)
        rows = rows[::stride][:max_points]
    return rows


@app.get("/api/v1/dashboard/summary")
def summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    vehicles = db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id).all()
    cutoff = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).timestamp() - 900
    active = sum(1 for v in vehicles if v.last_seen_at and v.last_seen_at.timestamp() >= cutoff)
    alerts = db.query(func.count(Alert.id)).filter(Alert.organization_id == user.organization_id, Alert.acknowledged.is_(False)).scalar() or 0
    return {"total_vehicles": len(vehicles), "online_vehicles": active, "offline_vehicles": len(vehicles) - active, "open_alerts": alerts}


@app.get("/api/v1/live/state")
def live_state(user: User = Depends(current_user)):
    return get_vehicle_states(user.organization_id)


@app.get("/api/v1/dashboard/exceptions", response_model=list[FleetExceptionOut])
def dashboard_exceptions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now_utc = datetime.now(timezone.utc); items: list[FleetExceptionOut] = []
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    for item in db.query(DeliveryException).filter(DeliveryException.organization_id == user.organization_id, DeliveryException.status == "open").all():
        items.append(FleetExceptionOut(id=f"delivery-{item.id}", category="dispatch", severity="high" if item.kind in ("late_stop", "failed_delivery") else "medium", title=item.kind.replace("_", " ").title(), detail=item.message, created_at=item.created_at, next_action="Open dispatch exception and assign an owner", href="/dispatch"))
    for item in db.query(SafetyIncident).filter(SafetyIncident.organization_id == user.organization_id, SafetyIncident.status.in_(("open", "investigating"))).all():
        items.append(FleetExceptionOut(id=f"incident-{item.id}", category="safety", severity=item.severity, title=item.title, detail=item.description or "Safety incident requires investigation", created_at=item.created_at, next_action="Review evidence and start investigation", href="/incidents"))
    for item in db.query(Defect).filter(Defect.organization_id == user.organization_id, Defect.status == "open", Defect.severity.in_(("major", "critical"))).all():
        items.append(FleetExceptionOut(id=f"defect-{item.id}", category="maintenance", severity="critical" if item.severity == "critical" else "high", title=item.title, detail=item.description or "Vehicle defect has not been resolved", created_at=item.reported_at, next_action="Open corrective work order", href="/inspections"))
    for item in db.query(DriverCertification).filter(DriverCertification.organization_id == user.organization_id, DriverCertification.expires_at.is_not(None), DriverCertification.expires_at <= now_utc).all():
        items.append(FleetExceptionOut(id=f"certification-{item.id}", category="compliance", severity="high", title=f"Expired certification: {item.name}", detail=f"Driver {item.driver_id} is not compliant for assignment", created_at=item.expires_at or now_utc, next_action="Renew certification before dispatch", href="/certifications"))
    for vehicle in db.query(Vehicle).filter(Vehicle.organization_id == user.organization_id, Vehicle.active.is_(True)).all():
        seen = vehicle.last_seen_at.replace(tzinfo=timezone.utc) if vehicle.last_seen_at and vehicle.last_seen_at.tzinfo is None else vehicle.last_seen_at
        if not seen or seen < now_utc - timedelta(minutes=30):
            items.append(FleetExceptionOut(id=f"offline-{vehicle.id}", category="telematics", severity="high", title=f"{vehicle.name} is offline", detail="No telemetry received in the last 30 minutes", created_at=seen or now_utc, next_action="Check tracker power, network, and device binding", href="/devices"))
    return sorted(items, key=lambda item: (-severity_rank[item.severity], item.created_at))[:100]


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


@app.get("/api/v1/incidents", response_model=list[IncidentOut])
def list_incidents(status: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(SafetyIncident).filter(SafetyIncident.organization_id == user.organization_id)
    if status: query = query.filter(SafetyIncident.status == status)
    return query.order_by(SafetyIncident.created_at.desc()).limit(500).all()


@app.post("/api/v1/incidents", response_model=IncidentOut, status_code=201)
def create_incident(body: IncidentIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    if body.vehicle_id and not db.query(Vehicle).filter(Vehicle.id == body.vehicle_id, Vehicle.organization_id == user.organization_id).first(): raise HTTPException(404, "Vehicle not found")
    if body.driver_id and not db.query(Driver).filter(Driver.id == body.driver_id, Driver.organization_id == user.organization_id).first(): raise HTTPException(404, "Driver not found")
    if body.evidence_file_ids and db.query(EvidenceFile).filter(EvidenceFile.organization_id == user.organization_id, EvidenceFile.id.in_(body.evidence_file_ids)).count() != len(set(body.evidence_file_ids)):
        raise HTTPException(404, "One or more evidence files not found")
    item = SafetyIncident(organization_id=user.organization_id, **body.model_dump()); db.add(item); db.flush(); record_audit(db, user, "incident.created", "safety_incident", item.id, {"severity": item.severity}); db.commit(); db.refresh(item); return item


@app.patch("/api/v1/incidents/{incident_id}", response_model=IncidentOut)
def update_incident(incident_id: int, body: IncidentPatch, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    item = db.query(SafetyIncident).filter(SafetyIncident.id == incident_id, SafetyIncident.organization_id == user.organization_id).first()
    if not item: raise HTTPException(404, "Incident not found")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items(): setattr(item, field, value)
    if changes.get("status") == "resolved": item.resolved_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(item); return item


@app.get("/api/v1/incidents/{incident_id}/actions", response_model=list[CorrectiveActionOut])
def list_corrective_actions(incident_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(CorrectiveAction).filter(CorrectiveAction.incident_id == incident_id, CorrectiveAction.organization_id == user.organization_id).order_by(CorrectiveAction.id.desc()).all()


@app.post("/api/v1/incidents/{incident_id}/actions", response_model=CorrectiveActionOut, status_code=201)
def create_corrective_action(incident_id: int, body: CorrectiveActionIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    incident = db.query(SafetyIncident).filter(SafetyIncident.id == incident_id, SafetyIncident.organization_id == user.organization_id).first()
    if not incident: raise HTTPException(404, "Incident not found")
    item = CorrectiveAction(organization_id=user.organization_id, incident_id=incident_id, **body.model_dump()); db.add(item); db.commit(); db.refresh(item); return item


@app.post("/api/v1/incidents/{incident_id}/actions/{action_id}/complete", response_model=CorrectiveActionOut)
def complete_corrective_action(incident_id: int, action_id: int, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    item = db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id, CorrectiveAction.incident_id == incident_id, CorrectiveAction.organization_id == user.organization_id).first()
    if not item: raise HTTPException(404, "Corrective action not found")
    item.status = "completed"; item.completed_at = datetime.now(timezone.utc); db.commit(); db.refresh(item); return item


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


@app.get("/api/v1/drivers/{driver_id}/certifications", response_model=list[DriverCertificationOut])
def list_driver_certifications(driver_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(DriverCertification).filter(DriverCertification.driver_id == driver_id, DriverCertification.organization_id == user.organization_id).all()


@app.post("/api/v1/drivers/{driver_id}/certifications", response_model=DriverCertificationOut, status_code=201)
def create_driver_certification(driver_id: int, body: DriverCertificationIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.id == driver_id, Driver.organization_id == user.organization_id).first()
    if not driver: raise HTTPException(404, "Driver not found")
    status = "expired" if body.expires_at and body.expires_at <= datetime.now(timezone.utc) else "valid"
    item = DriverCertification(organization_id=user.organization_id, driver_id=driver_id, status=status, **body.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item


@app.get("/api/v1/drivers/{driver_id}/availability", response_model=list[DriverAvailabilityOut])
def list_driver_availability(driver_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(DriverAvailability).filter(DriverAvailability.driver_id == driver_id, DriverAvailability.organization_id == user.organization_id).order_by(DriverAvailability.available_from.desc()).limit(100).all()


@app.get("/api/v1/drivers/{driver_id}/duty-logs", response_model=list[DriverDutyLogOut])
def list_driver_duty_logs(driver_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(DriverDutyLog).filter(DriverDutyLog.driver_id == driver_id, DriverDutyLog.organization_id == user.organization_id).order_by(DriverDutyLog.started_at.desc()).limit(500).all()


@app.post("/api/v1/drivers/{driver_id}/duty-logs", response_model=DriverDutyLogOut, status_code=201)
def create_driver_duty_log(driver_id: int, body: DriverDutyLogIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.id == driver_id, Driver.organization_id == user.organization_id, Driver.active.is_(True)).first()
    if not driver: raise HTTPException(404, "Driver not found")
    end = body.ended_at or datetime.now(timezone.utc)
    overlap = db.query(DriverDutyLog).filter(DriverDutyLog.driver_id == driver_id, DriverDutyLog.organization_id == user.organization_id, DriverDutyLog.started_at < end, (DriverDutyLog.ended_at.is_(None)) | (DriverDutyLog.ended_at > body.started_at)).first()
    if overlap: raise HTTPException(409, "Duty segment overlaps an existing segment")
    item = DriverDutyLog(organization_id=user.organization_id, driver_id=driver_id, **body.model_dump()); db.add(item); db.flush(); record_audit(db, user, "driver.duty_log.created", "driver_duty_log", item.id, {"status": item.status}); db.commit(); db.refresh(item); return item


@app.get("/api/v1/drivers/{driver_id}/hours", response_model=DriverHoursOut)
def driver_hours(driver_id: int, at: datetime | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not db.query(Driver).filter(Driver.id == driver_id, Driver.organization_id == user.organization_id).first(): raise HTTPException(404, "Driver not found")
    end = at or datetime.now(timezone.utc); start = end - timedelta(hours=24)
    logs = db.query(DriverDutyLog).filter(DriverDutyLog.driver_id == driver_id, DriverDutyLog.organization_id == user.organization_id, DriverDutyLog.started_at < end, (DriverDutyLog.ended_at.is_(None)) | (DriverDutyLog.ended_at > start)).all()
    on_duty = driving = 0
    for log in logs:
        left = max(log.started_at, start); right = min(log.ended_at or end, end)
        seconds = max(0, int((right - left).total_seconds()))
        if log.status in ("on_duty", "driving"): on_duty += seconds
        if log.status == "driving": driving += seconds
    return DriverHoursOut(driver_id=driver_id, window_start=start, on_duty_seconds=on_duty, driving_seconds=driving, remaining_on_duty_seconds=max(0, 14 * 3600 - on_duty), remaining_driving_seconds=max(0, 11 * 3600 - driving), compliant=on_duty <= 14 * 3600 and driving <= 11 * 3600)


@app.post("/api/v1/drivers/{driver_id}/availability", response_model=DriverAvailabilityOut, status_code=201)
def create_driver_availability(driver_id: int, body: DriverAvailabilityIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.id == driver_id, Driver.organization_id == user.organization_id).first()
    if not driver: raise HTTPException(404, "Driver not found")
    item = DriverAvailability(organization_id=user.organization_id, driver_id=driver_id, **body.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item


def driver_is_assignable(driver_id: int, organization_id: int, db: Session, at: datetime | None = None) -> bool:
    when = at or datetime.now(timezone.utc)
    driver = db.query(Driver).filter(Driver.id == driver_id, Driver.organization_id == organization_id, Driver.active.is_(True)).first()
    if not driver: return False
    expired = db.query(DriverCertification).filter(DriverCertification.driver_id == driver_id, DriverCertification.organization_id == organization_id, DriverCertification.expires_at.is_not(None), DriverCertification.expires_at <= when).first()
    if expired: return False
    availability = db.query(DriverAvailability).filter(DriverAvailability.driver_id == driver_id, DriverAvailability.organization_id == organization_id, DriverAvailability.available_from <= when, DriverAvailability.available_until >= when).order_by(DriverAvailability.available_from.desc()).first()
    return availability is None or availability.status == "available"


@app.get("/api/v1/drivers/safety", response_model=list[DriverSafetyOut])
def driver_safety_scores(user: User = Depends(current_user), db: Session = Depends(get_db)):
    result = []
    for driver in db.query(Driver).filter(Driver.organization_id == user.organization_id, Driver.active.is_(True)).all():
        assignments = db.query(VehicleAssignment).filter(VehicleAssignment.driver_id == driver.id, VehicleAssignment.organization_id == user.organization_id).all()
        vehicle_ids = [item.vehicle_id for item in assignments]
        trips = db.query(AutoTrip).filter(AutoTrip.organization_id == user.organization_id, AutoTrip.vehicle_id.in_(vehicle_ids)).all() if vehicle_ids else []
        events = db.query(Alert).filter(Alert.organization_id == user.organization_id, Alert.vehicle_id.in_(vehicle_ids)).all() if vehicle_ids else []
        harsh = sum(trip.harsh_events for trip in trips)
        overspeed = sum(1 for event in events if event.kind == "overspeed")
        average = round(sum(trip.driver_score for trip in trips) / len(trips), 1) if trips else 100.0
        risk = "high" if average < 70 or harsh >= 10 or overspeed >= 5 else "medium" if average < 85 or harsh >= 4 or overspeed >= 2 else "low"
        result.append(DriverSafetyOut(driver_id=driver.id, trips=len(trips), harsh_events=harsh, overspeed_events=overspeed, average_score=average, risk_level=risk))
    return result


@app.get("/api/v1/drivers/{driver_id}/coaching", response_model=list[DriverCoachingOut])
def list_driver_coaching(driver_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(DriverCoaching).filter(DriverCoaching.driver_id == driver_id, DriverCoaching.organization_id == user.organization_id).order_by(DriverCoaching.created_at.desc()).all()


@app.post("/api/v1/drivers/{driver_id}/coaching", response_model=DriverCoachingOut, status_code=201)
def create_driver_coaching(driver_id: int, body: DriverCoachingIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.id == driver_id, Driver.organization_id == user.organization_id).first()
    if not driver: raise HTTPException(404, "Driver not found")
    item = DriverCoaching(organization_id=user.organization_id, driver_id=driver_id, **body.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item


@app.post("/api/v1/drivers/{driver_id}/coaching/{coaching_id}/acknowledge", response_model=DriverCoachingOut)
def acknowledge_driver_coaching(driver_id: int, coaching_id: int, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    item = db.query(DriverCoaching).filter(DriverCoaching.id == coaching_id, DriverCoaching.driver_id == driver_id, DriverCoaching.organization_id == user.organization_id).first()
    if not item: raise HTTPException(404, "Coaching record not found")
    item.status = "acknowledged"; item.acknowledged_at = datetime.now(timezone.utc); db.commit(); db.refresh(item); return item


@app.post("/api/v1/trips", response_model=TripOut)
def create_trip(body: TripIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.vehicle_id and not db.query(Vehicle).filter(Vehicle.id == body.vehicle_id, Vehicle.organization_id == user.organization_id).first(): raise HTTPException(404, "Vehicle not found")
    if body.driver_id and not db.query(Driver).filter(Driver.id == body.driver_id, Driver.organization_id == user.organization_id).first(): raise HTTPException(404, "Driver not found")
    trip = Trip(organization_id=user.organization_id, **body.model_dump()); db.add(trip); db.commit(); db.refresh(trip); return trip


@app.get("/api/v1/trips", response_model=list[TripOut])
def list_trips(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Trip).filter(Trip.organization_id == user.organization_id).order_by(Trip.id.desc()).limit(500).all()


@app.get("/api/v1/customers", response_model=list[CustomerOut])
def list_customers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Customer).filter(Customer.organization_id == user.organization_id, Customer.active.is_(True)).order_by(Customer.name).all()


@app.post("/api/v1/customers", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    customer = Customer(organization_id=user.organization_id, **body.model_dump())
    db.add(customer); db.commit(); db.refresh(customer)
    return customer


@app.get("/api/v1/delivery-orders", response_model=list[DeliveryOrderOut])
def list_delivery_orders(status: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(DeliveryOrder).filter(DeliveryOrder.organization_id == user.organization_id)
    if status:
        query = query.filter(DeliveryOrder.status == status)
    return query.order_by(DeliveryOrder.created_at.desc()).limit(500).all()


@app.post("/api/v1/delivery-orders", response_model=DeliveryOrderOut, status_code=201)
def create_delivery_order(body: DeliveryOrderIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    if db.query(DeliveryOrder).filter(DeliveryOrder.organization_id == user.organization_id, DeliveryOrder.reference == body.reference).first():
        raise HTTPException(409, "Order reference already exists")
    if body.customer_id is not None and not db.query(Customer).filter(Customer.id == body.customer_id, Customer.organization_id == user.organization_id, Customer.active.is_(True)).first():
        raise HTTPException(404, "Customer not found")
    order = DeliveryOrder(organization_id=user.organization_id, dispatcher_id=user.id, **body.model_dump())
    db.add(order); db.commit(); db.refresh(order)
    return order


@app.post("/api/v1/delivery-orders/{order_id}/assign", response_model=DeliveryOrderOut)
def assign_delivery_order(order_id: int, body: DeliveryOrderAssign, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    order = db.query(DeliveryOrder).filter(DeliveryOrder.id == order_id, DeliveryOrder.organization_id == user.organization_id).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == body.vehicle_id, Vehicle.organization_id == user.organization_id, Vehicle.active.is_(True)).first()
    driver = db.query(Driver).filter(Driver.id == body.driver_id, Driver.organization_id == user.organization_id, Driver.active.is_(True)).first()
    if not order or not vehicle or not driver:
        raise HTTPException(404, "Order, active vehicle, or active driver not found")
    if not driver_is_assignable(body.driver_id, user.organization_id, db):
        raise HTTPException(409, "Driver is unavailable or has an expired certification")
    order.vehicle_id = vehicle.id; order.driver_id = driver.id; order.dispatcher_id = user.id; order.status = "assigned"
    db.commit(); db.refresh(order)
    return order


@app.get("/api/v1/delivery-orders/{order_id}/stops", response_model=list[DeliveryStopOut])
def list_delivery_stops(order_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    order = db.query(DeliveryOrder).filter(DeliveryOrder.id == order_id, DeliveryOrder.organization_id == user.organization_id).first()
    if not order:
        raise HTTPException(404, "Delivery order not found")
    return db.query(DeliveryStop).filter(DeliveryStop.order_id == order.id).order_by(DeliveryStop.sequence).all()


@app.get("/api/v1/delivery-orders/{order_id}/route-summary", response_model=DeliveryRouteSummaryOut)
def delivery_route_summary(order_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    order = db.query(DeliveryOrder).filter(DeliveryOrder.id == order_id, DeliveryOrder.organization_id == user.organization_id).first()
    if not order: raise HTTPException(404, "Delivery order not found")
    stops = db.query(DeliveryStop).filter(DeliveryStop.order_id == order.id).order_by(DeliveryStop.sequence).all(); mapped = [item for item in stops if item.latitude is not None and item.longitude is not None]
    speed = 40.0
    if order.vehicle_id:
        position = db.query(Position).filter(Position.vehicle_id == order.vehicle_id).order_by(Position.recorded_at.desc()).first()
        if position and position.speed_kph > 5: speed = position.speed_kph
    metrics = route_metrics([(item.latitude, item.longitude) for item in mapped], speed)
    return DeliveryRouteSummaryOut(order_id=order.id, stops=len(stops), mapped_stops=len(mapped), average_speed_kph=speed, **{key: round(value, 1) if isinstance(value, float) else value for key, value in metrics.items()})


@app.post("/api/v1/delivery-orders/{order_id}/optimize-route", response_model=DeliveryRouteOptimizeOut)
def optimize_delivery_route(order_id: int, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    order = db.query(DeliveryOrder).filter(DeliveryOrder.id == order_id, DeliveryOrder.organization_id == user.organization_id).first()
    if not order:
        raise HTTPException(404, "Delivery order not found")
    stops = db.query(DeliveryStop).filter(DeliveryStop.order_id == order.id, DeliveryStop.status != "completed", DeliveryStop.latitude.is_not(None), DeliveryStop.longitude.is_not(None)).order_by(DeliveryStop.sequence).all()
    if len(stops) < 2:
        raise HTTPException(409, "At least two mapped pending stops are required")
    order_indexes = optimize_points([(stop.latitude, stop.longitude) for stop in stops])
    ordered = [stops[index] for index in order_indexes]
    for sequence, stop in enumerate(ordered, 1):
        stop.sequence = sequence
    speed = 40.0
    if order.vehicle_id:
        position = db.query(Position).filter(Position.vehicle_id == order.vehicle_id).order_by(Position.recorded_at.desc()).first()
        if position and position.speed_kph > 5:
            speed = position.speed_kph
    metrics = route_metrics([(stop.latitude, stop.longitude) for stop in ordered], speed)
    db.commit()
    return DeliveryRouteOptimizeOut(order_id=order.id, stop_ids=[stop.id for stop in ordered], **metrics)


@app.post("/api/v1/delivery-orders/{order_id}/check-deviation", response_model=DeliveryDeviationOut)
def check_delivery_deviation(order_id: int, threshold_m: float = Query(5000, gt=100, le=100000), user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    order = db.query(DeliveryOrder).filter(DeliveryOrder.id == order_id, DeliveryOrder.organization_id == user.organization_id).first()
    if not order: raise HTTPException(404, "Delivery order not found")
    stop = db.query(DeliveryStop).filter(DeliveryStop.order_id == order.id, DeliveryStop.status != "completed", DeliveryStop.latitude.is_not(None), DeliveryStop.longitude.is_not(None)).order_by(DeliveryStop.sequence).first()
    if not order.vehicle_id or not stop:
        return DeliveryDeviationOut(order_id=order.id, stop_id=stop.id if stop else None, distance_to_next_stop_m=None, threshold_m=threshold_m, deviated=False, message="No assigned vehicle or mapped pending stop to evaluate.")
    position = db.query(Position).filter(Position.vehicle_id == order.vehicle_id, Position.organization_id == user.organization_id).order_by(Position.recorded_at.desc()).first()
    if not position:
        return DeliveryDeviationOut(order_id=order.id, stop_id=stop.id, distance_to_next_stop_m=None, threshold_m=threshold_m, deviated=False, message="No live position available.")
    from .gateway import _distance_m
    distance = _distance_m(position.latitude, position.longitude, stop.latitude, stop.longitude); deviated = distance > threshold_m
    if deviated:
        exists = db.query(DeliveryException).filter(DeliveryException.order_id == order.id, DeliveryException.stop_id == stop.id, DeliveryException.kind == "route_deviation", DeliveryException.status == "open").first()
        if not exists:
            db.add(DeliveryException(organization_id=user.organization_id, order_id=order.id, stop_id=stop.id, kind="route_deviation", message=f"Vehicle is {distance / 1000:.1f} km from pending stop #{stop.sequence}.")); db.commit()
    return DeliveryDeviationOut(order_id=order.id, stop_id=stop.id, distance_to_next_stop_m=round(distance, 1), threshold_m=threshold_m, deviated=deviated, message="Route deviation detected." if deviated else "Vehicle is within the route threshold.")


def create_late_stop_exception(stop: DeliveryStop, db: Session) -> None:
    if not stop.window_end or not stop.completed_at or stop.completed_at <= stop.window_end:
        return
    exists = db.query(DeliveryException).filter(DeliveryException.stop_id == stop.id, DeliveryException.kind == "late_stop").first()
    if not exists:
        db.add(DeliveryException(organization_id=stop.organization_id, order_id=stop.order_id, stop_id=stop.id, kind="late_stop", message=f"Stop #{stop.sequence} was completed after its delivery window."))
        db.flush()


@app.get("/api/v1/delivery-exceptions", response_model=list[DeliveryExceptionOut])
def list_delivery_exceptions(status: str | None = "open", user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(DeliveryException).filter(DeliveryException.organization_id == user.organization_id)
    if status:
        query = query.filter(DeliveryException.status == status)
    return query.order_by(DeliveryException.created_at.desc()).limit(500).all()


@app.post("/api/v1/delivery-exceptions/{exception_id}/resolve", response_model=DeliveryExceptionOut)
def resolve_delivery_exception(exception_id: int, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    item = db.query(DeliveryException).filter(DeliveryException.id == exception_id, DeliveryException.organization_id == user.organization_id).first()
    if not item:
        raise HTTPException(404, "Delivery exception not found")
    if item.status != "resolved":
        item.status = "resolved"; item.resolved_at = datetime.now(timezone.utc); db.commit(); db.refresh(item)
    return item


@app.post("/api/v1/delivery-orders/{order_id}/stops", response_model=DeliveryStopOut, status_code=201)
def create_delivery_stop(order_id: int, body: DeliveryStopIn, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    order = db.query(DeliveryOrder).filter(DeliveryOrder.id == order_id, DeliveryOrder.organization_id == user.organization_id).first()
    if not order or order.status == "completed":
        raise HTTPException(404 if not order else 409, "Delivery order not found or already completed")
    sequence = (db.query(func.max(DeliveryStop.sequence)).filter(DeliveryStop.order_id == order.id).scalar() or 0) + 1
    stop = DeliveryStop(organization_id=user.organization_id, order_id=order.id, sequence=sequence, **body.model_dump())
    db.add(stop); db.commit(); db.refresh(stop)
    return stop


@app.post("/api/v1/delivery-stops/{stop_id}/complete", response_model=DeliveryStopOut)
def complete_delivery_stop(stop_id: int, body: DeliveryStopComplete, user: User = Depends(require_roles("admin", "manager", "operator")), db: Session = Depends(get_db)):
    stop = db.query(DeliveryStop).filter(DeliveryStop.id == stop_id, DeliveryStop.organization_id == user.organization_id).first()
    if not stop:
        raise HTTPException(404, "Delivery stop not found")
    stop.status = "completed"; stop.proof_note = body.proof_note; stop.completed_at = datetime.now(timezone.utc)
    create_late_stop_exception(stop, db)
    order = db.query(DeliveryOrder).filter(DeliveryOrder.id == stop.order_id, DeliveryOrder.organization_id == user.organization_id).first()
    if order:
        remaining = db.query(DeliveryStop).filter(DeliveryStop.order_id == order.id, DeliveryStop.status != "completed").count()
        order.status = "completed" if remaining == 0 else "in_progress"
    db.commit(); db.refresh(stop)
    return stop


@app.post("/api/v1/geofences", response_model=GeofenceOut)
def create_geofence(body: GeofenceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    fence = Geofence(organization_id=user.organization_id, **body.model_dump()); db.add(fence); db.commit(); db.refresh(fence); return fence


@app.get("/api/v1/geofences", response_model=list[GeofenceOut])
def list_geofences(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Geofence).filter(Geofence.organization_id == user.organization_id, Geofence.active.is_(True)).all()


@app.delete("/api/v1/geofences/{geofence_id}", status_code=204)
def delete_geofence(geofence_id: int, user: User = Depends(require_roles("admin", "manager")), db: Session = Depends(get_db)):
    fence = db.query(Geofence).filter(Geofence.id == geofence_id, Geofence.organization_id == user.organization_id).first()
    if not fence: raise HTTPException(404, "Geofence not found")
    fence.active = False; db.commit()


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
    alert_queue: asyncio.Queue | None = None
    telemetry_queue: asyncio.Queue | None = None
    try:
        import jwt
        from .config import settings
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        org_id = int(claims["org"])
        alert_queue = _subscribe_alerts(org_id)
        telemetry_queue = subscribe_telemetry(org_id)

        async def push_alerts():
            while True:
                alert = await alert_queue.get()
                await websocket.send_json({"type": "alert", "data": alert})

        alert_task = asyncio.create_task(push_alerts())
        async def push_telemetry():
            while True:
                event = await telemetry_queue.get()
                await websocket.send_json({"type": "telemetry_event", "data": event})
        telemetry_task = asyncio.create_task(push_telemetry())
        try:
            while True:
                db = next(get_db())
                try:
                    rows = db.query(Position).filter(Position.organization_id == org_id).order_by(Position.recorded_at.desc()).limit(100).all()
                    latest: dict = {}
                    for row in rows: latest.setdefault(row.vehicle_id, row)
                    # Include last 20 trail points per vehicle
                    trails: dict = {}
                    for vid in latest:
                        trail = db.query(Position).filter(Position.vehicle_id == vid).order_by(Position.recorded_at.desc()).limit(20).all()
                        trails[vid] = [PositionOut.model_validate(t).model_dump(mode="json") for t in reversed(trail)]
                    await websocket.send_json({
                        "type": "positions",
                        "data": [PositionOut.model_validate(row).model_dump(mode="json") for row in latest.values()],
                        "trails": trails,
                    })
                finally:
                    db.close()
                await asyncio.sleep(3)
        finally:
            alert_task.cancel()
            telemetry_task.cancel()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if alert_queue is not None:
            try:
                _unsubscribe_alerts(int(claims["org"]), alert_queue)  # type: ignore[name-defined]
            except Exception:
                pass
        if telemetry_queue is not None:
            try: unsubscribe_telemetry(int(claims["org"]), telemetry_queue)  # type: ignore[name-defined]
            except Exception: pass
        try:
            await websocket.close()
        except RuntimeError:
            pass
