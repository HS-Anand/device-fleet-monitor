# Device Fleet Monitor

A Python application for monitoring a small fleet of simulated devices. Devices send heartbeats to a FastAPI backend, which records the latest heartbeat and reports whether each device is `ONLINE` or `OFFLINE`.

A device is `ONLINE` when the backend has received a heartbeat within the last 30 seconds. If the last heartbeat is more than 30 seconds old, the device is `OFFLINE`.



## Design and Architecture

I split the project into three parts so that device monitoring, device simulation, and operator controls could be handled independently.

- **Backend (`app/main.py`):** Handles device registration, heartbeat requests, device details, and fleet summary. It stores device information in memory and calculates connectivity status from the time of the last heartbeat.
- **Simulator (`simulator/simulator.py`):** Simulates five devices independently, with each device sending heartbeats every five seconds. Individual devices can be started and stopped without stopping the entire simulation.
- **Controller (`simulator/controller.py`):** Provides a separate interface for the operator to check simulator and API status, start or stop individual devices, and shut down the simulation.

### How the components work together

The simulator sends heartbeat requests to the backend over HTTP. The backend records each heartbeat and determines whether the device is `ONLINE` or `OFFLINE`. The controller communicates with the simulator's control interface and queries the backend API to show both the simulator's running state and the device's connectivity status.

Keeping these two statuses separate is intentional. A simulator worker can be stopped while the device remains `ONLINE` until its last heartbeat exceeds the 30-second timeout. This also makes it possible to demonstrate the timeout and recovery behaviour through the controller.

### Main design decisions

- **Request-driven status calculation:** Status is calculated when an API request is handled, avoiding a separate background worker to update device statuses.
- **Independent device controls:** Each simulated device has its own lifecycle controls, so one device can be stopped or restarted without affecting the others.
- **Separation of responsibilities:** The backend manages monitoring data, the simulator generates heartbeats, and the controller handles operator actions.
- **Simple state management:** An in-memory store keeps the implementation small and avoids introducing database setup for this assignment.

This structure keeps the project straightforward while making the main behaviours easy to run, observe, and test.

## Requirements

- Python 3.10 or newer
- Git
- A terminal

The commands below use macOS/Linux shell syntax. If you use Windows, activate the virtual environment with `.venv\\Scripts\\activate` instead of `source .venv/bin/activate`.

## 1. Clone and install

Clone the repository and move into the project directory:

```bash
git clone https://github.com/HS-Anand/device-fleet-monitor.git
cd device-fleet-monitor
```

Create a virtual environment and install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the remaining commands from the project root, with the virtual environment activated. If you open a new terminal, activate it again:

```bash
cd device-fleet-monitor
source .venv/bin/activate
```

## 2. Start the backend

In the first terminal, run:

```bash
uvicorn app.main:app --reload
```

The backend runs at `http://127.0.0.1:8000`. Keep this terminal open while using the simulator or controller.

Useful URLs:

- Swagger UI: http://127.0.0.1:8000/docs
- List devices: http://127.0.0.1:8000/devices
- Fleet summary: http://127.0.0.1:8000/summary

Swagger UI lets you try the API endpoints from your browser.

## 3. Start the simulator

Open a second terminal, go to the repository directory, activate the virtual environment, and run:

```bash
python simulator/simulate.py
```

The simulator registers `device-01` through `device-05` and sends heartbeats every five seconds. Leave it running while testing the fleet.

## 4. Start the controller

Open a third terminal, go to the repository directory, activate the virtual environment, and run:

```bash
python simulator/control.py
```

Use the commands printed by the controller to check status or start and stop individual devices.

To test the timeout:

1. Use the controller to stop one device.
2. Keep the backend and controller running and wait more than 30 seconds.
3. Check the API status; that device should now be `OFFLINE`.
4. Start the device again. When its next heartbeat reaches the backend, it should return to `ONLINE`.

Stopping a simulator worker does not immediately change the API status. The backend continues to report the device as `ONLINE` until its last heartbeat is older than 30 seconds.

To finish, use the controller's shutdown command if available, then stop the backend with `Ctrl+C`. If a simulator terminal is still running, stop it using its normal quit/shutdown command or `Ctrl+C`.

## API examples

The examples below assume the backend is running at `http://127.0.0.1:8000`. You can run them in another terminal or try the same endpoints in Swagger UI.

### Register a device

`POST /devices`

