import json
import struct
from typing import Union

from pyproj import Geod

from shapely import from_wkb, from_wkt, from_geojson
from shapely.geometry.base import BaseGeometry

# Geometry types accepted as input
_GeometryInput = Union[str, bytes, dict]

# EWKB flag that signals an embedded SRID
_EWKB_SRID_FLAG = 0x20000000


def _strip_ewkb_srid(data: bytes) -> bytes:
    """
    Strip the 4-byte SRID prefix from PostGIS EWKB so Shapely can parse it.

    EWKB layout (little-endian example):
        byte 0        : byte order (0x01 = LE, 0x00 = BE)
        bytes 1-4     : geometry type (uint32) with SRID flag OR-ed in
        bytes 5-8     : SRID (uint32) — only present when flag is set
        bytes 9+      : actual WKB geometry payload
    """
    if len(data) < 5:
        raise ValueError("EWKB data is too short to be valid.")

    byte_order = data[0]
    little_endian = byte_order == 1

    fmt = "<I" if little_endian else ">I"
    (geom_type,) = struct.unpack_from(fmt, data, 1)

    if geom_type & _EWKB_SRID_FLAG:
        # Remove the 4-byte SRID field from the header and clear the flag
        clean_type = geom_type & ~_EWKB_SRID_FLAG
        header  = bytes([byte_order]) + struct.pack(fmt, clean_type)
        payload = data[9:]          # skip byte_order(1) + type(4) + srid(4)
        return header + payload

    return data


def _decode_geometry(raw: _GeometryInput) -> BaseGeometry:
    """
    Parse a geometry value into a Shapely geometry object.

    Supported input formats:
        - Hex-encoded WKB / EWKB string  (e.g. from PostGIS)
        - Raw WKB / EWKB bytes
        - WKT string                     (e.g. 'POINT (106.8 -6.2)')
        - EWKT string                    (e.g. 'SRID=4326;POINT (106.8 -6.2)')
        - GeoJSON dict or JSON string    (e.g. {"type": "Point", "coordinates": [...]})
    """
    if isinstance(raw, dict):
        return from_geojson(json.dumps(raw))

    if isinstance(raw, bytes):
        # Try EWKB (strip SRID if present), then fall back to standard WKB
        try:
            return from_wkb(_strip_ewkb_srid(raw))
        except Exception:
            return from_wkb(raw)

    if isinstance(raw, str):
        stripped = raw.strip()

        # Hex-encoded WKB / EWKB
        if all(c in "0123456789abcdefABCDEF" for c in stripped) and len(stripped) % 2 == 0:
            try:
                raw_bytes = bytes.fromhex(stripped)
                return from_wkb(_strip_ewkb_srid(raw_bytes))
            except Exception:
                pass

        # GeoJSON string
        if stripped.startswith("{"):
            try:
                return from_geojson(stripped)
            except Exception:
                pass

        # EWKT: strip the 'SRID=nnnn;' prefix, then parse as WKT
        if stripped.upper().startswith("SRID="):
            semicolon = stripped.find(";")
            if semicolon != -1:
                stripped = stripped[semicolon + 1:]

        # WKT
        return from_wkt(stripped)

    raise TypeError(
        f"Unsupported geometry input type: {type(raw).__name__}. "
        "Expected str (WKB hex / WKT / EWKT / GeoJSON), bytes (WKB/EWKB), or dict (GeoJSON)."
    )


def decode_point_4326(raw: _GeometryInput) -> tuple[float, float]:
    """
    Decode a single-point SRID 4326 geometry into (longitude, latitude).

    Parameters
    ----------
    raw : hex WKB/EWKB string, raw WKB/EWKB bytes, WKT/EWKT string,
          GeoJSON dict, or GeoJSON string

    Returns
    -------
    (longitude, latitude) as floats in decimal degrees

    Raises
    ------
    TypeError  : unsupported input type
    ValueError : input is not a Point geometry
    """
    geom = _decode_geometry(raw)

    if geom.geom_type != "Point":
        raise ValueError(
            f"Expected a Point geometry, got '{geom.geom_type}'. "
            "Use decode_geometry_4326 for other geometry types."
        )

    return geom.x, geom.y


def decode_geometry_4326(raw: _GeometryInput) -> dict:
    """
    Decode any SRID 4326 geometry into a plain dict.

    Returns
    -------
    For a Point:
        {"type": "Point", "longitude": float, "latitude": float}

    For Polygon / MultiPolygon / LineString / etc.:
        {"type": <geom_type>, "coordinates": <nested list of [lon, lat]>}

    Raises
    ------
    TypeError  : unsupported input type
    ValueError : geometry cannot be decoded
    """
    geom = _decode_geometry(raw)

    if geom.geom_type == "Point":
        return {"type": "Point", "longitude": geom.x, "latitude": geom.y}

    # For all other geometry types, return GeoJSON-style coordinates
    geojson = json.loads(geom.__geo_interface__["coordinates"]
                         if False  # keep branch for clarity
                         else json.dumps(geom.__geo_interface__))
    return {
        "type":        geojson["type"],
        "coordinates": geojson["coordinates"],
    }


# WGS-84 ellipsoid used for all geodesic calculations
_GEOD = Geod(ellps="WGS84")

def geodesic_distance_m(
    first_point: tuple[float],
    second_point: tuple[float]
) -> float:
    """
    Return the geodesic (ellipsoidal) distance in metres between two
    SRID 4326 points.

    Parameters
    ----------
    lon1, lat1 : origin point in decimal degrees
    lon2, lat2 : destination point in decimal degrees

    Returns
    -------
    Distance in metres (always positive).
    """
    lon1, lat1 = first_point
    lon2, lat2 = second_point
    _, _, distance_m = _GEOD.inv(lon1, lat1, lon2, lat2)
    return abs(distance_m)


def component_distance_m(
    first_point: tuple[float],
    second_point: tuple[float]
) -> tuple[float, float]:
    """
    Return the signed east-west and north-south distance components in
    metres between two SRID 4326 points.

    The components are computed independently along each axis:
      - delta_lon_m : distance along the longitude axis (positive = east)
      - delta_lat_m : distance along the latitude axis  (positive = north)

    Parameters
    ----------
    lon1, lat1 : origin point in decimal degrees
    lon2, lat2 : destination point in decimal degrees

    Returns
    -------
    (delta_lon_m, delta_lat_m) in metres
    """
    # East-west component: hold latitude constant, move only in longitude
    lon1, lat1 = first_point
    lon2, lat2 = second_point
    _, _, delta_lon_m = _GEOD.inv(lon1, lat1, lon2, lat1)
    # North-south component: hold longitude constant, move only in latitude
    _, _, delta_lat_m = _GEOD.inv(lon1, lat1, lon1, lat2)

    # _GEOD.inv returns the forward azimuth; determine sign from coordinate delta
    if lon2 < lon1:
        delta_lon_m = -abs(delta_lon_m)
    else:
        delta_lon_m = abs(delta_lon_m)

    if lat2 < lat1:
        delta_lat_m = -abs(delta_lat_m)
    else:
        delta_lat_m = abs(delta_lat_m)

    return delta_lon_m, delta_lat_m
