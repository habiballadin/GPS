import asyncio
from math import asin, cos, radians, sin, sqrt
from sqlalchemy.exc import IntegrityError
from .config import settings
from .db import SessionLocal
from .models import Alert, Geofence, Position, RawPacket, Vehicle, now
from .protocols import decode_gt06, decode_teltonika, NormalizedPosition


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
            db.add(Position(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, device_imei=imei, event_id=p.event_id, recorded_at=p.recorded_at, latitude=p.latitude, longitude=p.longitude, altitude=p.altitude, speed_kph=p.speed_kph, heading=p.heading, ignition=p.ignition, satellites=p.satellites, raw_packet_id=raw.id))
            if p.speed_kph > 120:
                db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="overspeed", message=f"{p.speed_kph:.0f} km/h at {p.latitude:.5f},{p.longitude:.5f}"))
            for fence in db.query(Geofence).filter(Geofence.organization_id == vehicle.organization_id, Geofence.active.is_(True)).all():
                if _distance_m(p.latitude, p.longitude, fence.latitude, fence.longitude) <= fence.radius_m:
                    db.add(Alert(organization_id=vehicle.organization_id, vehicle_id=vehicle.id, kind="geofence", message=f"{vehicle.name} is inside {fence.name}"))
            count += 1
        vehicle.last_seen_at = now()
        db.commit()
        return count
    except IntegrityError:
        db.rollback(); return 0
    finally: db.close()


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth = 6_371_000
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return earth * 2 * asin(sqrt(a))


async def client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, protocol: str):
    imei = None
    try:
        if protocol == "teltonika":
            imei_packet = await reader.readexactly(17)
            imei = imei_packet.decode("ascii")
            writer.write(b"\x01"); await writer.drain()
        else:
            # GT06 login: 0x01 followed by a six-byte serial/IMEI payload.
            login = await read_frame(reader, "gt06")
            imei = ''.join(f'{b:02x}' for b in login[4:12]).lstrip('0')
            writer.write(login[-6:-2]); await writer.drain()
        while True:
            packet = await asyncio.wait_for(read_frame(reader, protocol), timeout=300)
            decoder = decode_teltonika if protocol == "teltonika" else decode_gt06
            count = ingest(protocol, imei, packet, decoder(packet, imei))
            if protocol == "teltonika": writer.write(b"\x00\x00\x00\x01" + count.to_bytes(4, "big"))
            else: writer.write(packet[-6:-2])
            await writer.drain()
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ValueError, UnicodeDecodeError):
        pass
    finally:
        writer.close(); await writer.wait_closed()


async def start_servers():
    return await asyncio.gather(
        asyncio.start_server(lambda r, w: client(r, w, "teltonika"), settings.tcp_teltonika_host, settings.tcp_teltonika_port),
        asyncio.start_server(lambda r, w: client(r, w, "gt06"), settings.tcp_gt06_host, settings.tcp_gt06_port),
    )
