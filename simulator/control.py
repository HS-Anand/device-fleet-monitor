import requests


CONTROL_URL = "http://127.0.0.1:8765"
API_URL = "http://127.0.0.1:8000"
DEVICE_IDS = {f"device-{i:02d}" for i in range(1, 6)}


def show_status():
    # Get the simulator thread states.
    control_response = requests.get(
        f"{CONTROL_URL}/status", timeout=5
    )
    control_response.raise_for_status()
    simulator_states = control_response.json()["devices"]

    # Get the actual heartbeat-derived device statuses.
    api_response = requests.get(
        f"{API_URL}/devices", timeout=5
    )
    api_response.raise_for_status()
    api_devices = {
        device["id"]: device["status"]
        for device in api_response.json()
    }

    print("\n=== Device Fleet Status ===")
    print(f"  {'Device':<14} {'Simulator':<14} {'API Status'}")
    print(f"  {'-' * 14} {'-' * 14} {'-' * 12}")

    online = 0
    offline = 0

    for device_id in sorted(DEVICE_IDS):
        simulator_state = simulator_states.get(
            device_id, "UNKNOWN"
        )
        api_status = api_devices.get(device_id, "UNKNOWN")

        print(
            f"  {device_id:<14} "
            f"{simulator_state:<14} "
            f"{api_status}"
        )

        if api_status == "ONLINE":
            online += 1
        elif api_status == "OFFLINE":
            offline += 1

    print(f"\n  Fleet: {online} ONLINE | {offline} OFFLINE\n")


def control_device(action, device_id):
    if device_id not in DEVICE_IDS:
        print("Unknown device. Choose device-01 to device-05.")
        return

    response = requests.post(
        f"{CONTROL_URL}/devices/{device_id}/{action}",
        timeout=8,
    )

    data = response.json()
    if response.ok:
        print(f"{data['device']}: {data['message']}")
    else:
        print(f"Error: {data.get('message', data.get('error'))}")


def main():

    print("Device Simulator Controller")
    print()
    print("Available commands:")
    print("  start <device_id> - Start sending device heartbeats.")
    print("  stop <device_id>  - Stop that device's heartbeats.")
    print("  status            - Show simulator and API status.")
    print("  quit              - Shut down the entire simulation.")
    print()
    print("Devices: device-01 to device-05")
    print()

    while True:
        try:
            command = input("controller> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nController closed; simulator continues running.")
            break

        if not command:
            continue

        if command == "quit":
            try:
                response = requests.post(
                    f"{CONTROL_URL}/shutdown",
                    timeout=5,
                )
                response.raise_for_status()
                print("Simulator shutdown requested.")
            except requests.RequestException as exc:
                print(f"Could not stop simulator: {exc}")
            break

        if command == "status":
            try:
                show_status()
            except requests.RequestException as exc:
                print(f"Could not retrieve fleet status: {exc}")
            continue

        parts = command.split()
        if len(parts) != 2 or parts[0] not in {"start", "stop"}:
            print("Invalid command. Example: stop device-03")
            continue

        try:
            control_device(parts[0], parts[1])
        except requests.RequestException as exc:
            print(f"Could not reach simulator: {exc}")


if __name__ == "__main__":
    main()