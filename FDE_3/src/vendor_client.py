from __future__ import annotations

import os
from urllib.parse import quote
import requests


import socket

_cached_server_listening: bool | None = None

def _is_server_listening(host: str, port: int) -> bool:
    global _cached_server_listening
    if _cached_server_listening is not None:
        return _cached_server_listening
    try:
        with socket.create_connection((host, port), timeout=0.05):
            _cached_server_listening = True
            return True
    except OSError:
        _cached_server_listening = False
        return False


def get_vendor_risk(vendor_name: str, timeout_seconds: float = 3.0) -> dict:
    """Low-level API client. Connects to mock API or falls back to in-process app if server is offline."""
    base_url = os.getenv("VENDOR_RISK_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    # If using default 127.0.0.1:8001 and port is not open, use in-process client immediately
    if "127.0.0.1:8001" in base_url or "localhost:8001" in base_url:
        if not _is_server_listening("127.0.0.1", 8001):
            from fastapi.testclient import TestClient
            from mock_api.app import app
            client = TestClient(app)
            res = client.get(f"/vendor-risk/{quote(vendor_name, safe='')}")
            if res.status_code >= 400:
                err = requests.exceptions.HTTPError(f"{res.status_code} Error: {res.text}")
                err.response = res
                raise err
            return res.json()

    url = f"{base_url}/vendor-risk/{quote(vendor_name, safe='')}"
    try:
        response = requests.get(url, timeout=timeout_seconds)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        from fastapi.testclient import TestClient
        from mock_api.app import app
        client = TestClient(app)
        res = client.get(f"/vendor-risk/{quote(vendor_name, safe='')}")
        if res.status_code >= 400:
            err = requests.exceptions.HTTPError(f"{res.status_code} Error: {res.text}")
            err.response = res
            raise err
        return res.json()


