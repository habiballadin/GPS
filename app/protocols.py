"""Small, isolated decoders for supported tracker protocols.

No custom device protocol is mixed into the HTTP layer. Add a decoder here and
map its output to NormalizedPosition; the rest of the system remains unchanged.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import struct


@dataclass
class NormalizedPosition:
    imei: str
    recorded_at: datetime
    latitude: float
    longitude: float
    altitude: float = 0
    speed_kph: float = 0
    heading: float = 0
    ignition: bool = False
    satellites: int = 0
    event_id: str = ""
    # IO telemetry fields
    harsh_braking: bool = False
    harsh_acceleration: bool = False
    harsh_cornering: bool = False
    towing: bool = False
    jamming: bool = False
    sos: bool = False
    crash: bool = False
    door_open: bool = False
    ext_voltage_mv: int = 0
    battery_mv: int = 0
    fuel_level: int = 0       # IO element 9 — analog input 1 (fuel sensor)
    odometer_m: int = 0       # IO element 16000 if available


def _u32(b: bytes) -> int:
    return struct.unpack(">I", b)[0]


def _crc16_ibm(data: bytes) -> int:
    """CRC-16/IBM used by Teltonika Codec 8/8E AVL frames."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def decode_codec12_response(packet: bytes) -> str:
    """Decode a Codec 12 or 13 command response from a Teltonika device."""
    if len(packet) < 12 or packet[:4] != b"\x00\x00\x00\x00":
        raise ValueError("invalid Teltonika frame")
    data_len = _u32(packet[4:8])
    data = packet[8:8 + data_len]
    codec = data[0]
    if codec not in (0x0C, 0x0D):
        raise ValueError("not a Codec 12/13 response")
    p = 1
    if data[p] != 1: raise ValueError("unexpected quantity")
    p += 1
    if data[p] != 0x06: raise ValueError("not a response type")
    p += 1
    if codec == 0x0D:
        imei_len = int.from_bytes(data[p:p + 4], "big"); p += 4
        p += imei_len  # skip IMEI
    resp_len = int.from_bytes(data[p:p + 4], "big"); p += 4
    return data[p:p + resp_len].decode("ascii", errors="replace")


