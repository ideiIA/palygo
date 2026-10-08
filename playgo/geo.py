"""Distância entre pontos. Sem PostGIS: latitude/longitude em colunas comuns, caixa delimitadora
para o índice e haversine para a distância exata — suficiente na escala de uma cidade."""

from math import asin, cos, radians, sin, sqrt

from sqlalchemy import Float, and_, cast, func

RAIO_TERRA_KM = 6371.0088
KM_POR_GRAU = 111.32


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lng2 - lng1) / 2) ** 2
    return 2 * RAIO_TERRA_KM * asin(min(1.0, sqrt(a)))


def distancia_sql(col_lat, col_lng, lat: float, lng: float):
    """Expressão SQL da distância em km até (lat, lng)."""
    p1, p2 = radians(lat), func.radians(cast(col_lat, Float))
    dlat = p2 - p1
    dlng = func.radians(cast(col_lng, Float)) - radians(lng)
    a = func.power(func.sin(dlat / 2), 2) + cos(p1) * func.cos(p2) * func.power(func.sin(dlng / 2), 2)
    return 2 * RAIO_TERRA_KM * func.asin(func.least(1.0, func.sqrt(a)))


def caixa_sql(col_lat, col_lng, lat: float, lng: float, km: float):
    """Pré-filtro barato (usa índice) que garante conter o círculo de `km` ao redor do ponto."""
    dlat = km / KM_POR_GRAU
    dlng = km / (KM_POR_GRAU * max(0.05, cos(radians(lat))))
    return and_(col_lat.between(lat - dlat, lat + dlat), col_lng.between(lng - dlng, lng + dlng))


def formatar_km(km: float | None) -> str:
    if km is None:
        return ""
    return f"{km:.1f} km".replace(".", ",") if km >= 1 else f"{round(km * 1000 / 10) * 10} m"
