from flask import Flask, Response
import subprocess
import threading
import os
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# =============================================================================
# CAMERA CONFIGURATION
# fps        = how often FFmpeg captures a new frame from the camera
# poll_ms    = how often the browser requests a new frame (milliseconds)
# scale      = output resolution
# =============================================================================
CAMERAS = {
    "cam1": {
        "url": "rtsp://" + os.getenv("CAM1USER") + ":" + os.getenv("CAM1PASS") + "@" + os.getenv("CAM1IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
        "fps": os.getenv("CAM1FPS"),
        "poll_ms": os.getenv("CAM1POOL"),     # WiFi doorbell — slower poll
        "scale": "320:-1"
    },
    "cam2": {
        "url": "rtsp://" + os.getenv("CAM2USER") + ":" + os.getenv("CAM2PASS") + "@" + os.getenv("CAM2IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
        "fps": os.getenv("CAM2FPS"),
        "poll_ms": os.getenv("CAM2POOL"),     # POE — faster poll
        "scale": "640:-1"
    },
    "cam3": {
        "url": "rtsp://" + os.getenv("CAM3USER") + ":" + os.getenv("CAM3PASS") + "@" + os.getenv("CAM3IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
        "fps": os.getenv("CAM3FPS"),
        "poll_ms": os.getenv("CAM3POOL"),     # POE — faster poll
        "scale": "640:-1"
    },
    "cam4": {
        "url": "rtsp://" + os.getenv("CAM4USER") + ":" + os.getenv("CAM4PASS") + "@" + os.getenv("CAM4IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
        "fps": os.getenv("CAM4FPS"),
        "poll_ms": os.getenv("CAM4POOL"),     # POE — faster poll
        "scale": "640:-1"
    },
}

# =============================================================================
# FRAME STORE
# One latest JPEG frame per camera. Poller writes, Flask reads.
# =============================================================================
latest_frames = {name: None for name in CAMERAS}
frame_locks = {name: threading.Lock() for name in CAMERAS}


# =============================================================================
# POLLER
# One persistent FFmpeg process per camera running in its own thread.
# Reads frames continuously and updates latest_frames in place.
# Never spawns additional processes — restarts the same one if it dies.
# =============================================================================
def poller(name, config):
    cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", config["url"],
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-q:v", "5",
        "-vf", "scale=" + config["scale"],
        "-r", config["fps"],
        "pipe:1"
    ]
    while True:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            buf = b""
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                buf += chunk
                start = buf.find(b"\xff\xd8")
                end = buf.find(b"\xff\xd9")
                if start != -1 and end != -1 and end > start:
                    frame = buf[start:end + 2]
                    with frame_locks[name]:
                        latest_frames[name] = frame
                    buf = buf[end + 2:]
        finally:
            proc.stdout.close()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        time.sleep(2)


# =============================================================================
# FLASK ROUTES
# /cam/<name>  — returns the latest JPEG snapshot for that camera
# /config.js   — serves per-camera poll intervals to the browser
# /            — serves the HTML page
# =============================================================================
@app.route("/cam/<name>")
def snapshot(name):
    if name not in CAMERAS:
        return "Not found", 404
    with frame_locks[name]:
        frame = latest_frames[name]
    if frame is None:
        return "No frame yet", 503
    return Response(frame, mimetype="image/jpeg")


@app.route("/config.js")
def config_js():
    """Expose per-camera poll intervals to the browser as a JS config object."""
    lines = ["var CAMERA_POLL_MS = {"]
    for name, config in CAMERAS.items():
        lines.append('  "{}": {},'.format(name, config["poll_ms"]))
    lines.append("};")
    return Response("\n".join(lines), mimetype="application/javascript")


@app.route("/")
def index():
    return open("frontend/index2.html").read()


# =============================================================================
# STARTUP — launch one poller thread per camera
# =============================================================================
for cam_name, cam_config in CAMERAS.items():
    t = threading.Thread(target=poller, args=(cam_name, cam_config), daemon=True)
    t.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)