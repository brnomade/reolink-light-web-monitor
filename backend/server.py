from flask import Flask, Response
import subprocess
import threading
import os
import time
import signal
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

CAMERAS = {
    "cam1": {
        "url": "rtsp://" + os.getenv("CAM1USER") + ":" + os.getenv("CAM1PASS") + "@" + os.getenv("CAM1IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
        "fps": "2",
        "scale": "320:-1"
    },
    "cam2": {
        "url": "rtsp://" + os.getenv("CAM2USER") + ":" + os.getenv("CAM2PASS") + "@" + os.getenv("CAM2IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
        "fps": "5",
        "scale": "640:-1"
    },
    "cam3": {
        "url": "rtsp://" + os.getenv("CAM3USER") + ":" + os.getenv("CAM3PASS") + "@" + os.getenv("CAM3IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
        "fps": "5",
        "scale": "640:-1"
    },
    "cam4": {
        "url": "rtsp://" + os.getenv("CAM4USER") + ":" + os.getenv("CAM4PASS") + "@" + os.getenv("CAM4IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
        "fps": "5",
        "scale": "640:-1"
    },
}


class CameraStream:
    """Manages one persistent FFmpeg process per camera."""

    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        self.proc = None
        self.thread = threading.Thread(target=self._capture, daemon=True)
        self.thread.start()

    def _build_cmd(self):
        return [
            "ffmpeg",
            "-timeout", "10000000",
            "-rtsp_transport", "tcp",
            "-i", self.config["url"],
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-q:v", "5",
            "-vf", "scale=" + self.config["scale"],
            "-r", self.config["fps"],
            "pipe:1"
        ]

    def _capture(self):
        while self.running:
            self.proc = None
            try:
                self.proc = subprocess.Popen(
                    self._build_cmd(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
                buf = b""
                while self.running:
                    chunk = self.proc.stdout.read(4096)  # read in chunks not byte-by-byte
                    if not chunk:
                        break
                    buf += chunk
                    # extract all complete JPEG frames from buffer
                    while True:
                        start = buf.find(b"\xff\xd8")
                        end = buf.find(b"\xff\xd9")
                        if start == -1 or end == -1 or end < start:
                            break
                        frame = buf[start:end + 2]
                        with self.lock:
                            self.frame = frame
                        buf = buf[end + 2:]
            except Exception:
                pass
            finally:
                self._kill_proc()
            if self.running:
                time.sleep(2)  # wait before reconnecting

    def _kill_proc(self):
        if self.proc:
            try:
                self.proc.stdout.close()
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=2)
                except Exception:
                    pass
            self.proc = None

    def get_frame(self):
        with self.lock:
            return self.frame

    def stop(self):
        self.running = False
        self._kill_proc()


# Initialise one CameraStream per camera
streams = {name: CameraStream(name, config) for name, config in CAMERAS.items()}


def generate(camera_stream):
    """Yield frames to the browser client."""
    while True:
        frame = camera_stream.get_frame()
        if frame:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        time.sleep(0.1)


@app.route("/cam/<name>")
def stream(name):
    if name not in streams:
        return "Not found", 404
    return Response(
        generate(streams[name]),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.route("/")
def index():
    return open("frontend/index.html").read()


def shutdown(signum, frame):
    """Clean up all FFmpeg processes on exit."""
    for s in streams.values():
        s.stop()
    os._exit(0)


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)