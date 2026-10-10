
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.main as main


client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clear_devices():
    """Keep each test independent of previously registered devices."""
    with main.devices_lock:
        main.devices.clear()

    yield

    with main.devices_lock:
        main.devices.clear()


def test_device_registration():
    response = client.post(
        "/devices",
        json={"id": "device-01", "name": "Lab Device 01"},
    )

    assert response.status_code == 201
    assert response.json()["id"] == "device-01"
    assert response.json()["status"] == "OFFLINE"


def test_duplicate_registration_returns_conflict():
    payload = {"id": "device-01", "name": "Lab Device 01"}

    client.post("/devices", json=payload)
    response = client.post("/devices", json=payload)

    assert response.status_code == 409


def test_heartbeat_marks_device_online():
    client.post(
        "/devices",
        json={"id": "device-01", "name": "Lab Device 01"},
    )

    response = client.post(
        "/devices/device-01/heartbeat",
        json={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "OK",
            "cpu_usage": 45.5,
            "signal_strength": -70,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ONLINE"
    assert response.json()["heartbeat_status"] == "OK"
    assert response.json()["cpu_usage"] == 45.5


def test_heartbeat_for_unknown_device_returns_404():
    response = client.post(
        "/devices/missing/heartbeat",
        json={"timestamp": datetime.now(timezone.utc).isoformat()},
    )

    assert response.status_code == 404


def test_device_status_changes_after_30_seconds():
    last_heartbeat = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)
    device = {"last_heartbeat_at": last_heartbeat}

    assert main.current_status(device, last_heartbeat) == "ONLINE"
    assert (
        main.current_status(
            device, last_heartbeat + timedelta(seconds=30)
        )
        == "ONLINE"
    )
    assert (
        main.current_status(
            device, last_heartbeat + timedelta(seconds=31)
        )
        == "OFFLINE"
    )


def test_new_device_without_heartbeat_is_offline():
    device = {"last_heartbeat_at": None}

    assert main.current_status(device) == "OFFLINE"


def test_fleet_summary_counts_devices():
    client.post(
        "/devices",
        json={"id": "device-01", "name": "Device 01"},
    )
    client.post(
        "/devices",
        json={"id": "device-02", "name": "Device 02"},
    )

    client.post(
        "/devices/device-01/heartbeat",
        json={"timestamp": datetime.now(timezone.utc).isoformat()},
    )

    response = client.get("/summary")

    assert response.status_code == 200
    assert response.json() == {
        "total": 2,
        "online": 1,
        "offline": 1,
    }


def test_invalid_cpu_usage_is_rejected():
    client.post(
        "/devices",
        json={"id": "device-01", "name": "Device 01"},
    )

    response = client.post(
        "/devices/device-01/heartbeat",
        json={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu_usage": 101,
        },
    )

    assert response.status_code == 422



def test_api_status_changes_after_timeout(monkeypatch):
    heartbeat_time = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)
    current_time = heartbeat_time

    monkeypatch.setattr(main, "utc_now", lambda: current_time)

    client.post(
        "/devices",
        json={"id": "device-timeout", "name": "Timeout Test Device"},
    )

    client.post(
        "/devices/device-timeout/heartbeat",
        json={
            "timestamp": heartbeat_time.isoformat(),
            "status": "OK",
        },
    )

    response = client.get("/devices/device-timeout")
    assert response.status_code == 200
    assert response.json()["status"] == "ONLINE"

    current_time = heartbeat_time + timedelta(seconds=31)

    response = client.get("/devices/device-timeout")
    assert response.status_code == 200
    assert response.json()["status"] == "OFFLINE"


