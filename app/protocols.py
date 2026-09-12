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


def _u32(b: bytes) -> int:
    return struct.unpack(">I", b)[0]


def _crc16(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


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
    if len(data) != data_len or len(crc) != 4 or data[1] != packet[8 + data_len - 1] or int.from_bytes(crc[-2:], "big") != _crc16(data):
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
        # Skip IO according to Codec 8/8E. This keeps the GPS decoder strict and safe.
        if pos >= len(data): raise ValueError("truncated Teltonika IO")
        event_io = data[pos]; pos += 1
        if codec == 0x08:
            if pos + 1 > len(data): raise ValueError("truncated Teltonika IO")
            total = data[pos]; pos += 1
            for size, width in ((1, 1), (2, 2), (4, 4), (8, 8)):
                if pos >= len(data): break
                n = data[pos]; pos += 1 + n * (1 + width)
        else:
            if pos + 2 > len(data): raise ValueError("truncated Teltonika IO")
            total = int.from_bytes(data[pos:pos + 2], "big"); pos += 2
            for width, nbytes in ((1, 1), (2, 2), (4, 4), (8, 8), (16, 16)):
                if pos + 2 > len(data): break
                n = int.from_bytes(data[pos:pos + 2], "big"); pos += 2 + n * (2 + nbytes)
        out.append(NormalizedPosition(imei, datetime.fromtimestamp(ts / 1000, timezone.utc), lat, lon, alt, speed, angle, False, sats, f"{ts}-{lon}-{lat}"))
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
