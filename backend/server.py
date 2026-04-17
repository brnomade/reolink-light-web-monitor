from flask import Flask, Response
import subprocess, threading
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

CAMERAS = {
    "cam1": "rtsp://" + os.getenv("CAM1USER") + ":" + os.getenv("CAM1PASS") + "@" + os.getenv("CAM1IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
    "cam2": "rtsp://" + os.getenv("CAM2USER") + ":" + os.getenv("CAM2PASS") + "@" + os.getenv("CAM2IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
    "cam3": "rtsp://" + os.getenv("CAM3USER") + ":" + os.getenv("CAM3PASS") + "@" + os.getenv("CAM3IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM"),
    "cam4": "rtsp://" + os.getenv("CAM4USER") + ":" + os.getenv("CAM4PASS") + "@" + os.getenv("CAM4IP") + ":" + os.getenv("DEFAULT_CAMERA_PORT") + "/h264Preview_01_" + os.getenv("DEFAULT_CAMERA_STREAM")
}

def mjpeg_stream(rtsp_url):
    cmd = [
        "ffmpeg", "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-f", "mjpeg",        # output format
        "-q:v", "5",          # quality (2=best, 31=worst)
        "-vf", "scale=640:-1",# resize to 640px wide
        "-r", "5",            # 8fps — light on the iPad
        "pipe:1"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            # JPEG starts with FFD8, ends with FFD9
            buf = b""
            while True:
                byte = proc.stdout.read(1)
                if not byte:
                    return
                buf += byte
                if buf[-2:] == b"\xff\xd9":
                    break
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + buf + b"\r\n")
    finally:
        proc.kill()

@app.route("/cam/<name>")
def stream(name):
    if name not in CAMERAS:
        return "Not found", 404
    return Response(
        mjpeg_stream(CAMERAS[name]),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route("/")
def index():
    return open("frontend/index.html").read()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)