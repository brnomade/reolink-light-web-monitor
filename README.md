# Reolink Camera Viewer — iOS 9 Safari Compatible

A lightweight, self-hosted camera wall that displays 4 Reolink IP cameras in a single webpage. Designed specifically to work on **old iPads running iOS 9 Safari**, with no JavaScript frameworks, no apps, and no cloud dependency.

---

## Overview

This solution bridges the gap between modern IP camera protocols (RTSP) and the very limited browser capabilities of iOS 9. It uses a small Python server running on a Linux machine on your local network to transcode camera streams into a format that even a decade-old iPad can render natively.

```
Reolink Cameras (RTSP)
        │
        ▼
  FFmpeg (per camera)
  Transcodes H.264 → MJPEG
        │
        ▼
  Python / Flask Server
  Serves MJPEG over HTTP
        │
        ▼
  iPad (iOS 9 Safari)
  4x <img> tags, no JS required
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
| MJPEG via `<img>` | ✓ Always worked | ✓ |

**MJPEG over HTTP via `<img>` tags** is the most compatible and simplest approach. It requires no JavaScript whatsoever — the browser simply streams a multipart JPEG response directly into an image element.

### Why Not Native HLS?

iOS Safari does support native HLS via `<video>` tags, but Reolink cameras expose RTSP, not HLS. Converting RTSP → HLS requires generating `.m3u8` playlists and `.ts` segment files with latency buffering. This is significantly more complex and introduces 5–15 seconds of delay. MJPEG is simpler, more immediate, and perfectly adequate for a surveillance viewer.

---

## Architecture

### Components

**Linux Server (application tier)**
- Python 3 + Flask — lightweight HTTP server
- FFmpeg — pulls RTSP from each camera, outputs MJPEG frames over a pipe
- One FFmpeg process per camera, running continuously
- Serves the HTML page at `/` and each stream at `/cam/camN`

**iPad (client)**
- Opens `http://SERVER_IP:5000` in Safari
- Receives a plain HTML page with 4 `<img>` tags
- Each `<img>` streams MJPEG continuously — no polling, no JavaScript

---

## Erorr Handling

### `index.html`

Deliberately old-school HTML — no JavaScript, no frameworks. Uses `-webkit-` prefixed flexbox for iOS 9 compatibility.

The `onerror` handler automatically retries a dropped stream after 3 seconds — the only JavaScript in the entire solution.

---

## FFmpeg Parameters Explained

| Parameter | Value | Purpose |
|---|---|---|
| `-rtsp_transport tcp` | tcp | More reliable than UDP on home networks |
| `-f mjpeg` | mjpeg | Output format — multipart JPEG |
| `-q:v` | 5 | JPEG quality (2=best, 31=worst). 5 is a good balance |
| `-vf scale=640:-1` | 640px wide | Resize — sufficient for a 50% viewport on iPad |
| `-r` | 8 | 8 frames per second — light on network and CPU |
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

Use the **sub stream** (`_sub`) for this viewer. It is designed for secondary viewers and uses significantly less bandwidth with no visible quality difference at this display size.

---

## Hardware Requirements

### Linux Server
Any always-on Linux machine on your local network. A Raspberry Pi 3B+ or better is sufficient. The application is lightweight — four MJPEG sub-streams at 8fps will use well under 10% CPU on any modern machine.

### iPad
Any iPad capable of running iOS 9. Tested on Safari — no app installation required.

### Cameras
Any Reolink camera with RTSP support. RTSP must be explicitly enabled via the Reolink app (see Installation guide).

---

## Project Structure

```
camera-viewer/

├──backend
    ├── server.py       # Flask application and FFmpeg stream manager
├──frontend
    ├── index.html      # Camera grid page (served by Flask)
├── README.md       # This file
├── INSTALLATION.md # Setup, port configuration, and debugging
└── FAQ.md          # Common questions on performance and longevity
```
