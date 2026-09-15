import asyncio
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from sqlalchemy.exc import IntegrityError
from .config import settings
from .db import SessionLocal
from .models import Alert, AutoTrip, Geofence, MaintenanceReminder, Position, RawPacket, SafetyIncident, TelemetryEvent, Vehicle, VehicleOdometer, now
from .protocols import decode_codec12_response, decode_packet, NormalizedPosition
from .live_state import set_vehicle_state

# imei -> asyncio.StreamWriter for connected Teltonika devices
_teltonika_clients: dict[str, asyncio.StreamWriter] = {}
# imei -> Future waiting for a command response
_teltonika_pending: dict[str, asyncio.Future] = {}
# imei -> last ignition state for trip detection and ignition alerts
_ignition_state: dict[str, bool] = {}
# imei -> set of fence ids currently inside (geofence state machine)
_geofence_inside: dict[str, set[int]] = {}
# imei -> (last_idle_start_ts, idle_alerted) for idle detection
_idle_state: dict[str, tuple[datetime | None, bool]] = {}
# org_id -> set of WebSocket connections for real-time alert push
_alert_subscribers: dict[int, set[asyncio.Queue]] = {}
_telemetry_subscribers: dict[int, set[asyncio.Queue]] = {}


def _subscribe_alerts(org_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _alert_subscribers.setdefault(org_id, set()).add(q)
    return q


def _unsubscribe_alerts(org_id: int, q: asyncio.Queue) -> None:
    _alert_subscribers.get(org_id, set()).discard(q)


def _push_alert(org_id: int, alert_dict: dict) -> None:
    for q in list(_alert_subscribers.get(org_id, set())):
        try:
            q.put_nowait(alert_dict)
        except asyncio.QueueFull:
            pass


def subscribe_telemetry(org_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _telemetry_subscribers.setdefault(org_id, set()).add(q)
    return q


def unsubscribe_telemetry(org_id: int, q: asyncio.Queue) -> None:
    _telemetry_subscribers.get(org_id, set()).discard(q)


def _push_telemetry(org_id: int, event: dict) -> None:
    for q in list(_telemetry_subscribers.get(org_id, set())):
        try: q.put_nowait(event)
        except asyncio.QueueFull: pass


def _add_alert(db, org_id: int, vehicle_id: int, kind: str, message: str) -> None:
    a = Alert(organization_id=org_id, vehicle_id=vehicle_id, kind=kind, message=message)
    db.add(a)
    if kind in {"crash", "sos", "towing", "jamming"}:
        recent = db.query(SafetyIncident).filter(SafetyIncident.organization_id == org_id, SafetyIncident.vehicle_id == vehicle_id, SafetyIncident.status.in_(("open", "investigating")), SafetyIncident.title == f"Telemetry {kind}").first()
        if not recent:
            severity = "critical" if kind in {"crash", "sos"} else "high"
            db.add(SafetyIncident(organization_id=org_id, vehicle_id=vehicle_id, title=f"Telemetry {kind}", severity=severity, description=message))
            db.flush()
    _push_alert(org_id, {"kind": kind, "vehicle_id": vehicle_id, "message": message, "created_at": now().isoformat()})


def normalized_event_type(position: NormalizedPosition) -> str:
    if position.crash: return "safety.crash"
    if position.sos: return "safety.sos"
    if position.towing or position.jamming: return "security.tamper"
    if position.ignition: return "position.ignition_on"
    return "position"


def _is_outside_schedule(schedule: str) -> bool:
    """Return True if current UTC time is outside the allowed window HH:MM-HH:MM."""
    try:
        start_s, end_s = schedule.split("-")
        sh, sm = int(start_s[:2]), int(start_s[3:])
        eh, em = int(end_s[:2]), int(end_s[3:])
        now_t = datetime.now(timezone.utc)
        cur = now_t.hour * 60 + now_t.minute
        start = sh * 60 + sm
        end = eh * 60 + em
        if start <= end:
            return not (start <= cur < end)
        else:  # overnight window e.g. 22:00-06:00
            return not (cur >= start or cur < end)
    except Exception:
        return False


async def read_frame(reader: asyncio.StreamReader, protocol: str) -> bytes:
    if protocol == "teltonika":
        header = await reader.readexactly(8)
        length = int.from_bytes(header[4:8], "big")
        if length > settings.max_packet_bytes: raise ValueError("packet too large")
        return header + await reader.readexactly(length + 4)
    header = await reader.readexactly(3)
    length_bytes = 1 if header[:2] == b"\x78\x78" else 2
    if length_bytes == 2:
        header += await reader.readexactly(1)
    length = header[2] if length_bytes == 1 else int.from_bytes(header[2:4], "big")
    if length > settings.max_packet_bytes: raise ValueError("packet too large")
    return header + await reader.readexactly(length + 2 if length_bytes == 1 else length)


def ingest(protocol: str, imei: str, packet: bytes, decoded: tuple[NormalizedPosition, ...]) -> int:
    db = SessionLocal()
    try:
        vehicle = db.query(Vehicle).filter(Vehicle.imei == imei, Vehicle.active.is_(True)).first()
        if not vehicle: return 0
        raw = RawPacket(imei=imei, protocol=protocol, payload_hex=packet.hex())
        db.add(raw); db.flush()
        count = 0
        org_id = vehicle.organization_id
        vid = vehicle.id

        for p in decoded:
            if db.query(Position).filter(Position.device_imei == imei, Position.event_id == p.event_id).first():
                continue

            telemetry_row = TelemetryEvent(
                organization_id=org_id, vehicle_id=vid, device_imei=imei,
                source_protocol=protocol, event_key=p.event_id,
                event_type=normalized_event_type(p), recorded_at=p.recorded_at,
                latitude=p.latitude, longitude=p.longitude,
                payload={"speed_kph": p.speed_kph, "heading": p.heading, "ignition": p.ignition, "satellites": p.satellites, "fuel_level": p.fuel_level, "odometer_m": p.odometer_m, "harsh_braking": p.harsh_braking, "harsh_acceleration": p.harsh_acceleration, "harsh_cornering": p.harsh_cornering, "door_open": p.door_open, "battery_mv": p.battery_mv, "ext_voltage_mv": p.ext_voltage_mv},
            )
            db.add(telemetry_row)
            _push_telemetry(org_id, {"vehicle_id": vid, "device_imei": imei, "source_protocol": protocol, "event_key": p.event_id, "event_type": normalized_event_type(p), "recorded_at": p.recorded_at.isoformat(), "latitude": p.latitude, "longitude": p.longitude, "payload": {"speed_kph": p.speed_kph, "ignition": p.ignition}})

            pos_row = Position(
                organization_id=org_id, vehicle_id=vid,
                device_imei=imei, event_id=p.event_id, recorded_at=p.recorded_at,
                latitude=p.latitude, longitude=p.longitude, altitude=p.altitude,
                speed_kph=p.speed_kph, heading=p.heading, ignition=p.ignition,
                satellites=p.satellites, raw_packet_id=raw.id,
                harsh_braking=p.harsh_braking, harsh_acceleration=p.harsh_acceleration,
                harsh_cornering=p.harsh_cornering, towing=p.towing, jamming=p.jamming,
                sos=p.sos, crash=p.crash, door_open=p.door_open,
                ext_voltage_mv=p.ext_voltage_mv, battery_mv=p.battery_mv,
                fuel_level=p.fuel_level, odometer_m=p.odometer_m,
            )
            db.add(pos_row); db.flush()
            set_vehicle_state(org_id, vid, {"vehicle_id": vid, "device_imei": imei, "protocol": protocol, "recorded_at": p.recorded_at.isoformat(), "latitude": p.latitude, "longitude": p.longitude, "speed_kph": p.speed_kph, "heading": p.heading, "ignition": p.ignition, "satellites": p.satellites, "fuel_level": p.fuel_level, "battery_mv": p.battery_mv, "event_type": normalized_event_type(p)})

            # --- Configurable overspeed ---
            if p.speed_kph > vehicle.overspeed_kph:
                _add_alert(db, org_id, vid, "overspeed", f"{p.speed_kph:.0f} km/h (limit {vehicle.overspeed_kph}) at {p.latitude:.5f},{p.longitude:.5f}")

            # --- Harsh driving ---
            if p.harsh_braking:
                _add_alert(db, org_id, vid, "harsh_braking", f"Harsh braking at {p.latitude:.5f},{p.longitude:.5f}")
            if p.harsh_acceleration:
                _add_alert(db, org_id, vid, "harsh_acceleration", f"Harsh acceleration at {p.latitude:.5f},{p.longitude:.5f}")
            if p.harsh_cornering:
                _add_alert(db, org_id, vid, "harsh_cornering", f"Harsh cornering at {p.latitude:.5f},{p.longitude:.5f}")

            # --- Towing, jamming, SOS, crash, door ---
            if p.towing:
                _add_alert(db, org_id, vid, "towing", f"Towing detected at {p.latitude:.5f},{p.longitude:.5f}")
            if p.jamming:
                _add_alert(db, org_id, vid, "jamming", f"GPS jamming detected at {p.latitude:.5f},{p.longitude:.5f}")
            if p.sos:
                _add_alert(db, org_id, vid, "sos", f"SOS triggered at {p.latitude:.5f},{p.longitude:.5f}")
            if p.crash:
                _add_alert(db, org_id, vid, "crash", f"Crash detected at {p.latitude:.5f},{p.longitude:.5f} speed={p.speed_kph:.0f}km/h")
            if p.door_open:
                _add_alert(db, org_id, vid, "door_open", f"Door opened at {p.latitude:.5f},{p.longitude:.5f}")

            # --- Low external power / battery ---
            if 0 < p.ext_voltage_mv < 9000:
                _add_alert(db, org_id, vid, "low_external_power", f"External voltage low: {p.ext_voltage_mv}mV")
            if 0 < p.battery_mv < 3400:
                _add_alert(db, org_id, vid, "low_battery", f"Battery low: {p.battery_mv}mV")

            # --- Ignition on/off alerts + trip detection ---
            prev_ignition = _ignition_state.get(imei)
            if prev_ignition is not None and prev_ignition != p.ignition:
                if p.ignition:
                    _add_alert(db, org_id, vid, "ignition_on", f"Ignition ON at {p.latitude:.5f},{p.longitude:.5f}")
                    db.add(AutoTrip(
                        organization_id=org_id, vehicle_id=vid,
                        started_at=p.recorded_at, start_lat=p.latitude, start_lon=p.longitude,
                    ))
                else:
                    _add_alert(db, org_id, vid, "ignition_off", f"Ignition OFF at {p.latitude:.5f},{p.longitude:.5f}")
                    open_trip = db.query(AutoTrip).filter(
                        AutoTrip.vehicle_id == vid, AutoTrip.ended_at.is_(None)
                    ).order_by(AutoTrip.id.desc()).first()
                    if open_trip:
                        open_trip.ended_at = p.recorded_at
                        open_trip.end_lat = p.latitude
                        open_trip.end_lon = p.longitude
                        trip_positions = db.query(Position).filter(
                            Position.vehicle_id == vid,
                            Position.recorded_at >= open_trip.started_at,
                            Position.recorded_at <= p.recorded_at,
                        ).order_by(Position.recorded_at.asc()).all()
                        dist = max_spd = harsh = idle_s = 0
                        for i in range(1, len(trip_positions)):
                            prev_p = trip_positions[i - 1]
                            cur_p = trip_positions[i]
                            seg = _distance_m(prev_p.latitude, prev_p.longitude, cur_p.latitude, cur_p.longitude)
                            if seg < 50_000: dist += seg
                            max_spd = max(max_spd, cur_p.speed_kph)
                            if cur_p.harsh_braking: harsh += 1
                            if cur_p.harsh_acceleration: harsh += 1
                            if cur_p.harsh_cornering: harsh += 1
                            # Idle: ignition on, speed=0
                            dt = (cur_p.recorded_at - prev_p.recorded_at).total_seconds()
                            if cur_p.ignition and cur_p.speed_kph == 0:
                                idle_s += int(dt)
                        open_trip.distance_m = dist
                        open_trip.max_speed_kph = max_spd
                        open_trip.harsh_events = harsh
                        open_trip.idle_seconds = idle_s
                        # Score: -5 per harsh event, -0.5 per km/h over limit, -1 per idle minute
                        open_trip.driver_score = max(0.0, 100.0
                            - harsh * 5
                            - max(0, max_spd - vehicle.overspeed_kph) * 0.5
                            - (idle_s / 60) * 1.0)
            _ignition_state[imei] = p.ignition

            # --- Idle detection (state machine) ---
            idle_start, idle_alerted = _idle_state.get(imei, (None, False))
            if p.ignition and p.speed_kph == 0:
                if idle_start is None:
                    _idle_state[imei] = (p.recorded_at, False)
                elif not idle_alerted:
                    idle_minutes = (p.recorded_at - idle_start).total_seconds() / 60
                    if idle_minutes >= vehicle.idle_alert_minutes:
                        _add_alert(db, org_id, vid, "idle", f"Idle for {idle_minutes:.0f} min at {p.latitude:.5f},{p.longitude:.5f}")
                        _idle_state[imei] = (idle_start, True)
            else:
                _idle_state[imei] = (None, False)

            # --- Geofence state machine (entry AND exit, no duplicate fires) ---
            fences = db.query(Geofence).filter(Geofence.organization_id == org_id, Geofence.active.is_(True)).all()
            prev_inside = _geofence_inside.get(imei, set())
            now_inside: set[int] = set()
            for fence in fences:
                if _inside_geofence(fence, p.latitude, p.longitude):
                    now_inside.add(fence.id)
            for fence in fences:
                was = fence.id in prev_inside
                is_now = fence.id in now_inside
                if not was and is_now:
                    _add_alert(db, org_id, vid, "geofence_enter", f"{vehicle.name} entered {fence.name}")
                    # Scheduled immobilizer: cut engine on geofence exit if schedule active
                elif was and not is_now:
                    _add_alert(db, org_id, vid, "geofence_exit", f"{vehicle.name} exited {fence.name}")
            _geofence_inside[imei] = now_inside

            # --- Scheduled immobilizer check ---
            if vehicle.immobilizer_schedule and p.ignition:
                if _is_outside_schedule(vehicle.immobilizer_schedule):
                    writer = _teltonika_clients.get(imei)
                    if writer:
                        asyncio.get_event_loop().create_task(_send_immobilize(imei, writer))
                        _add_alert(db, org_id, vid, "scheduled_immobilizer", f"Engine cut by schedule ({vehicle.immobilizer_schedule})")

            # --- Odometer + engine hours ---
            odo = db.query(VehicleOdometer).filter(VehicleOdometer.vehicle_id == vid).first()
            if not odo:
                odo = VehicleOdometer(vehicle_id=vid, organization_id=org_id)
                db.add(odo); db.flush()
            if odo.last_position_id:
                last_pos = db.get(Position, odo.last_position_id)
                if last_pos:
                    seg = _distance_m(last_pos.latitude, last_pos.longitude, p.latitude, p.longitude)
                    if seg < 50_000:
                        odo.total_distance_m += seg
            if p.ignition:
                odo.engine_hours_s += 30
            odo.last_position_id = pos_row.id

            # --- Maintenance reminders ---
            reminders = db.query(MaintenanceReminder).filter(
                MaintenanceReminder.vehicle_id == vid,
                MaintenanceReminder.triggered.is_(False),
            ).all()
            for rem in reminders:
                triggered = False
                if rem.odometer_threshold_m and odo.total_distance_m >= rem.odometer_threshold_m:
                    triggered = True
                if rem.engine_hours_threshold_s and odo.engine_hours_s >= rem.engine_hours_threshold_s:
                    triggered = True
                if triggered:
                    rem.triggered = True
                    _add_alert(db, org_id, vid, "maintenance_due", f"Maintenance due: {rem.name}")

            count += 1

        vehicle.last_seen_at = now()
        db.commit()
        return count
    except IntegrityError:
        db.rollback(); return 0
    finally:
        db.close()


async def _send_immobilize(imei: str, writer: asyncio.StreamWriter) -> None:
    try:
        writer.write(encode_codec12("setdigout 1 1"))
        await writer.drain()
    except Exception:
        pass


def _gt06_ack(protocol: int, serial: bytes) -> bytes:
    body = bytes([0x05, protocol]) + serial
    crc = _crc16_gt06(body)
    return b"\x78\x78" + body + crc.to_bytes(2, "big") + b"\x0d\x0a"


def _crc16_gt06(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth = 6_371_000
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return earth * 2 * asin(sqrt(a))


def _point_in_polygon(lat: float, lon: float, points: list[list[float]]) -> bool:
    inside = False
    j = len(points) - 1
    for i, point in enumerate(points):
        yi, xi = point[0], point[1]; yj, xj = points[j][0], points[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi): inside = not inside
        j = i
    return inside


def _point_to_segment_m(lat: float, lon: float, a: list[float], b: list[float]) -> float:
    scale = 111_000.0
    px, py = lon * scale, lat * scale; ax, ay = a[1] * scale, a[0] * scale; bx, by = b[1] * scale, b[0] * scale
    dx, dy = bx - ax, by - ay; t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1.0)));
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def _inside_geofence(fence: Geofence, lat: float, lon: float) -> bool:
    if fence.geofence_type == "polygon" and fence.geometry:
        return _point_in_polygon(lat, lon, fence.geometry.get("coordinates", []))
    if fence.geofence_type == "corridor" and fence.geometry:
        points = fence.geometry.get("coordinates", [])
        return any(_point_to_segment_m(lat, lon, points[i], points[i + 1]) <= (fence.corridor_width_m or 0) for i in range(len(points) - 1))
    return _distance_m(lat, lon, fence.latitude, fence.longitude) <= fence.radius_m


