# Frequently Asked Questions

---

## Performance & Network

### Will running this 24/7 affect my network?

It depends on which stream you use.

**Main stream** (`h264Preview_01_main`) is the full-quality feed, typically **1–4 Mbps per camera**. Four cameras running continuously could use **4–16 Mbps** of sustained LAN bandwidth. On a modern home network (100Mbps+) this is manageable but noticeable.

**Sub stream** (`h264Preview_01_sub`) is the recommended choice for this viewer. It is designed specifically for secondary displays and typically uses only **256–512 Kbps per camera** — roughly **1–2 Mbps total** for all four cameras. At the display size used in the 2×2 grid on an iPad, the quality difference is negligible.

To switch to sub streams, change `_main` to `_sub` in the `CAMERAS` dictionary in `server.py`:

```python
"cam1": "rtsp://admin:password@192.168.1.14:554/h264Preview_01_sub",
```

---

### How much CPU will the Linux server use?

FFmpeg is doing the heavy lifting — it decodes H.264 from RTSP and re-encodes as MJPEG. For four sub-streams at 8fps and 640px wide, expect:

- **Raspberry Pi 3B+:** ~40–60% CPU (acceptable, monitor with `htop`)
- **Raspberry Pi 4:** ~10–20% CPU
- **Any modern x86 Linux machine:** under 10% CPU

You can reduce CPU further by lowering the frame rate in `server.py`:

```python
"-r", "5",  # Drop from 8fps to 5fps
```

5fps is still perfectly smooth for a surveillance viewer.

---

### Will this saturate my WiFi if the cameras are wireless?

Each camera streams its RTSP feed to your Linux server, and the server streams MJPEG to the iPad. This means traffic flows:

```
Camera → (WiFi or wired) → Linux Server → (WiFi) → iPad
```

If both the cameras and the iPad are on WiFi, you are effectively using your wireless bandwidth twice per stream. Using sub-streams keeps this to well under 5 Mbps total, which any 2.4GHz or 5GHz WiFi network handles easily.

If cameras are on wired ethernet and only the iPad is on WiFi, the camera-to-server leg is off the wireless network entirely, reducing WiFi load significantly.

---

## Camera Longevity & Health

### Does continuous RTSP streaming wear out the cameras?

No. Reolink cameras (and IP cameras in general) are designed for always-on operation. The hardware encoder inside the camera runs continuously regardless of whether anything is consuming the stream — it is encoding and buffering video constantly. Opening an RTSP connection simply starts delivering that already-encoded data to a client. The camera is not doing additional work because you are watching it.

---

### Will the cameras run hotter because of this?

Marginally, but not meaningfully. Active RTSP connections add a small amount of network stack and buffer activity on the camera's processor. In practice this is negligible compared to the continuous work the camera is already doing — encoding video, running motion detection, and managing its own firmware.

Reolink cameras are designed for outdoor and indoor continuous use and are rated to operate at temperatures well above anything a home environment would produce. Heat is not a concern under normal deployment conditions.

If you have cameras installed in a sealed enclosure with no airflow in a hot environment (e.g., a south-facing attic in summer), ensure the enclosure is ventilated — but that applies regardless of whether you are streaming.

---

### Should I use the main stream or sub stream to reduce wear?

There is no meaningful difference in hardware wear between the two. The camera encodes both streams simultaneously at all times — it does not start or stop encoding based on whether a client is connected. Use the sub stream purely for network and CPU efficiency, not for any concern about camera longevity.

---

## Reliability & Maintenance

### What happens if a camera drops off the network?

FFmpeg will detect the broken RTSP connection and the stream process will exit. The `<img>` tag in the HTML page will trigger its `onerror` handler, which retries the stream after 3 seconds:

```html
<img src="/cam/cam1" onerror="setTimeout(function(){this.src='/cam/cam1?t='+Date.now()},3000)">
```

The camera cell will briefly go black, then automatically reconnect when the camera is reachable again. No manual refresh is needed.

---

### What happens if the Linux server reboots?

If you have configured the systemd service (see INSTALLATION.md), the camera viewer will start automatically after boot once the network is available. The `After=network.target` directive in the service file ensures this ordering.

---

### Can I view the cameras from outside my home network?

Not with this setup as-is. The Flask server listens on your local network only. To access remotely you would need to either:

- Set up a **VPN** (e.g., WireGuard) into your home network — the recommended approach as it keeps the cameras off the public internet
- Configure **port forwarding** on your router — not recommended as it exposes your camera streams publicly

This is out of scope for this project, but a WireGuard setup is straightforward on most Linux servers.

---

### Can this run on a microcontroller like an M5Stack AtomS3 Lite?

No. The AtomS3 Lite is an ESP32-S3 microcontroller — it has no operating system, no pip, no subprocess support, and no way to run FFmpeg. It has roughly 512KB of usable RAM. Transcoding even a single RTSP stream to MJPEG requires a full Linux environment with several hundred megabytes of headroom.

The AtomS3 Lite is well suited to edge tasks — sensor reading, Modbus/RS485 communication, ESPHome integrations — but not to serving application logic. Use any always-on Linux machine on your network for the application tier.