def decode_teltonika(packet: bytes, imei: str) -> tuple[NormalizedPosition, ...]:
    """Decode Teltonika Codec 8/8E AVL packets (GPS and core IO fields).

    The reader validates the preamble, length, codec and CRC framing. It accepts
    Codec 8 and 8 Extended packets; unsupported IO layouts are rejected safely.
    """
    if len(packet) < 24 or packet[:4] != b"\x00\x00\x00\x00":
        raise ValueError("invalid Teltonika frame")
    data_len = _u32(packet[4:8])
    data = packet[8:8 + data_len]
    crc = packet[8 + data_len:12 + data_len]
    if len(data) != data_len or len(crc) != 4 or data[1] != packet[8 + data_len - 1] or int.from_bytes(crc[-2:], "big") != _crc16_ibm(data):
        raise ValueError("invalid Teltonika frame length")
    codec, count = data[0], data[1]
    if codec not in (0x08, 0x8E):
        raise ValueError("unsupported Teltonika codec")
    pos = 2
    out = []
    for _ in range(count):
        if pos + 24 > len(data):
            raise ValueError("truncated Teltonika AVL record")
        ts = int.from_bytes(data[pos:pos + 8], "big"); pos += 8
        priority = data[pos]; pos += 1
        lon = int.from_bytes(data[pos:pos + 4], "big", signed=True) / 10_000_000; pos += 4
        lat = int.from_bytes(data[pos:pos + 4], "big", signed=True) / 10_000_000; pos += 4
        alt = int.from_bytes(data[pos:pos + 2], "big", signed=True); pos += 2
        angle = int.from_bytes(data[pos:pos + 2], "big"); pos += 2
        sats = data[pos]; pos += 1
        speed = int.from_bytes(data[pos:pos + 2], "big"); pos += 2
        # Parse IO elements from Codec 8/8E
        io: dict[int, int] = {}
        if pos >= len(data): raise ValueError("truncated Teltonika IO")
        event_io = data[pos]; pos += 1
        if codec == 0x08:
            if pos + 1 > len(data): raise ValueError("truncated Teltonika IO")
            _total = data[pos]; pos += 1
            for width in (1, 2, 4, 8):
                if pos >= len(data): break
                n = data[pos]; pos += 1
                for _ in range(n):
                    if pos + 1 + width > len(data): break
                    eid = data[pos]; pos += 1
                    io[eid] = int.from_bytes(data[pos:pos + width], "big"); pos += width
        else:  # 8E
            if pos + 2 > len(data): raise ValueError("truncated Teltonika IO")
            _total = int.from_bytes(data[pos:pos + 2], "big"); pos += 2
            for width in (1, 2, 4, 8, 16):
                if pos + 2 > len(data): break
                n = int.from_bytes(data[pos:pos + 2], "big"); pos += 2
                for _ in range(n):
                    if pos + 2 + width > len(data): break
                    eid = int.from_bytes(data[pos:pos + 2], "big"); pos += 2
                    io[eid] = int.from_bytes(data[pos:pos + width], "big"); pos += width
        out.append(NormalizedPosition(
            imei=imei,
            recorded_at=datetime.fromtimestamp(ts / 1000, timezone.utc),
            latitude=lat, longitude=lon, altitude=alt,
            speed_kph=speed, heading=angle, satellites=sats,
            event_id=f"{ts}-{lon}-{lat}",
            ignition=bool(io.get(239, 0)),
            harsh_braking=bool(io.get(16, 0)),
            harsh_acceleration=bool(io.get(17, 0)),
            harsh_cornering=bool(io.get(18, 0)),
            towing=bool(io.get(236, 0)),
            jamming=bool(io.get(449, 0)),
            sos=bool(io.get(1, 0)),
            crash=bool(io.get(247, 0)),
            door_open=bool(io.get(2, 0)),
            ext_voltage_mv=io.get(66, 0),
            battery_mv=io.get(67, 0),
            fuel_level=io.get(9, 0),
            odometer_m=io.get(16000, 0),
        ))
    return tuple(out)


def _bcd_date(value: bytes) -> datetime:
    digits = ''.join(f'{x:02x}' for x in value)
    yy, mm, dd, hh, mi, ss = [int(digits[i:i + 2]) for i in range(0, 12, 2)]
    return datetime(2000 + yy, mm, dd, hh, mi, ss, tzinfo=timezone.utc)


def decode_gt06(packet: bytes, imei: str) -> tuple[NormalizedPosition, ...]:
    """Decode GT06 location packets used by many CONCOX V5 units."""
    if len(packet) < 20 or packet[:2] not in (b"\x78\x78", b"\x79\x79"):
        raise ValueError("invalid GT06 frame")
    length_bytes = 1 if packet[:2] == b"\x78\x78" else 2
    length = packet[2] if length_bytes == 1 else int.from_bytes(packet[2:4], "big")
    start = 3 if length_bytes == 1 else 4
    frame = packet[:start + length + 2]
    if len(frame) < start + length + 2:
        raise ValueError("truncated GT06 frame")
    protocol = packet[start]
    if protocol not in (0x10, 0x11, 0x12, 0x22):
        raise ValueError("unsupported GT06 protocol")
    p = start + 1
    recorded = _bcd_date(packet[p:p + 6]); p += 6
    sats = packet[p] & 0x0F; p += 1
    lat = int.from_bytes(packet[p:p + 4], "big") / 1_800_000; p += 4
    lon = int.from_bytes(packet[p:p + 4], "big") / 1_800_000; p += 4
    course_status = int.from_bytes(packet[p:p + 2], "big"); p += 2
    speed = packet[p]
    # GT06 latitude/longitude sign bits live in the course/status word.
    if not (course_status & 0x8000): lat = -lat
    if course_status & 0x4000: lon = -lon
    return (NormalizedPosition(imei, recorded, lat, lon, speed_kph=speed, heading=course_status & 0x03FF, satellites=sats, event_id=f"{recorded.isoformat()}-{lat}-{lon}"),)
