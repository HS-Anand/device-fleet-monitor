
import json
import queue
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests


BASE_URL = "http://127.0.0.1:8000"
CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 8765
HEARTBEAT_INTERVAL = 5
DEVICE_COUNT = 5


class DeviceSimulator:
    def __init__(self):
        self.stop_events = {}
        self.threads = {}
        self.lock = threading.Lock()
        self.events = queue.Queue()

    def report_event(self, message):
        now = datetime.now().strftime("%H:%M:%S")
        self.events.put(f"[{now}] {message}")

    def register_devices(self):
        for i in range(1, DEVICE_COUNT + 1):
            device_id = f"device-{i:02d}"

            response = requests.post(
                f"{BASE_URL}/devices",
                json={
                    "id": device_id,
                    "name": f"Lab Device {i:02d}",
                },
                timeout=5,
            )

            if response.status_code == 409:
                print(f"{device_id}: already registered")
            else:
                response.raise_for_status()
                print(f"{device_id}: registered")

    def send_heartbeats(self, device_id, stop_event):
        while not stop_event.is_set():
            try:
                response = requests.post(
                    f"{BASE_URL}/devices/{device_id}/heartbeat",
                    json={
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "status": "OK",
                    },
                    timeout=4,
                )
                response.raise_for_status()

                now = datetime.now().strftime("%H:%M:%S")
                print(f"[{now}] {device_id} -> heartbeat sent", flush=True)

            except requests.RequestException as exc:
                print(f"{device_id}: heartbeat failed: {exc}", flush=True)

            stop_event.wait(HEARTBEAT_INTERVAL)

    def start_device(self, device_id):
        with self.lock:
            existing = self.threads.get(device_id)

            if existing and existing.is_alive():
                if not self.stop_events[device_id].is_set():
                    return False, "Device is already running."

                return False, "Device is still stopping; try again shortly."

            stop_event = threading.Event()
            thread = threading.Thread(
                target=self.send_heartbeats,
                args=(device_id, stop_event),
                name=f"heartbeat-{device_id}",
                daemon=True,
            )

            self.stop_events[device_id] = stop_event
            self.threads[device_id] = thread
            thread.start()

        self.report_event(
            f"{device_id} -> heartbeat restarted by controller"
        )
        return True, "Heartbeat loop started."

    def stop_device(self, device_id):
        with self.lock:
            thread = self.threads.get(device_id)
            stop_event = self.stop_events.get(device_id)

            if thread is None or stop_event is None:
                return False, "Device is not running."

            if stop_event.is_set():
                return False, "Device is already stopping."

            stop_event.set()

        thread.join(timeout=5)

        if thread.is_alive():
            return False, "Device is still stopping; try again shortly."

        with self.lock:
            self.threads.pop(device_id, None)
            self.stop_events.pop(device_id, None)

        self.report_event(
            f"{device_id} -> heartbeat stopped by controller"
        )
        return True, "Heartbeat loop stopped."

    def get_status(self):
        with self.lock:
            return {
                f"device-{i:02d}": (
                    "RUNNING"
                    if (
                        (thread := self.threads.get(f"device-{i:02d}"))
                        and thread.is_alive()
                        and not self.stop_events[f"device-{i:02d}"].is_set()
                    )
                    else "STOPPED"
                )
                for i in range(1, DEVICE_COUNT + 1)
            }

    def shutdown(self):
        with self.lock:
            devices = list(self.threads.items())
            for device_id, stop_event in self.stop_events.items():
                stop_event.set()

        for device_id, thread in devices:
            thread.join(timeout=5)

        with self.lock:
            self.threads.clear()
            self.stop_events.clear()


def make_control_handler(simulator, request_shutdown):
    class ControlHandler(BaseHTTPRequestHandler):
        def send_json(self, status_code, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/status":
                self.send_json(404, {"error": "Unknown control endpoint"})
                return

            self.send_json(200, {"devices": simulator.get_status()})

        def do_POST(self):
            if self.path == "/shutdown":
                self.send_json(200, {"message": "Simulator shutting down."})
                threading.Thread(
                    target=request_shutdown,
                    daemon=True,
                ).start()
                return

            parts = self.path.strip("/").split("/")

            if len(parts) != 3 or parts[0] != "devices":
                self.send_json(404, {"error": "Unknown control endpoint"})
                return

            device_id, action = parts[1], parts[2]
            valid_devices = {
                f"device-{i:02d}" for i in range(1, DEVICE_COUNT + 1)
            }

            if device_id not in valid_devices:
                self.send_json(404, {"error": "Unknown simulated device"})
                return

            if action == "stop":
                success, message = simulator.stop_device(device_id)
            elif action == "start":
                success, message = simulator.start_device(device_id)
            else:
                self.send_json(404, {"error": "Action must be start or stop"})
                return

            self.send_json(
                200 if success else 409,
                {"device": device_id, "message": message},
            )

        def log_message(self, format, *args):
            pass

    return ControlHandler


def main():
    simulator = DeviceSimulator()
    control_server = None
    event_thread = None

    try:
        simulator.register_devices()

        for i in range(1, DEVICE_COUNT + 1):
            simulator.start_device(f"device-{i:02d}")

        control_server = ThreadingHTTPServer(
            (CONTROL_HOST, CONTROL_PORT),
            make_control_handler(simulator, lambda: control_server.shutdown()),
        )

        control_thread = threading.Thread(
            target=control_server.serve_forever,
            daemon=True,
        )
        control_thread.start()

        def display_events():
            while True:
                message = simulator.events.get()
                if message is None:
                    break
                print(message, flush=True)

        event_thread = threading.Thread(
            target=display_events,
            daemon=True,
        )
        event_thread.start()

        print("\nDevice simulator running:")
        for i in range(1, DEVICE_COUNT + 1):
            print(
                f"device-{i:02d} -> heartbeat every "
                f"{HEARTBEAT_INTERVAL} seconds"
            )

        print(f"\nControl interface: http://{CONTROL_HOST}:{CONTROL_PORT}")
        control_thread.join()

    except requests.RequestException as exc:
        print(f"Cannot reach the monitoring API at {BASE_URL}: {exc}")
    except OSError as exc:
        print(f"Could not start the control interface: {exc}")
    except KeyboardInterrupt:
        print("\nShutting down simulator...")
    finally:
        simulator.shutdown()

        if control_server is not None:
            control_server.server_close()

        simulator.events.put(None)
        if event_thread is not None:
            event_thread.join(timeout=2)

        print("Simulator stopped.")


if __name__ == "__main__":
    main()