```bash
curl -X POST http://127.0.0.1:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"id":"device-01","name":"Lab Device 01"}'
```

A successful registration returns `201 Created`. Registering an ID that already exists returns `409 Conflict`.

### Send a heartbeat

`POST /devices/{id}/heartbeat`

```bash
curl -X POST http://127.0.0.1:8000/devices/device-01/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"timestamp":"2026-10-10T10:30:00Z","status":"OK","cpu_usage":42,"signal_strength":-71}'
```

The heartbeat includes a timestamp and a device-reported status. CPU usage and signal strength are optional metrics. Connectivity is calculated using the time the backend receives the heartbeat, rather than trusting the device's clock.

### List all devices

`GET /devices`

```bash
curl http://127.0.0.1:8000/devices
```

### Get one device

`GET /devices/{id}`

```bash
curl http://127.0.0.1:8000/devices/device-01
```

An unknown device returns `404 Not Found`.

### Get a fleet summary

`GET /summary`

```bash
curl http://127.0.0.1:8000/summary
```

Example response:

```json
{
  "total": 5,
  "online": 5,
  "offline": 0
}
```

The values depend on the latest heartbeat received from each registered device.

## Run the tests

From the project root, with the virtual environment activated, run:

```bash
python -m pytest -v
```

The tests cover device registration, duplicate IDs, heartbeat handling, unknown devices, status calculation, the 30-second timeout, fleet summary, and invalid CPU usage.

## Assumptions

- A newly registered device is `OFFLINE` until its first heartbeat arrives.
- The 30-second timeout is measured from the time the backend receives a heartbeat.
- Device IDs must be unique.
- The simulator uses five predefined devices and a five-second heartbeat interval.
- Device records are kept in memory while the backend is running.

## Known limitations

- Device records are lost when the backend restarts.
- The in-memory store is intended for a single backend process and is not shared across multiple workers.
- The simulator and controller are intended for a local demonstration.
- Authentication and persistent storage are not included.
- The heartbeat timeout and local service addresses are fixed in the code rather than configurable through environment variables.

## What I would improve with one more day

- **Persistent storage:** Add SQLite or PostgreSQL so device records survive backend restarts.
- **Configuration:** Move the timeout, heartbeat interval, and service addresses into environment variables.
- **Device filtering:** Allow the API to return only `ONLINE` or `OFFLINE` devices.
- **Structured logging:** Record registrations, heartbeat failures, and status-related events in a consistent format.
- **Integration tests:** Test the full simulator workflow, including stopping a device, waiting for timeout, and restarting it.
- **Deployment:** Add Docker support to make setup more consistent across environments.

## AI Usage

**Tools used**

- **ChatGPT:** Used to discuss the architecture, work through implementation choices, iterate on the API, simulator, controller and tests, troubleshoot issues, and review test coverage and documentation.
- **Claude:** Used as a second reviewer to challenge the design and look for edge cases, including timezone handling, test isolation, concurrency, and gaps against the assignment requirements.

**A suggestion I changed or rejected**

AI initially suggested using a background worker to periodically update each device's status. For a simpler implementation, I chose a request-driven approach instead: whenever the API is queried, it compares the current time with the device's last heartbeat to determine whether it is `ONLINE` or `OFFLINE`. This avoids an extra thread, timers, and coordination between the status checker and heartbeat handler. A device that stops reporting will show as `OFFLINE` on the next API request after the 30-second timeout. The trade-off is that its status is calculated when requested rather than updated automatically at exactly the 30-second mark.

**What I personally verified**

- Ran the automated test suite and checked the results for device registration, duplicate IDs, heartbeat handling, input validation, fleet summary, and timeout behaviour.
- Checked that a newly registered device starts as `OFFLINE` and becomes `ONLINE` after receiving a heartbeat.
- Verified the 30-second timeout boundary using controlled time in the tests, rather than waiting in real time.
- Tested the simulator and controller together with five devices, including checking status and starting or stopping individual devices.
- Checked that stopping a simulator worker does not immediately mark a device offline; the API changes its status after the heartbeat timeout, and a subsequent heartbeat brings it back online.
- Checked API error handling for duplicate registrations, unknown devices, and invalid CPU usage.
- Reviewed the API responses and Swagger documentation against the implemented endpoints.

I reviewed the code I am submitting and can explain the design choices, trade-offs, and limitations of the implementation.
