from flask import Flask, Response, request
import subprocess
import threading
import os
import time
import logging
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# LOGGING SETUP
# Writes to both console and a rotating log file.
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("camera_monitor.log")
    ]
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# =============================================================================
# CAMERA CONFIGURATION
# fps      = frames per second FFmpeg captures from camera
# poll_ms  = how often browser requests a new frame (milliseconds)
# scale    = output resolution
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
    #"cam4": {
    #    "url": "rtsp://" + os.getenv("CAM4USER") + ":" + os.getenv("CAM4PASS") + "@" + os.getenv("CAM4IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
    #    "fps": os.getenv("CAM4FPS"),
    #    "poll_ms": os.getenv("CAM4POOL"),     # POE — faster poll
    #    "scale": "640:-1"
    #},
}

# =============================================================================
# FRAME STORE
# One latest JPEG frame per camera plus health metrics.
# =============================================================================
latest_frames = {name: None for name in CAMERAS}
frame_locks = {name: threading.Lock() for name in CAMERAS}

# Health metrics per camera
health = {
    name: {
        "frames_captured": 0,
        "last_frame_at": None,
        "ffmpeg_restarts": 0,
        "last_restart_at": None,
    }
    for name in CAMERAS
}
health_lock = threading.Lock()


# =============================================================================
# POLLER
# One persistent FFmpeg process per camera.
# Logs restarts, frame captures, and stalls.
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

    log.info("[%s] Poller starting", name)

    while True:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        log.info("[%s] FFmpeg process started (pid=%d)", name, proc.pid)

        try:
            buf = b""
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    log.warning("[%s] FFmpeg stdout closed — camera dropped or process died", name)
                    break
                buf += chunk
                start = buf.find(b"\xff\xd8")
                end = buf.find(b"\xff\xd9")
                if start != -1 and end != -1 and end > start:
                    frame = buf[start:end + 2]
                    with frame_locks[name]:
                        latest_frames[name] = frame
                    with health_lock:
                        health[name]["frames_captured"] += 1
                        health[name]["last_frame_at"] = time.time()
                    buf = buf[end + 2:]
        finally:
            proc.stdout.close()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            log.warning("[%s] FFmpeg process ended (pid=%d)", name, proc.pid)
            with health_lock:
                health[name]["ffmpeg_restarts"] += 1
                health[name]["last_restart_at"] = time.time()

        time.sleep(2)


# =============================================================================
# HEALTH REPORTER
# Logs a summary of all cameras every 60 seconds.
# =============================================================================
def health_reporter():
    while True:
        time.sleep(60)
        with health_lock:
            log.info("=== HEALTH REPORT ===")
            for name, h in health.items():
                last_frame = "never"
                if h["last_frame_at"]:
                    age = time.time() - h["last_frame_at"]
                    last_frame = "{:.1f}s ago".format(age)
                last_restart = "never"
                if h["last_restart_at"]:
                    age = time.time() - h["last_restart_at"]
                    last_restart = "{:.1f}s ago".format(age)
                log.info(
                    "[%s] frames=%d last_frame=%s restarts=%d last_restart=%s",
                    name,
                    h["frames_captured"],
                    last_frame,
                    h["ffmpeg_restarts"],
                    last_restart
                )
            log.info("=====================")


# =============================================================================
# REQUEST METRICS
# Tracks per-camera request counts and last request time per client IP.
# =============================================================================
request_metrics = {
    name: {
        "total_requests": 0,
        "failed_requests": 0,
        "last_client": None,
        "last_request_at": None,
    }
    for name in CAMERAS
}
metrics_lock = threading.Lock()


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

    client_ip = request.remote_addr
    start = time.time()

    with frame_locks[name]:
        frame = latest_frames[name]

    elapsed = (time.time() - start) * 1000

    with metrics_lock:
        request_metrics[name]["total_requests"] += 1
        request_metrics[name]["last_client"] = client_ip
        request_metrics[name]["last_request_at"] = time.time()

    if frame is None:
        with metrics_lock:
            request_metrics[name]["failed_requests"] += 1
        log.warning("[%s] No frame available for client %s", name, client_ip)
        return "No frame yet", 503

    log.debug("[%s] Served frame to %s in %.1fms (%d bytes)", name, client_ip, elapsed, len(frame))
    return Response(frame, mimetype="image/jpeg")


@app.route("/health")
def health_endpoint():
    """Human-readable health summary accessible from any browser on the network."""
    lines = []
    with health_lock:
        for name, h in health.items():
            last_frame = "never"
            stale = False
            if h["last_frame_at"]:
                age = time.time() - h["last_frame_at"]
                last_frame = "{:.1f}s ago".format(age)
                stale = age > 30
            with metrics_lock:
                m = request_metrics[name]
            lines.append(
                "{name}: frames={frames} last_frame={last_frame} {stale} "
                "restarts={restarts} requests={reqs} failed={failed} last_client={client}".format(
                    name=name,
                    frames=h["frames_captured"],
                    last_frame=last_frame,
                    stale="[STALE]" if stale else "[OK]",
                    restarts=h["ffmpeg_restarts"],
                    reqs=m["total_requests"],
                    failed=m["failed_requests"],
                    client=m["last_client"] or "none"
                )
            )
    return Response("\n".join(lines), mimetype="text/plain")


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
# STARTUP
# =============================================================================
for cam_name, cam_config in CAMERAS.items():
    t = threading.Thread(target=poller, args=(cam_name, cam_config), daemon=True)
    t.start()

t = threading.Thread(target=health_reporter, daemon=True)
t.start()

log.info("Camera monitor started with %d cameras", len(CAMERAS))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)