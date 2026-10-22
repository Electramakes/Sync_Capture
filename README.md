# Sync_Capture

A small demo that takes **one photo with a phone camera and one photo with a laptop webcam at the same moment**, started with a single button press.

The phone needs **no app**. It only opens a web page in its normal browser. Everything runs on your own Wi-Fi, and nothing is uploaded to the internet.

---

## How it works

Two devices do not share a clock, so sending "take a photo now" over Wi-Fi would give a random delay each time. This demo avoids that in three steps:

1. **Clock sync.** The phone sends 40 quick pings to the laptop. For each one it measures the round-trip time and estimates the difference between the two clocks (the same idea as NTP). It keeps the ping with the **shortest** round trip, because that one is the most accurate.
2. **Scheduled trigger.** When you press the button, the laptop does not say "now". It says "capture at time T", where T is **3 seconds in the future**. Each device converts T to its own clock and waits for that moment.
3. **Cameras kept warm.** Both cameras are already running. At time T each device simply grabs its newest frame. Opening a camera at the last second would add hundreds of milliseconds.

```
Phone browser  <---- Wi-Fi ---->  Laptop (Python server + webcam)
 - shows camera preview            - serves the phone page
 - syncs its clock                 - owns the laptop webcam
 - captures at time T              - control page with live preview
 - uploads its photo               - captures at time T, saves everything
```

---

## What you need

- A laptop with a webcam, running **Windows** (Mac and Linux also work, see the notes in the commands)
- **Python 3** (tested with Python 3.14 and OpenCV 5.0)
- A phone with a normal browser (Chrome or Safari)
- The laptop and phone on the **same Wi-Fi network**

---

## Setup (first time only)

Open a terminal in the project folder. In VS Code: **File, Open Folder**, then **Terminal, New Terminal**.

**1. Create a virtual environment and activate it**

```
py -m venv .venv
.venv\Scripts\activate
```

> On Windows, `py` is the Python launcher. If `python` is not recognised, use `py`.
> On Mac or Linux: `python3 -m venv .venv` and `source .venv/bin/activate`.
> If PowerShell says scripts are disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.
> When it works, you will see `(.venv)` at the start of the line.

**2. Install the libraries**

```
pip install -r requirements.txt
```

**3. Create the HTTPS certificate**

Phone browsers only allow camera access on an HTTPS page, so the server needs a certificate. This script creates a self-signed one (`key.pem` and `cert.pem`). No extra tools are needed.

```
python make_cert.py
```

The certificate is valid for 30 days and includes your laptop's current Wi-Fi address. **If you change Wi-Fi network, run this command again.**

---

## Run it

```
python server.py
```

The terminal prints two addresses:

```
Phone   : open https://192.168.x.x:8000   (accept the certificate warning, tap Start)
Laptop  : open https://localhost:8000/control   (press the button)
```

**On the phone**

1. Open the first address.
2. The browser warns that the certificate is not trusted. This is expected because the certificate is self-signed. Choose **Advanced**, then **Continue / Proceed**.
3. Tap **Start camera + sync** and allow camera access.
4. Wait for the message `ready. best RTT ... ms, offset ... ms`.
5. Keep the screen on and the page open.

**On the laptop**

1. Open `https://localhost:8000/control` in your browser (a full browser such as Edge or Chrome works best).
2. You will see a **live preview of the laptop webcam** under the button.
3. Press **TAKE PHOTO (both devices)**.

Three seconds later both devices capture. To stop, click in the terminal and press **Ctrl + C**.

Windows may ask whether Python can use the network. Choose **Allow** (private networks), or the phone will not be able to connect.

---

## Where the results go

Everything is saved on the laptop in a folder called `captures`:

| File | Content |
|------|---------|
| `1_laptop.jpg`, `1_phone.jpg` | The photo pair of shot 1 (and `2_...` for shot 2, and so on) |
| `log.csv` | One row per photo with the scheduled time and the actual capture time |

`log.csv` columns: `shot_id`, `device`, `scheduled_T_ms`, `capture_ms`, `capture_minus_T_ms`.

> **Important:** the shot numbers start again at 1 every time the server restarts, so old photos with the same name are overwritten. Rename or move the `captures` folder between runs.

---

## Settings you can change

