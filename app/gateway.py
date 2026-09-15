import asyncio
from math import asin, cos, radians, sin, sqrt
from sqlalchemy.exc import IntegrityError
from .config import settings
from .db import SessionLocal
from .models import Alert, AutoTrip, Geofence, Position, RawPacket, Vehicle, VehicleOdometer, now
from .protocols import decode_gt06, decode_teltonika, decode_codec12_response, NormalizedPosition

# imei -> asyncio.StreamWriter for connected Teltonika devices
_teltonika_clients: dict[str, asyncio.StreamWriter] = {}
# imei -> Future waiting for a command response
_teltonika_pending: dict[str, asyncio.Future] = {}
# imei -> last ignition state for trip detection
_ignition_state: dict[str, bool] = {}


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
        for p in decoded:
            exists = db.query(Position).filter(Position.device_imei == imei, Position.event_id == p.event_id).first()
            if exists: continue
            pos_row = Position(
                organization_id=vehicle.organization_id, vehicle_id=vehicle.id,
                device_imei=imei, event_id=p.event_id, recorded_at=p.recorded_at,
                latitude=p.latitude, longitude=p.longitude, altitude=p.altitude,
                speed_kph=p.speed_kph, heading=p.heading, ignition=p.ignition,
                satellites=p.satellites, raw_packet_id=raw.id,
                harsh_braking=p.harsh_braking, harsh_acceleration=p.harsh_acceleration,
                harsh_cornering=p.harsh_cornering, towing=p.towing, jamming=p.jamming,
                sos=p.sos, ext_voltage_mv=p.ext_voltage_mv, battery_mv=p.battery_mv,
                odometer_m=p.odometer_m,
            )
            db.add(pos_row); db.flush()

            # --- Alerts ---
            if p.speed_kph > 120:
                db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="overspeed", message=f"{p.speed_kph:.0f} km/h at {p.latitude:.5f},{p.longitude:.5f}"))
            if p.harsh_braking:
                db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="harsh_braking", message=f"Harsh braking at {p.latitude:.5f},{p.longitude:.5f}"))
            if p.harsh_acceleration:
                db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="harsh_acceleration", message=f"Harsh acceleration at {p.latitude:.5f},{p.longitude:.5f}"))
            if p.harsh_cornering:
                db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="harsh_cornering", message=f"Harsh cornering at {p.latitude:.5f},{p.longitude:.5f}"))
            if p.towing:
                db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="towing", message=f"Towing detected at {p.latitude:.5f},{p.longitude:.5f}"))
            if p.jamming:
                db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="jamming", message=f"GPS jamming detected at {p.latitude:.5f},{p.longitude:.5f}"))
            if p.sos:
                db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="sos", message=f"SOS triggered at {p.latitude:.5f},{p.longitude:.5f}"))
            if p.ext_voltage_mv > 0 and p.ext_voltage_mv < 9000:
                db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="low_external_power", message=f"External voltage low: {p.ext_voltage_mv}mV"))

            # --- Geofence entry/exit ---
            for fence in db.query(Geofence).filter(Geofence.organization_id == vehicle.organization_id, Geofence.active.is_(True)).all():
                inside = _distance_m(p.latitude, p.longitude, fence.latitude, fence.longitude) <= fence.radius_m
                if inside:
                    db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="geofence_enter", message=f"{vehicle.name} entered {fence.name}"))
                else:
                    db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="geofence_exit", message=f"{vehicle.name} exited {fence.name}"))

            # --- Auto trip detection ---
            prev_ignition = _ignition_state.get(imei)
            if prev_ignition is not None:
                if not prev_ignition and p.ignition:
                    # Ignition turned ON — start new trip
                    db.add(AutoTrip(
                        organization_id=vehicle.organization_id, vehicle_id=vehicle.id,
                        started_at=p.recorded_at, start_lat=p.latitude, start_lon=p.longitude,
                    ))
                elif prev_ignition and not p.ignition:
                    # Ignition turned OFF — close open trip
                    open_trip = db.query(AutoTrip).filter(
                        AutoTrip.vehicle_id == vehicle.id, AutoTrip.ended_at.is_(None)
                    ).order_by(AutoTrip.id.desc()).first()
                    if open_trip:
                        open_trip.ended_at = p.recorded_at
                        open_trip.end_lat = p.latitude
                        open_trip.end_lon = p.longitude
                        # Compute distance and score from positions in this trip window
                        trip_positions = db.query(Position).filter(
                            Position.vehicle_id == vehicle.id,
                            Position.recorded_at >= open_trip.started_at,
                            Position.recorded_at <= p.recorded_at,
                        ).order_by(Position.recorded_at.asc()).all()
                        dist = 0.0
                        max_spd = 0.0
                        harsh = 0
                        for i in range(1, len(trip_positions)):
                            dist += _distance_m(trip_positions[i-1].latitude, trip_positions[i-1].longitude, trip_positions[i].latitude, trip_positions[i].longitude)
                            max_spd = max(max_spd, trip_positions[i].speed_kph)
                            if trip_positions[i].harsh_braking: harsh += 1
                            if trip_positions[i].harsh_acceleration: harsh += 1
                            if trip_positions[i].harsh_cornering: harsh += 1
                        open_trip.distance_m = dist
                        open_trip.max_speed_kph = max_spd
                        open_trip.harsh_events = harsh
                        open_trip.driver_score = max(0.0, 100.0 - harsh * 5 - (max(0, max_spd - 120) * 0.5))
            _ignition_state[imei] = p.ignition

            # --- Odometer accumulation ---
            odo = db.query(VehicleOdometer).filter(VehicleOdometer.vehicle_id == vehicle.id).first()
            if not odo:
                odo = VehicleOdometer(vehicle_id=vehicle.id, organization_id=vehicle.organization_id)
                db.add(odo)
                db.flush()
            if odo.last_position_id:
                last_pos = db.get(Position, odo.last_position_id)
                if last_pos:
                    seg = _distance_m(last_pos.latitude, last_pos.longitude, p.latitude, p.longitude)
                    if seg < 50_000:  # ignore teleports > 50km
                        odo.total_distance_m += seg
            if p.ignition:
                # Approximate engine hours: assume ~30s between packets
                odo.engine_hours_s += 30
            odo.last_position_id = pos_row.id

            count += 1
        vehicle.last_seen_at = now()
        db.commit()
        return count
    except IntegrityError:
        db.rollback(); return 0
    finally: db.close()


