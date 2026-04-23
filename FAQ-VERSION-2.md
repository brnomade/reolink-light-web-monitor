# Frequently Asked Questions

---

## Architecture

### How does the camera viewer work?

The system has two distinct parts that operate independently:

**The poller** runs on the Linux server. It starts one persistent FFmpeg process per camera at boot. Each FFmpeg process connects to its camera via RTSP, continuously decodes incoming video, and writes the latest decoded JPEG frame into a shared memory dictionary. Only the most recent frame is kept — there is no frame history, no buffer queue, and no disk writes.

**The Flask web server** runs alongside the poller. When a browser requests a camera image, Flask reads the latest frame from the shared dictionary and returns it as a single JPEG response. The HTTP connection opens, delivers one image, and closes immediately.

The browser polls for new frames repeatedly using a JavaScript `setInterval` timer, creating the appearance of live video.

```
FFmpeg (cam1) ──┐
FFmpeg (cam2) ──┤──► shared frame dict ──► Flask ──► browser (polling)
FFmpeg (cam3) ──┤
FFmpeg (cam4) ──┘
```

---

### Why was the design changed from MJPEG streaming to snapshot polling?

The original design served each camera as a continuous MJPEG stream — one long-lived HTTP connection per camera that never closed. This caused two serious problems:

**Zombie FFmpeg processes.** Every time a browser disconnected or reconnected (due to a page refresh, the watchdog timer firing, or the browser being closed), a new FFmpeg process was spawned but the old one was never properly terminated. Over time hundreds of orphaned FFmpeg processes accumulated, each consuming memory even at 0% CPU.

**No control over connections.** With persistent streams, the server had no clean way to know when a browser had gone away. Processes leaked because Flask's generator cleanup was unreliable when clients disconnected abruptly.

The snapshot polling design eliminates both problems entirely. Each HTTP request is short-lived and self-contained. Browser disconnections are irrelevant — the poller keeps running regardless, and Flask simply stops receiving requests.

---

### How many FFmpeg processes run at any given time?

Exactly one per configured camera, always. They are started once when the server boots and run continuously. They are never spawned in response to browser connections or disconnections. If a process dies (e.g. the camera goes offline), it is restarted automatically after a 2 second pause — still one process per camera.

You can verify this at any time:

```bash
ps aux | grep ffmpeg | grep -v grep | wc -l
```

This should always return the number of cameras you have configured.

---

### What is `/config.js` and why does it exist?

`/config.js` is a small JavaScript file served dynamically by Flask. It contains the per-camera polling intervals defined in `server.py`:

```javascript
var CAMERA_POLL_MS = {
  "cam1": 500,
  "cam2": 200,
  "cam3": 200,
  "cam4": 200,
};
```

This allows the HTML page to read polling configuration from the server rather than having it hardcoded in two separate places. To change a camera's polling frequency, you edit the `poll_ms` value in `server.py` only — the browser picks it up automatically on next page load.

---

## Performance & Network

### Will running this 24/7 affect my network?

It depends on which stream you use.

**Main stream** (`h264Preview_01_main`) is the full-quality feed, typically 1–4 Mbps per camera. Four cameras running continuously could use 4–16 Mbps of sustained LAN bandwidth.

**Sub stream** (`h264Preview_01_sub`) is the recommended choice. It is designed specifically for secondary displays and typically uses only 256–512 Kbps per camera — roughly 1–2 Mbps total for all four cameras. At the display size used in the 2×2 grid on an iPad the quality difference is negligible.

To switch to sub streams, set `DEFAULT_CAMERA_STREAM=sub` in your `.env` file.

---

### How does the polling frequency affect network usage?

The poller and the browser poll independently and at different rates.

**FFmpeg (server side)** captures frames from the camera at the rate set by the `fps` value in `CAMERAS`. This is the rate at which RTSP data flows from the camera to the server — it runs regardless of whether any browser is connected.

