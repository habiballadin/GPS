"""Routing and ETA provider abstraction.

The default implementation is deterministic and dependency-free.  Deployments can
set ROUTE_PROVIDER_URL to an OSRM-compatible endpoint (or a compatible proxy) to
get road distance and traffic-aware durations.
"""
from __future__ import annotations

from datetime import datetime
import math
from typing import Iterable

import httpx

from .config import settings


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def _provider_route(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    base = settings.route_provider_url
    if not base or len(points) < 2:
        return None
    coords = ";".join(f"{lon},{lat}" for lat, lon in points)
    url = f"{base.rstrip('/')}/route/v1/driving/{coords}"
    params = {"overview": "false", "steps": "false", "annotations": "false"}
    if settings.route_provider_api_key:
        params["access_token"] = settings.route_provider_api_key
    try:
        response = httpx.get(url, params=params, timeout=settings.route_provider_timeout_seconds)
        response.raise_for_status()
        route = response.json().get("routes", [])[0]
        distance = float(route["distance"])
        duration = float(route.get("duration_in_traffic", route["duration"]))
        return distance, duration / 60.0
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None


def traffic_factor(at: datetime | None = None) -> float:
    """Conservative local traffic estimate when no provider is configured."""
    value = at or datetime.now().astimezone()
    if value.weekday() < 5 and value.hour in (7, 8, 9, 16, 17, 18, 19):
        return 1.25
    return 1.0


def route_metrics(points: Iterable[tuple[float, float]], speed_kph: float = 40.0) -> dict:
    points = list(points)
    if len(points) < 2:
        return {"distance_m": 0.0, "estimated_minutes": None, "provider": "none", "traffic_aware": False, "traffic_factor": 1.0}
    provider = _provider_route(points)
    if provider:
        distance, minutes = provider
        return {"distance_m": distance, "estimated_minutes": minutes, "provider": settings.route_provider_name, "traffic_aware": True, "traffic_factor": 1.0}
    distance = sum(haversine_m(points[i - 1], points[i]) for i in range(1, len(points)))
    factor = traffic_factor()
    minutes = (distance / 1000.0) / max(speed_kph, 1.0) * 60.0 * factor
    return {"distance_m": distance, "estimated_minutes": minutes, "provider": "straight_line", "traffic_aware": factor > 1.0, "traffic_factor": factor}


def optimize_points(points: Iterable[tuple[float, float]]) -> list[int]:
    """Return a nearest-neighbour order, retaining the first stop as the anchor."""
    points = list(points)
    if len(points) < 3:
        return list(range(len(points)))
    remaining = set(range(1, len(points)))
    order = [0]
    while remaining:
        current = order[-1]
        nxt = min(remaining, key=lambda idx: haversine_m(points[current], points[idx]))
        order.append(nxt)
        remaining.remove(nxt)
    return order