def _gt06_ack(protocol: int, serial: bytes) -> bytes:
    """Build a GT06 server response: 78 78 | 05 | protocol | serial(2) | crc(2) | 0D 0A."""
    body = bytes([0x05, protocol]) + serial
    crc = _crc16_gt06(body)
    return b"\x78\x78" + body + crc.to_bytes(2, "big") + b"\x0d\x0a"


def _crc16_gt06(data: bytes) -> int:
    """CRC-16/X25 (CRC-ITU) used by the GT06/CONCOX wire protocol."""
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


def encode_codec12(command: str) -> bytes:
    """Encode a Codec 12 command packet to send to a Teltonika device."""
    cmd = command.encode()
    cmd_len = len(cmd).to_bytes(4, "big")
    data = b"\x0C\x01\x05" + cmd_len + cmd + b"\x01"
    data_len = len(data).to_bytes(4, "big")
    from .protocols import _crc16_ibm
    crc = _crc16_ibm(data).to_bytes(4, "big")
    return b"\x00\x00\x00\x00" + data_len + data + crc


async def send_device_command(imei: str, command: str, timeout: float = 10.0) -> str | None:
    """Send a Codec 12 command to a connected Teltonika device. Returns response text or None."""
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
            # Teltonika login frames start with a two-byte big-endian IMEI
            # length, followed by the ASCII IMEI itself (normally 15 digits).
            # Do not include the length prefix in the device identifier.
            imei_length = int.from_bytes(await reader.readexactly(2), "big")
            if not 8 <= imei_length <= 32:
                raise ValueError("invalid Teltonika IMEI length")
            imei = (await reader.readexactly(imei_length)).decode("ascii")
            writer.write(b"\x01"); await writer.drain()
            _teltonika_clients[imei] = writer
        else:
            # GT06 login: 78 78 | length(1) | 0x01 | 8-byte BCD IMEI | 2-byte serial | 2-byte CRC | 0D 0A
            login = await read_frame(reader, "gt06")
            if login[3] != 0x01:
                raise ValueError("expected GT06 login frame")
            imei = ''.join(f'{b:02x}' for b in login[4:12])[-15:]
            serial = login[-6:-4]
            ack = _gt06_ack(0x01, serial)
            writer.write(ack); await writer.drain()
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
                count = ingest(protocol, imei, packet, decode_teltonika(packet, imei))
                writer.write(b"\x00\x00\x00\x01" + count.to_bytes(4, "big"))
            else:
                frame_start = 3 if packet[:2] == b"\x78\x78" else 4
                frame_protocol = packet[frame_start]
                # V5 trackers send heartbeats (0x13) between location reports.
                # Acknowledge every valid frame and keep a heartbeat as evidence
                # that the authenticated device is online.
                decoded = decode_gt06(packet, imei) if frame_protocol in (0x10, 0x11, 0x12, 0x22) else ()
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
