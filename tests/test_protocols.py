from app.gateway import _crc16_gt06, _gt06_ack
from app.protocols import _crc16_ibm, decode_gt06


def test_invalid_gt06_is_rejected():
    try:
        decode_gt06(b"bad", "123")
    except ValueError as exc:
        assert "invalid GT06" in str(exc)
    else:
        assert False


def test_gt06_login_ack_uses_crc_itu():
    # Published GT06 login response for serial 0x0001.
    assert _crc16_gt06(bytes.fromhex("05010001")) == 0xD9DC
    assert _gt06_ack(0x01, bytes.fromhex("0001")) == bytes.fromhex("787805010001d9dc0d0a")


def test_teltonika_crc_uses_ibm_variant():
    assert _crc16_ibm(b"123456789") == 0xBB3D
