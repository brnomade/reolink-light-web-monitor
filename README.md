# Reolink Camera Viewer - Version 2 — iOS 9 & Android Compatible

A lightweight, self-hosted camera wall that displays up to 4 Reolink IP cameras in a single webpage. Designed to work on **old iPads running iOS 9 Safari** and **Android tablets**, with no JavaScript frameworks, no apps, and no cloud dependency.

---

## Overview

This solution bridges the gap between modern IP camera protocols (RTSP) and the very limited browser capabilities of iOS 9. A small Python server running on a Linux machine on your local network handles all the heavy lifting — pulling RTSP streams, transcoding frames, and serving snapshots on demand. The browser simply polls for the latest JPEG image at a configured interval.

```
Reolink Cameras (RTSP)
        │
        ▼
  FFmpeg (one persistent process per camera)
  Decodes H.264 → stores latest JPEG frame in memory
        │
        ▼
  Python / Flask Server
  Serves latest JPEG snapshot on request
  Serves health status, config, and HTML page
        │
        ▼
  Browser (iOS 9 Safari / Android Chrome)
  Polls for new frames via JavaScript setInterval
  Displays 2×2 grid with status bar and camera labels
```

---

## Why This Approach

### The iOS 9 Safari Constraint

iOS 9 Safari is severely limited compared to modern browsers:

| Feature | iOS 9 Safari | Modern Browser |
|---|---|---|
| HLS.js | ✗ No ES6/fetch | ✓ |
| WebRTC | ✗ Not supported | ✓ |
| Media Source Extensions | ✗ Absent | ✓ |
| Native HLS (`<video>`) | ✓ Supported | ✓ |
| MJPEG via `<img>` | ✓ Works | ✓ |
| JPEG snapshot polling | ✓ Works | ✓ |

### Why Snapshot Polling Instead of MJPEG Streaming

The initial implementation used continuous MJPEG streams — one long-lived HTTP connection per camera. This caused two serious problems:

**Zombie FFmpeg processes.** Every time a browser disconnected or reconnected, a new FFmpeg process was spawned but the old one was never properly terminated. Over time hundreds of orphaned processes accumulated, each consuming memory at 0% CPU. In production this reached 150+ zombie processes before a reboot.

**Browser freezing.** Long-lived HTTP connections on iOS 9 caused the browser to freeze after 1–2 hours as memory accumulated with no release mechanism.

The snapshot polling design eliminates both problems. Each HTTP request is short-lived and self-contained. FFmpeg processes are started once at boot and never restarted in response to browser activity.

### Why Not Native HLS?

iOS Safari supports native HLS via `<video>` tags, but Reolink cameras expose RTSP not HLS. Converting RTSP → HLS requires generating `.m3u8` playlists and `.ts` segment files with latency buffering — significantly more complex and introduces 5–15 seconds of delay. JPEG snapshot polling is simpler, lower latency, and perfectly adequate for a surveillance viewer.

---

## Architecture

### Server Side

**Poller** — one persistent thread per camera, each running one FFmpeg process. FFmpeg connects to the camera via RTSP, continuously decodes incoming H.264 video, and writes the latest decoded JPEG frame into a shared memory dictionary. Only the most recent frame is kept — no history, no buffer queue, no disk writes.

**Flask** — serves the HTML page, per-camera JPEG snapshots, a JavaScript config file, and a plain-text health endpoint. Each snapshot request opens, delivers one JPEG, and closes immediately.

**Health reporter** — a background thread that logs a summary of all cameras every 60 seconds, including frame counts, last frame age, FFmpeg restart counts, and request metrics.

### Client Side

**Browser** — loads `index.html` which contains a 2×2 camera grid and a status bar. JavaScript polls each camera independently at its configured interval using `setInterval`. A hidden `Image()` object loads each new frame in the background before swapping it into the visible `<img>` tag, preventing flicker.

**Config** — per-camera polling intervals, active flags, and display names are served from the server via `/config.js`. This keeps all configuration in one place — the `.env` file.

### Process Count

Exactly one FFmpeg process per active camera, always. Started once at boot, never spawned in response to browser connections. Verify at any time:

```bash
ps aux | grep ffmpeg | grep -v grep | wc -l
```

---

## Configuration

All configuration lives in a `.env` file. No hardcoded values in the application code.

```ini
# ── Shared defaults ────────────────────────────────────────────────────────
DEFAULT_CAMERA_PORT=554
DEFAULT_CAMERA_STREAM=sub

# ── Camera 1 (WiFi doorbell) ───────────────────────────────────────────────
CAM1IP=192.168.1.14
CAM1USER=admin
CAM1PASS=yourpassword
CAM1NAME=Doorbell
CAM1FPS=2
CAM1POOL=500
CAM1ACTIVE=True

# ── Camera 2 (POE) ─────────────────────────────────────────────────────────
CAM2IP=192.168.1.171
CAM2USER=admin
CAM2PASS=yourpassword
CAM2NAME=Garden
CAM2FPS=5
CAM2POOL=200
CAM2ACTIVE=True

# ── Camera 3 (POE) ─────────────────────────────────────────────────────────
CAM3IP=192.168.1.153
CAM3USER=admin
CAM3PASS=yourpassword
CAM3NAME=Garage
CAM3FPS=5
CAM3POOL=200
CAM3ACTIVE=True

# ── Camera 4 (not installed) ───────────────────────────────────────────────
CAM4IP=192.168.1.0
CAM4USER=admin
CAM4PASS=admin
CAM4NAME=Driveway
CAM4FPS=5
CAM4POOL=200
CAM4ACTIVE=False
```