def encode_codec12(command: str) -> bytes:
    cmd = command.encode()
    cmd_len = len(cmd).to_bytes(4, "big")
    data = b"\x0C\x01\x05" + cmd_len + cmd + b"\x01"
    data_len = len(data).to_bytes(4, "big")
    from .protocols import _crc16_ibm
    crc = _crc16_ibm(data).to_bytes(4, "big")
    return b"\x00\x00\x00\x00" + data_len + data + crc


async def send_device_command(imei: str, command: str, timeout: float = 10.0) -> str | None:
    writer = _teltonika_clients.get(imei)
    if not writer:
        return None
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    _teltonika_pending[imei] = fut
    try:
        writer.write(encode_codec12(command))
        await writer.drain()
        return await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        return "timeout"
    finally:
        _teltonika_pending.pop(imei, None)


async def client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, protocol: str):
    imei = None
    try:
        if protocol == "teltonika":
            imei_length = int.from_bytes(await reader.readexactly(2), "big")
            if not 8 <= imei_length <= 32:
                raise ValueError("invalid Teltonika IMEI length")
            imei = (await reader.readexactly(imei_length)).decode("ascii")
            writer.write(b"\x01"); await writer.drain()
            _teltonika_clients[imei] = writer
        else:
            login = await read_frame(reader, "gt06")
            if login[3] != 0x01:
                raise ValueError("expected GT06 login frame")
            imei = ''.join(f'{b:02x}' for b in login[4:12])[-15:]
            serial = login[-6:-4]
            writer.write(_gt06_ack(0x01, serial)); await writer.drain()
        while True:
            packet = await asyncio.wait_for(read_frame(reader, protocol), timeout=300)
            if protocol == "teltonika":
                if len(packet) > 8 and packet[8] in (0x0C, 0x0D):
                    try:
                        response = decode_codec12_response(packet)
                        fut = _teltonika_pending.get(imei)
                        if fut and not fut.done(): fut.set_result(response)
                    except ValueError:
                        pass
                    continue
                count = ingest(protocol, imei, packet, decode_packet(protocol, packet, imei))
                writer.write(b"\x00\x00\x00\x01" + count.to_bytes(4, "big"))
            else:
                frame_start = 3 if packet[:2] == b"\x78\x78" else 4
                frame_protocol = packet[frame_start]
                decoded = decode_packet(protocol, packet, imei) if frame_protocol in (0x10, 0x11, 0x12, 0x22) else ()
                count = ingest(protocol, imei, packet, decoded)
                writer.write(_gt06_ack(frame_protocol, packet[-6:-4]))
            await writer.drain()
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ValueError, UnicodeDecodeError):
        pass
    finally:
        if imei and protocol == "teltonika": _teltonika_clients.pop(imei, None)
        writer.close(); await writer.wait_closed()


async def start_servers():
    return await asyncio.gather(
        asyncio.start_server(lambda r, w: client(r, w, "teltonika"), settings.tcp_teltonika_host, settings.tcp_teltonika_port),
        asyncio.start_server(lambda r, w: client(r, w, "gt06"), settings.tcp_gt06_host, settings.tcp_gt06_port),
    )
