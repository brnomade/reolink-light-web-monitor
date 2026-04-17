# Installation & Debugging Guide

This guide covers everything needed to get the camera viewer running from scratch, including all port configuration, firewall setup, and diagnostic commands used during development.

---

## Prerequisites

### On your Linux server

```bash
# Python and pip
sudo apt update
sudo apt install python3 python3-pip

# FFmpeg
sudo apt install ffmpeg

# Flask
pip3 install flask

# Optional but useful for diagnostics
sudo apt install nmap netcat-openbsd
```

### On your Reolink cameras

RTSP must be enabled manually. By default, many Reolink cameras ship with RTSP disabled.

**Via the Reolink app:**
1. Open the Reolink app and select a camera
2. Go to **Settings (gear icon) → Network → Advanced**
3. Find **Port Settings**
4. Enable **RTSP** — confirm port is set to **554**
5. Save and repeat for each camera

**Via the camera web interface:**
1. Open `http://CAMERA_IP:9000` in a browser
2. Log in with your admin credentials
3. Navigate to **Settings → Network → Advanced → Port Settings**
4. Enable RTSP on port 554

---

## Step 1: Find Your Camera IPs

If you don't know your camera IP addresses, scan your network:

```bash
# Ping sweep — lists all responding devices
nmap -sn 192.168.1.0/24
```

Or use arp-scan for a more reliable layer-2 scan:

```bash
sudo apt install arp-scan
sudo arp-scan --localnet
```

Alternatively, check your **router's DHCP lease table** — Reolink cameras usually appear with their model name. Most routers expose this at `http://192.168.1.1` or `http://192.168.0.1`.

---

## Step 2: Verify Camera Connectivity

### Ping each camera

```bash
ping 192.168.1.14
ping 192.168.1.171
ping 192.168.1.153
```

Expected output on a healthy wired or WiFi connection:

```
64 bytes from 192.168.1.14: icmp_seq=1 ttl=64 time=1.2 ms
64 bytes from 192.168.1.14: icmp_seq=2 ttl=64 time=1.1 ms
```

> **Warning:** High packet loss (>5%) or high latency (>10ms) on a local network indicates a connectivity problem — weak WiFi signal, bad cable, or overloaded switch. Fix this before proceeding. RTSP streams will be unreliable on a flaky connection.

### Check RTSP port is open

```bash
nc -zv 192.168.1.14 554
nc -zv 192.168.1.171 554
nc -zv 192.168.1.153 554
```

Expected output:

```
Connection to 192.168.1.14 554 port [tcp/rtsp] succeeded!
```

If you see `Connection refused`, RTSP is not enabled on that camera — go back to the Reolink app and enable it.

### Scan what ports a camera is exposing

If you're unsure whether RTSP is enabled or on a non-standard port:

```bash
nmap -p 1-10000 192.168.1.14
```

Common Reolink ports:

| Port | Service |
|---|---|
| 554 | RTSP (standard) |
| 9000 | Reolink proprietary HTTP API |
| 80 | Web interface (some models) |
| 443 | HTTPS (some models) |
| 8554 | RTSP alternate (some models) |
| 9554 | RTSP alternate (some models) |

---

## Step 3: Test FFmpeg Directly

Before running the Flask server, confirm FFmpeg can pull a single frame from each camera. Replace `yourpassword` with your admin password.

```bash
ffmpeg -rtsp_transport tcp \
  -i "rtsp://admin:yourpassword@192.168.1.14:554/h264Preview_01_sub" \
  -f mjpeg -q:v 5 -vf scale=640:-1 -r 8 -frames:v 1 \
  /tmp/test_cam1.jpg
```

Then verify the output is a valid JPEG:

```bash
ls -lh /tmp/test_cam1.jpg
file /tmp/test_cam1.jpg
```

Expected:

```
-rw-r--r-- 1 user user 42K Apr 17 12:00 /tmp/test_cam1.jpg
/tmp/test_cam1.jpg: JPEG image data, ...
```

Repeat for each camera IP.

### If FFmpeg fails — enable verbose output

Remove stderr suppression to see error detail. In `server.py`, temporarily change:

```python
# From:
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

# To:
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
```

This will print FFmpeg's full output to your terminal when the server runs.