All settings are in `server.py`. After any change, **save the file (Ctrl + S), stop the server (Ctrl + C) and start it again**. The phone page is stored inside the Python file, so it also needs a restart.

**Delay before the shot** (default 3 seconds)

Near the top of the file:

```python
LEAD_MS = 3000   # capture is scheduled this far in the future
```

The value is in milliseconds, so `3000` is 3 seconds. Use `5000` for 5 seconds. Keep it at 1 second or more, so the phone has time to receive the message.

**Which phone camera** (rear or front)

Search for `facingMode` in `server.py`:

```javascript
facingMode: 'environment'   // rear camera
facingMode: 'user'          // front (selfie) camera
```

**Which laptop camera**

Search for `LaptopCam(0)`:

```python
cam = LaptopCam(0)   # 0 = first camera, try 1 if the wrong one opens
```

**Other settings**

- Phone camera resolution and frame rate: in the same `getUserMedia` line (`width: 1280, height: 720, frameRate: 30`).
- Number of clock-sync pings: the `syncClock(n = 40)` function.
- Port: `port=8000` at the bottom of the file.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| `python` is not found | Use `py` instead, or install Python and tick "Add python.exe to PATH" |
| Phone cannot open the page | Same Wi-Fi? Allow Python in the Windows firewall. Make sure the address starts with `https://` |
| Phone says the certificate is not trusted | Expected. Choose Advanced, then Continue. If the camera still does not open, create a trusted certificate with `mkcert` |
| Laptop preview is black or empty | Close other apps using the camera (Zoom, Teams, Windows Camera). Check Windows Settings, Privacy, Camera, "Let desktop apps access your camera". Try `LaptopCam(1)` |
| Laptop preview does not appear after an update | Save `server.py`, then restart the server |
| No phone photo for a shot | The phone page was not started yet, or the screen was locked. Tap Start and keep the screen on |
| Wrong phone camera | Change `facingMode` (see above) and restart |

---

## How to measure the sync error

1. Put the phone and the laptop side by side, both cameras pointing at a third screen that shows a **millisecond stopwatch** (a stopwatch website on a second monitor or tablet works well).
2. Take about 30 shots with the control button.
3. For each pair, read the stopwatch value in the phone photo and in the laptop photo. The difference is the sync error for that shot.
4. Report the **average** (a fixed offset caused by each camera's own delay) and the **spread** (the real jitter of the method).

---

## Results

Shot 1 is shown at the results file: both frames read **00:42.6x**. The last digit is smeared by the stopwatch screen refresh, so a single pair is only a first check, not a measurement.

Full test (fill in after the 30-shot measurement):

| Measure | Value |
|---------|-------|
| Number of shots | <30> |
| Average offset (phone minus laptop) | <__ ms> |
| Spread (standard deviation) | <__ ms> |
| Largest difference | <__ ms> |

---

## Limitations

- This is **software sync, not hardware sync**. There is no shared sync signal between the phone and the laptop, so the result cannot be frame-exact.
- Each camera has its own delay between the sensor and the frame the code receives. This shows up as a roughly constant offset between the devices.
- At 30 fps one frame lasts about 33 ms, so around plus or minus one frame is a realistic accuracy.
- Wi-Fi delay changes from moment to moment. The scheduled trigger and the best-round-trip clock sync reduce this, but do not remove it.
- Browsers can round their timers (Safari does this more strongly), which limits how well the phone clock can be estimated.
- Only one phone is supported at a time.

## Ideas for better synchronization

- A shared timecode or sync signal between the cameras
- A wired trigger, for example a microcontroller that fires all cameras at once
- Cameras with hardware sync (genlock)
- Marking the same event in all recordings (a flash or a clap) and aligning the videos afterwards
- A native phone app with access to exact capture timestamps
- Several phones at once

---

## Project files

```
server.py            Server, laptop camera, phone web page, control page
make_cert.py         Creates key.pem and cert.pem for HTTPS
requirements.txt     Python libraries
results/             Example photos and measurements
captures/            Created automatically when you take photos (not uploaded)
key.pem, cert.pem    Created by make_cert.py (never share or upload these)
```

## Technologies

Python, FastAPI and Uvicorn (server), OpenCV (laptop camera), browser `getUserMedia` and Canvas (phone camera), NTP-style clock offset estimation.