| Variable | Purpose |
|---|---|
| `CAM?IP` | Camera IP address |
| `CAM?USER` / `CAM?PASS` | RTSP credentials |
| `CAM?NAME` | Display name shown in browser |
| `CAM?FPS` | FFmpeg capture rate from camera |
| `CAM?POOL` | Browser polling interval in milliseconds |
| `CAM?ACTIVE` | `True` to enable, `False` to disable without removing config |

**Important:** `CAM?ACTIVE` must be read as a boolean in Python. The correct pattern is:

```python
"active": os.getenv("CAM1ACTIVE", "True").lower() == "true"
```

A plain `os.getenv("CAM1ACTIVE")` returns the string `"False"` which Python treats as truthy — the camera would still be polled.

---

## Per-Camera Settings

WiFi cameras and wired POE cameras have very different network characteristics and should be configured differently:

| Camera | Connection | FPS | Poll interval | Reason |
|---|---|---|---|---|
| Doorbell | WiFi | 2 | 500ms | High jitter — slower poll reduces reconnects |
| POE cameras | Wired | 5 | 200ms | Stable connection supports faster polling |

---

## Browser Features

### Status Bar

A thin bar across the top of the page shows:

- **Coloured dot + status text** — green (`server ok`) when all active cameras delivered a frame in the last 10 seconds, amber (`partial`) if some are working, red (`no signal`) if none are responding
- **Live clock** — updates every second; if this stops, JavaScript is frozen
- **Countdown to refresh** — counts down to the next automatic page reload

### Camera Labels

Each camera cell shows the configured display name and the time its last frame arrived. If a camera errors, it shows the error count.

### Inactive Cameras

Cameras with `CAM?ACTIVE=False` are handled entirely in the browser:
- The `<img>` element is removed from the DOM on page load — no broken image placeholder
- The cell shows a dark background with the camera name and "not installed"
- Inactive cameras are excluded from the health indicator calculation

### Automatic Page Reload

The page reloads itself every 5 minutes via `setTimeout`. This clears browser memory, which is particularly important on old iOS 9 hardware with limited RAM. The page also reloads when it becomes visible again after being suspended (e.g. screen lock), using the `webkitvisibilitychange` event.

---

## Health Endpoint

A plain-text health summary is available at:

```
http://SERVER_IP:5000/health
```

Example output:

```
cam1: frames=390 last_frame=0.2s ago [OK] restarts=1 requests=378 failed=0 last_client=192.168.1.200
cam2: frames=583 last_frame=0.4s ago [OK] restarts=0 requests=1726 failed=0 last_client=192.168.1.200
cam3: frames=580 last_frame=0.2s ago [OK] restarts=0 requests=1724 failed=0 last_client=192.168.1.200
cam4: inactive
```

---

## FFmpeg Parameters

| Parameter | Value | Purpose |
|---|---|---|
| `-rtsp_transport tcp` | tcp | More reliable than UDP on home networks |
| `-f image2pipe` | image2pipe | Pipe individual JPEG frames to stdout |
| `-vcodec mjpeg` | mjpeg | JPEG output codec |
| `-q:v` | 5 | JPEG quality (2=best, 31=worst) |
| `-vf scale` | per camera | Resize — 320px for WiFi doorbell, 640px for POE |
| `-r` | per camera | Frame rate — 2fps for WiFi, 5fps for POE |
| `pipe:1` | stdout | Streams output to Flask rather than a file |

---

## RTSP URL Format

Reolink cameras use one of these URL patterns depending on model and firmware:

```
# Main stream (higher quality, more bandwidth)
rtsp://admin:PASSWORD@CAMERA_IP:554/h264Preview_01_main

# Sub stream (recommended — lower bandwidth, sufficient for this viewer)
rtsp://admin:PASSWORD@CAMERA_IP:554/h264Preview_01_sub
```

Use the **sub stream** (`_sub`). It is designed for secondary viewers and uses significantly less bandwidth — typically 256–512 Kbps per camera versus 1–4 Mbps for the main stream.

---

## Hardware Requirements

### Linux Server

Any always-on Linux machine on your local network. An Intel i5 or equivalent is more than sufficient. CPU usage with three active sub-streams at the configured frame rates is typically under 10%.

### Viewing Device

Any device with a modern browser. Tested on:
- iPad running iOS 9.3.5 Safari
- Android tablet running Chrome

No app installation required on either device.

### Cameras

Any Reolink camera with RTSP support. RTSP must be explicitly enabled via the Reolink app — it is disabled by default on most models. See INSTALLATION.md for details.

---

## Process Management

The server is managed by PM2 for automatic restart on boot and crash recovery:

```bash
pm2 start backend/server.py --interpreter python3 --name security-monitor
pm2 save
pm2 startup
```

Run in fork mode (default) — cluster mode is not applicable for Python.

---

## Project Structure

```
reolink-light-web-monitor/
├── backend/
│   └── server.py        # Flask app, FFmpeg poller, health endpoint
├── frontend/
│   └── index.html       # Camera grid, status bar, polling logic
├── .env                 # All configuration — never commit this
├── README.md            # This file
├── INSTALLATION.md      # Setup, port configuration, and debugging
└── FAQ.md               # Common questions on performance and longevity
```