"""Prove that the test suite cannot reach the internet, and that local tooling still works."""

from __future__ import annotations

import socket

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest_socket import SocketConnectBlockedError

# A public IP literal, so the check does not depend on DNS being available.
_PUBLIC_ADDRESS = ("1.1.1.1", 443)


def test_raw_socket_to_public_host_is_blocked() -> None:
    with pytest.raises(SocketConnectBlockedError):
        socket.create_connection(_PUBLIC_ADDRESS, timeout=1)


def test_requests_library_is_blocked() -> None:
    # The official serpapi client uses requests, so this is the path real searches take.
    with pytest.raises(SocketConnectBlockedError):
        requests.get("https://1.1.1.1/", timeout=1)


def test_fastapi_test_client_still_works() -> None:
    # On Windows asyncio needs a loopback socketpair; the block must not break it.
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        response = client.get("/ping")
    assert response.json() == {"status": "ok"}
