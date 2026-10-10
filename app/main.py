from datetime import datetime, timezone
from threading import RLock
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="Device Fleet Monitor",
    description="Heartbeat-based device monitoring API",
    version="1.0.0",
)

TIMEOUT_SECONDS = 30
devices: dict[str, dict] = {}
devices_lock = RLock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DeviceRegistration(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)


class HeartbeatRequest(BaseModel):
    timestamp: datetime
    status: Literal["OK", "WARNING", "ERROR"] = "OK"
    cpu_usage: float | None = Field(default=None, ge=0, le=100)
    signal_strength: int | None = None


def current_status(device: dict, now: datetime | None = None) -> str:
    last_seen = device["last_heartbeat_at"]
    if last_seen is None:
        return "OFFLINE"

    elapsed = ((now or utc_now()) - last_seen).total_seconds()
    return "ONLINE" if elapsed <= TIMEOUT_SECONDS else "OFFLINE"


def serialize_device(device: dict) -> dict:
    return {
        "id": device["id"],
        "name": device["name"],
        "status": current_status(device),
        "last_heartbeat": (
            device["last_heartbeat_at"].isoformat()
            if device["last_heartbeat_at"] is not None
            else None
        ),
        "heartbeat_status": device["heartbeat_status"],
        "cpu_usage": device["cpu_usage"],
        "signal_strength": device["signal_strength"],
    }


def get_device_or_404(device_id: str) -> dict:
    device = devices.get(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@app.get(
    "/",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def home():
    return """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Device Fleet Monitor</title>
      <style>
        body { font: 16px system-ui, sans-serif; max-width: 900px;
               margin: 48px auto; padding: 0 20px; color: #172033;
               background: #f5f7fb; }
        h1 { margin-bottom: 8px; }
        p { color: #596579; }
        .panel { background: white; padding: 24px; border-radius: 12px;
                 border: 1px solid #e0e5ee; margin-top: 24px; }
        a { color: #155eef; margin-right: 20px; }
        code { background: #eef2ff; padding: 3px 6px; border-radius: 4px; }
      </style>
    </head>
    <body>
      <h1>Device Fleet Monitor</h1>
      <p>Monitor registered devices using heartbeat-based health tracking.</p>
      <div class="panel">
        <h2>API resources</h2>
        <p><a href="/docs">Interactive API documentation</a></p>
        <p><a href="/devices">View all devices</a></p>
        <p><a href="/summary">View fleet summary</a></p>
        <p>Device status changes to OFFLINE when no heartbeat is received
           for more than 30 seconds.</p>
      </div>
    </body>
    </html>
    """


@app.post("/devices", status_code=status.HTTP_201_CREATED)
def register_device(request: DeviceRegistration):
    with devices_lock:
        if request.id in devices:
            raise HTTPException(status_code=409, detail="Device already registered")

        devices[request.id] = {
            "id": request.id,
            "name": request.name,
            "last_heartbeat_at": None,
            "heartbeat_status": None,
            "cpu_usage": None,
            "signal_strength": None,
        }
        return serialize_device(devices[request.id])


@app.post("/devices/{device_id}/heartbeat")
def receive_heartbeat(device_id: str, request: HeartbeatRequest):
    with devices_lock:
        device = get_device_or_404(device_id)
        # Liveness uses server receipt time, not the device's clock.
        device["last_heartbeat_at"] = utc_now()
        device["heartbeat_status"] = request.status
        device["cpu_usage"] = request.cpu_usage
        device["signal_strength"] = request.signal_strength
        return serialize_device(device)


@app.get("/devices")
def list_devices():
    with devices_lock:
        return [serialize_device(device) for device in devices.values()]


@app.get("/devices/{device_id}")
def get_device(device_id: str):
    with devices_lock:
        return serialize_device(get_device_or_404(device_id))


@app.get("/summary")
def fleet_summary():
    with devices_lock:
        counts = {"ONLINE": 0, "OFFLINE": 0}
        for device in devices.values():
            counts[current_status(device)] += 1

        return {
            "total": len(devices),
            "online": counts["ONLINE"],
            "offline": counts["OFFLINE"],
        }