### Common FFmpeg errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `Connection refused` | RTSP not enabled or wrong port | Enable RTSP in Reolink app |
| `401 Unauthorized` | Wrong credentials | Check username/password in CAMERAS dict |
| `No route to host` | Camera unreachable | Check ping, fix network |
| `Invalid data found` | Wrong URL path | Try `_main` vs `_sub`, or check model RTSP URL |
| Stream hangs silently | UDP transport issue | Ensure `-rtsp_transport tcp` is in the command |

### RTSP URL variants by Reolink model

```bash
# Standard (most models)
rtsp://admin:PASSWORD@IP:554/h264Preview_01_main
rtsp://admin:PASSWORD@IP:554/h264Preview_01_sub

# Some newer firmware
rtsp://admin:PASSWORD@IP:554/Preview_01_main

# Query string format (some models)
rtsp://IP:554/h264Preview_01_main?username=admin&password=PASSWORD
```

---

## Step 4: Configure and Run the Server

Edit `server.py` and update the `CAMERAS` dictionary with your real IPs and password:

```python
CAMERAS = {
    "cam1": "rtsp://admin:yourpassword@192.168.1.14:554/h264Preview_01_sub",
    "cam2": "rtsp://admin:yourpassword@192.168.1.171:554/h264Preview_01_sub",
    "cam3": "rtsp://admin:yourpassword@192.168.1.153:554/h264Preview_01_sub",
    "cam4": "rtsp://admin:yourpassword@192.168.1.XXX:554/h264Preview_01_sub",
}
```

Start the server:

```bash
python3 server.py
```

You should see:

```
* Running on http://0.0.0.0:5000
```

> **Important:** It must say `0.0.0.0`, not `127.0.0.1`. If it says `127.0.0.1`, the server is only accessible locally and the iPad won't be able to reach it.

---

## Step 5: Open the Linux Firewall

If UFW (Uncomplicated Firewall) is active on your server, port 5000 must be opened:

```bash
# Check firewall status
sudo ufw status

# Open port 5000
sudo ufw allow 5000

# Reload firewall rules
sudo ufw reload
```

Verify the rule was added:

```bash
sudo ufw status | grep 5000
```

---

## Step 6: Test From Desktop Browser First

Before trying the iPad, confirm the streams work from a desktop browser on the same network.

Find your server's local IP:

```bash
ip a | grep "inet " | grep -v 127
```

Look for the `192.168.x.x` address. Then open in a browser:

```
http://192.168.1.YOUR_SERVER_IP:5000
```

- The page should load with 4 camera cells
- Each cell should show a live image within a few seconds
- You can also test individual streams directly: `http://192.168.1.YOUR_SERVER_IP:5000/cam/cam1`

---

## Step 7: Access From the iPad

Open Safari on the iPad and navigate to:

```
http://192.168.1.YOUR_SERVER_IP:5000
```

**Tip — add to home screen:** Tap the Share button in Safari → **Add to Home Screen**. This creates a fullscreen shortcut icon that launches the camera view directly without browser chrome.

---

## Step 8: Run as a Systemd Service (Auto-start on Boot)

To have the camera viewer start automatically whenever your Linux server boots:

```bash
sudo nano /etc/systemd/system/cameras.service
```

Paste the following — update the path and username:

```ini
[Unit]
Description=Reolink Camera Viewer
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/YOUR_USER/camera-viewer/server.py
WorkingDirectory=/home/YOUR_USER/camera-viewer
Restart=always
RestartSec=5
User=YOUR_USER

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cameras
sudo systemctl start cameras

# Check it's running
sudo systemctl status cameras
```

View live logs:

```bash
journalctl -u cameras -f
```

---

## Diagnostic Quick Reference

| Problem | Command | Expected Result |
|---|---|---|
| Can't ping camera | `ping CAMERA_IP` | `time=<5ms`, no loss |
| RTSP port closed | `nc -zv CAMERA_IP 554` | `succeeded!` |
| Find open ports | `nmap -p 1-10000 CAMERA_IP` | Port 554 listed |
| Test single frame | `ffmpeg -rtsp_transport tcp -i "rtsp://..." -frames:v 1 /tmp/test.jpg` | Valid JPEG created |
| Find server IP | `ip a \| grep "inet "` | `192.168.x.x` |
| Firewall status | `sudo ufw status` | Port 5000 allowed |
| Test stream locally | `curl http://localhost:5000/cam/cam1` | Binary MJPEG data |
| Service status | `sudo systemctl status cameras` | `active (running)` |
