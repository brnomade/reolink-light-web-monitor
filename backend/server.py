from flask import Flask, Response
import subprocess, threading
import os
from dotenv import load_dotenv
import time

load_dotenv()

app = Flask(__name__)

CAMERAS = {
    "cam1": "rtsp://" + os.getenv("CAM1USER") + ":" + os.getenv("CAM1PASS") + "@" + os.getenv("CAM1IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
    "cam2": "rtsp://" + os.getenv("CAM2USER") + ":" + os.getenv("CAM2PASS") + "@" + os.getenv("CAM2IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
    "cam3": "rtsp://" + os.getenv("CAM3USER") + ":" + os.getenv("CAM3PASS") + "@" + os.getenv("CAM3IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
    "cam4": "rtsp://" + os.getenv("CAM4USER") + ":" + os.getenv("CAM4PASS") + "@" + os.getenv("CAM4IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM")
}

# Shared latest frame per camera
latest_frames = {name: None for name in CAMERAS}
locks = {name: threading.Lock() for name in CAMERAS}


def capture_camera(name, rtsp_url):
    """One persistent thread per camera — keeps one FFmpeg process alive."""
    while True:
        cmd = [
            "ffmpeg", "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-f", "mjpeg",
            "-q:v", "5",
            "-vf", "scale=640:-1",
            "-r", "8",
            "pipe:1"
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            while True:
                buf = b""
                while True:
                    byte = proc.stdout.read(1)
                    if not byte:
                        raise StopIteration
                    buf += byte
                    if buf[-2:] == b"\xff\xd9":
                        break
                with locks[name]:
                    latest_frames[name] = buf
        except StopIteration:
            pass
        finally:
            proc.kill()
        time.sleep(2)  # pause before reconnecting



def generate_stream(name):
    """Serve the latest frame to a browser client."""
    while True:
        with locks[name]:
            frame = latest_frames[name]
        if frame:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        time.sleep(1)


@app.route("/cam/<name>")
def stream(name):
    if name not in CAMERAS:
        return "Not found", 404
    return Response(
        generate_stream(name),
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


# Start one capture thread per camera at startup
for cam_name, cam_url in CAMERAS.items():
    t = threading.Thread(target=capture_camera, args=(cam_name, cam_url), daemon=True)
    t.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
