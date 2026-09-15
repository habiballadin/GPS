"""Latest vehicle state cache with Redis in production and memory locally."""
import json
from threading import Lock
from .config import settings

_memory: dict[str, dict] = {}
_lock = Lock()
_redis = None

def _client():
    global _redis
    if _redis is not None or not settings.redis_url:
        return _redis
    try:
        from redis import Redis
        _redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
        _redis.ping()
        return _redis
    except Exception:
        _redis = None
        return None

def set_vehicle_state(organization_id: int, vehicle_id: int, state: dict) -> None:
    key = f"fleet:{organization_id}:vehicle:{vehicle_id}"
    client = _client()
    if client:
        try:
            client.setex(key, settings.live_state_ttl_seconds, json.dumps(state, separators=(",", ":")))
            return
        except Exception:
            pass
    with _lock: _memory[key] = state

def get_vehicle_states(organization_id: int) -> list[dict]:
    prefix = f"fleet:{organization_id}:vehicle:"
    client = _client()
    if client:
        try:
            states = []
            for key in client.scan_iter(match=f"{prefix}*"):
                raw = client.get(key)
                if raw: states.append(json.loads(raw))
            return states
        except Exception:
            pass
    with _lock: return [value for key, value in _memory.items() if key.startswith(prefix)]
