"""Fetch device topics from the RiceMesh backend API on startup."""

__all__ = ["fetch_device_topics"]

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

_API_HOST  = os.getenv("RICEMESH_API_HOST")
_API_EMAIL = os.getenv("RICEMESH_API_EMAIL")
_API_PASS  = os.getenv("RICEMESH_API_PASS")


async def _login(client: httpx.AsyncClient) -> str:
    """POST /login and return the Bearer JWT token.

    Raises RuntimeError if credentials are missing or login fails.
    """
    if not _API_HOST or not _API_EMAIL or not _API_PASS:
        raise RuntimeError(
            "RICEMESH_API_HOST, RICEMESH_API_EMAIL, and RICEMESH_API_PASS "
            "must be set in environment"
        )

    resp = await client.post(
        f"{_API_HOST}/auth/login",
        json={"email": _API_EMAIL, "password": _API_PASS},
    )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Login failed: HTTP {resp.status_code} — {resp.text}"
        )

    body: dict = resp.json()
    data: dict = body.get("data")
    token = data.get("access_token")
    if not token:
        raise RuntimeError(
            f"Login response did not contain a token field: {resp.json()}"
        )

    return token


async def _get_device_topics(client: httpx.AsyncClient, token: str) -> list[str]:
    """GET /devices across all pages with Bearer auth and return all topic strings.

    Uses meta.totalPages from the first response to determine how many pages to fetch.
    Raises RuntimeError if any request fails or the response is malformed.
    """
    headers = {"Authorization": f"Bearer {token}"}
    topics: list[str] = []
    page = 1

    while True:
        resp = await client.get(
            f"{_API_HOST}/devices",
            headers=headers,
            params={"page": page},
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch devices (page {page}): HTTP {resp.status_code} — {resp.text}"
            )

        body: dict = resp.json()
        devices: list[dict] = body.get("data", [])
        topics.extend(d["topic"] for d in devices if d.get("topic"))

        total_pages = body.get("meta", {}).get("totalPages", 1)
        if page >= total_pages:
            break

        page += 1

    return topics



async def fetch_device_topics() -> list[str]:
    """Login to the RiceMesh API and return the MQTT topic for every device.

    Returns an empty list if login or device fetch fails (logged to stdout).
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token  = await _login(client)
            topics = await _get_device_topics(client, token)
            print(f"Fetched {len(topics)} device topic(s): {topics}")
            return topics
    except Exception as e:
        print(f"[device_bootstrap] Could not fetch device topics: {e}")
        return []