**The browser** requests frames from Flask at the rate set by `poll_ms`. This is the rate at which data flows from the server to the iPad. If no browser is open, no data flows on this leg at all.

The two rates are intentionally decoupled. The poller always keeps the latest frame ready; the browser consumes it as fast or as slowly as it likes.

| Camera | FFmpeg capture | Browser poll | Connection type |
|---|---|---|---|
| cam1 doorbell | 2 fps | every 500ms | WiFi |
| cam2 | 5 fps | every 200ms | Wired POE |
| cam3 | 5 fps | every 200ms | Wired POE |
| cam4 | 5 fps | every 200ms | Wired POE |

---

### Why does the doorbell camera poll less frequently than the POE cameras?

The doorbell connects over WiFi which has significantly higher latency and jitter than a wired POE connection. Running it at 5fps and polling every 200ms would cause frequent request timeouts and reconnections as the WiFi connection struggles to keep up.

At 2fps and 500ms polling the doorbell is asked to deliver far less data per second, making it much more tolerant of the variable latency that WiFi introduces. For a doorbell this is entirely acceptable — you are watching for people approaching a door, not monitoring fast-moving activity.

---

### How much CPU will the Linux server use?

FFmpeg is doing the heavy lifting — it decodes H.264 from RTSP and re-encodes as JPEG. For four sub-streams at the configured frame rates, expect:

- **Raspberry Pi 4:** 15–25% CPU
- **Any modern x86 Linux machine (i5 or better):** under 10% CPU

You can monitor in real time with:

```bash
htop
```

---

## Camera Longevity & Health

### Does continuous RTSP streaming wear out the cameras?

No. Reolink cameras are designed for always-on operation. The hardware encoder inside the camera runs continuously regardless of whether anything is consuming the stream. Opening an RTSP connection simply starts delivering already-encoded data to a client. The camera does no additional work because you are watching it.

---

### Will the cameras run hotter because of this?

Marginally, but not meaningfully. Active RTSP connections add a small amount of network and buffer activity. This is negligible compared to the continuous work the camera is already doing — encoding video, running motion detection, and managing firmware. Reolink cameras are rated for continuous outdoor and indoor operation well above normal home temperatures.

---

## Reliability & Maintenance

### What happens if a camera goes offline?

The FFmpeg process for that camera will detect the broken RTSP connection and exit. The poller's outer `while True` loop catches this, waits 2 seconds, and restarts the same FFmpeg process. The browser will briefly receive a 503 response for that camera (no frame available) and continue polling. When the camera comes back online the poller reconnects automatically and frames resume. No manual intervention is needed.

---

### What happens if the Linux server reboots?

If you have configured the systemd service (see INSTALLATION.md), the camera viewer starts automatically after boot once the network is available. The `After=network.target` directive ensures the network is up before the server starts.

---

### Why does the page reload every 10 minutes?

The `<meta http-equiv="refresh" content="600">` tag in `index.html` causes the browser to reload the full page every 10 minutes. This is a precaution for old hardware — iOS 9 on an older iPad has limited RAM and browsers on constrained devices can accumulate memory over long sessions. A periodic reload clears all browser memory and restarts the polling timers cleanly. The number 600 is seconds — adjust it to taste.

---

### Can this run on a microcontroller like an M5Stack AtomS3 Lite?

No. The AtomS3 Lite is an ESP32-S3 microcontroller with no operating system, no pip, no subprocess support, and no ability to run FFmpeg. It has roughly 512KB of usable RAM. Transcoding even a single RTSP stream requires a full Linux environment with several hundred megabytes of headroom. Use any always-on Linux machine on your network for the application tier.

---

### Can I view the cameras from outside my home network?

Not with this setup as-is. The Flask server listens on your local network only. To access remotely the recommended approach is to set up a VPN (e.g. WireGuard) into your home network — this keeps the cameras off the public internet entirely. Configuring port forwarding on your router is not recommended as it exposes your camera streams publicly.
