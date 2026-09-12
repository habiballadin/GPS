from app.protocols import decode_gt06


def test_invalid_gt06_is_rejected():
    try:
        decode_gt06(b"bad", "123")
    except ValueError as exc:
        assert "invalid GT06" in str(exc)
    else:
        assert False
