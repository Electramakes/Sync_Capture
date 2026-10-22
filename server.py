"""Phone + laptop synchronized photo demo.

The laptop runs this server and owns the laptop webcam (OpenCV).
The phone only opens a web page in its browser (no app needed).

Idea: clock sync (NTP-style) + "capture at future time T" + cameras kept warm.

Run:  python server.py
"""
import csv
import os
import socket
import threading
import time

import cv2
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse

LEAD_MS = 3000   # capture is scheduled this far in the future
OUT = "captures"
os.makedirs(OUT, exist_ok=True)

app = FastAPI()
state = {"id": 0, "T": 0.0}
log_lock = threading.Lock()


def now_ms():
    return time.time() * 1000


def log(row):
    with log_lock:
        new = not os.path.exists(f"{OUT}/log.csv")
        with open(f"{OUT}/log.csv", "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["shot_id", "device", "scheduled_T_ms", "capture_ms", "capture_minus_T_ms"])
            w.writerow(row)


# ---------- laptop camera: keep it running, always hold the newest frame ----------
class LaptopCam:
    def __init__(self, index=0):
        # On Windows, CAP_DSHOW opens much faster
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.frame, self.t = None, 0.0
        self.lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            ok, f = self.cap.read()
            if ok:
                with self.lock:
                    self.frame, self.t = f, now_ms()
            else:
                time.sleep(0.05)

    def latest(self):
        with self.lock:
            return self.frame, self.t


cam = LaptopCam(0)


def laptop_capture(shot_id, T):
    while now_ms() < T - 15:      # coarse wait
        time.sleep(0.005)
    while now_ms() < T:           # fine wait (busy loop)
        pass
    t = now_ms()
    frame, _ = cam.latest()
    if frame is None:
        print("laptop camera gave no frame")
        return
    cv2.imwrite(f"{OUT}/{shot_id}_laptop.jpg", frame)
    log([shot_id, "laptop", round(T, 1), round(t, 1), round(t - T, 1)])
    print(f"shot {shot_id}: laptop captured {t - T:+.1f} ms from target")


# ---------- API ----------
@app.get("/ping")
def ping():
    return {"t": now_ms()}


@app.get("/poll")
def poll():
    return state


@app.post("/trigger")
def trigger():
    state["id"] += 1
    state["T"] = now_ms() + LEAD_MS
    threading.Thread(target=laptop_capture, args=(state["id"], state["T"]), daemon=True).start()
    return state


@app.post("/upload")
async def upload(request: Request):
    shot_id = int(request.headers["x-shot-id"])
    t_cap = float(request.headers["x-capture-time"])   # phone capture time, in laptop clock
    with open(f"{OUT}/{shot_id}_phone.jpg", "wb") as f:
        f.write(await request.body())
    T = state["T"]
    log([shot_id, "phone", round(T, 1), round(t_cap, 1), round(t_cap - T, 1)])
    print(f"shot {shot_id}: phone captured {t_cap - T:+.1f} ms from target")
    return {"ok": True}

@app.get("/stream")
def stream():
    def mjpeg():
        while True:
            frame, _ = cam.latest()
            if frame is not None:
                ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"
            time.sleep(0.05)
    return StreamingResponse(mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")

# ---------- pages ----------
PHONE_PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<body style="font-family:sans-serif;margin:12px">
<button id=go style="font-size:20px;padding:12px">Start camera + sync</button>
<p id=s>not started</p>
<video id=v autoplay playsinline muted style="width:100%"></video>
<canvas id=c style="display:none"></canvas>
<script>
const nowMs = () => performance.timeOrigin + performance.now();
const $ = id => document.getElementById(id);
let offset = 0, lastId = 0;   // offset = laptop clock - phone clock (ms)

async function syncClock(n = 40) {
  let best = null;
  for (let i = 0; i < n; i++) {
    const t0 = nowMs();
    const j = await (await fetch('/ping', {cache: 'no-store'})).json();
    const t1 = nowMs();
    const rtt = t1 - t0;
    // assume the reply was made halfway through the round trip
    if (!best || rtt < best.rtt) best = {rtt, off: j.t - (t0 + t1) / 2};
    await new Promise(r => setTimeout(r, 30));
  }
  offset = best.off;
  return best;
}

async function grab(id) {
  const tCap = nowMs() + offset;            // capture time expressed in laptop clock
  const v = $('v'), c = $('c');
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext('2d').drawImage(v, 0, 0);
  c.toBlob(async b => {
    await fetch('/upload', {method: 'POST', body: b,
      headers: {'X-Shot-Id': id, 'X-Capture-Time': tCap}});
    $('s').textContent = 'shot ' + id + ' uploaded';
  }, 'image/jpeg', 0.9);
}

function schedule(id, T) {
  const target = T - offset;                // target time in phone clock
  const wait = target - nowMs() - 30;
  if (wait < -30) return;                   // already passed
  setTimeout(() => { while (nowMs() < target) {} grab(id); }, Math.max(0, wait));
}

async function pollLoop() {
  while (true) {
    try {
      const st = await (await fetch('/poll', {cache: 'no-store'})).json();
      if (st.id > lastId) { lastId = st.id; schedule(st.id, st.T); }
    } catch (e) {}
    await new Promise(r => setTimeout(r, 150));
  }
}
// you could use environment for rear camera --- user for front camera in facing mode. 
$('go').onclick = async () => {
  const stream = await navigator.mediaDevices.getUserMedia(
    {video: {facingMode: 'user', width: 1280, height: 720, frameRate: 30}, audio: false});
  $('v').srcObject = stream;
  const b = await syncClock();
  $('s').textContent = 'ready. best RTT ' + b.rtt.toFixed(1) + ' ms, offset ' + b.off.toFixed(1) + ' ms';
  pollLoop();
};
</script></body>"""

CONTROL_PAGE = """<!doctype html><body style="font-family:sans-serif;margin:24px">
<button style="font-size:28px;padding:20px" onclick="fetch('/trigger',{method:'POST'})
 .then(r=>r.json()).then(j=>document.getElementById('o').textContent='triggered shot '+j.id)">
 TAKE PHOTO (both devices)</button><p id=o></p>
<img src="/stream" style="width:640px;max-width:100%"></body>"""


@app.get("/", response_class=HTMLResponse)
def phone():
    return PHONE_PAGE


@app.get("/control", response_class=HTMLResponse)
def control():
    return CONTROL_PAGE


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # no packet is sent; just finds the LAN address
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ip = lan_ip()
    print(f"Phone   : open https://{ip}:8000   (accept the certificate warning, tap Start)")
    print(f"Laptop  : open https://localhost:8000/control   (press the button)")
    uvicorn.run(app, host="0.0.0.0", port=8000, ssl_keyfile="key.pem",
                ssl_certfile="cert.pem", log_level="warning")
