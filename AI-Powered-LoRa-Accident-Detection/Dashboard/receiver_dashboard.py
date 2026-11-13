#!/usr/bin/env python3
"""
receiver_dashboard.py
---------------------
Live web page for your LoRa accident receiver. Your receiver sketch is NOT
changed: this program reads what it already prints over USB (the
"ACCIDENT ALERT RECEIVED" and "MPU SENSOR DATA" blocks) and shows it on a page.

Setup (once):
    pip install pyserial

Run:
    python receiver_dashboard.py --port COM5
    (no --port: it lists the ports and asks you to pick the RECEIVER's)

Then open   http://localhost:8000   in a browser.

IMPORTANT: close the Arduino Serial Monitor for the receiver first.
Only one program can use a COM port at a time.

Try it without any hardware:
    python receiver_dashboard.py --demo

Every alert is also saved to alerts_log.csv (handy for your test counts).
Show the page on a phone on the same WiFi:  add  --host 0.0.0.0  and open
http://<laptop-ip>:8000  on the phone.
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # only needed when not using --demo
    serial = None

LOG_FILE = "alerts_log.csv"
MAX_ALERTS = 100

LOCK = threading.Lock()
STATE = {
    "connected": False,
    "port": None,
    "last_packet_ts": None,   # when the last packet (any kind) arrived
    "mpu": None,              # latest MPU Data packet
    "alerts": [],             # newest first
    "alert_count": 0,
    "packet_count": 0,
}

# ----------------------------------------------------------------------
#  Parsing the receiver's serial text
# ----------------------------------------------------------------------
NUM = r"(-?\d+(?:\.\d+)?)"
RE_RSSI = re.compile(r"RSSI:\s*" + NUM + r"\s*dBm\s*\|\s*SNR:\s*" + NUM)
RE_LAT = re.compile(r"^LAT:\s*" + NUM)
RE_LON = re.compile(r"^LONG:\s*" + NUM)
RE_SPEED = re.compile(r"^SPEED \(km/h\):\s*" + NUM)
RE_ALT = re.compile(r"^ALT \(m\):\s*" + NUM)
RE_HDOP = re.compile(r"^HDOP:\s*" + NUM)
RE_SAT = re.compile(r"^Satellites:\s*(\d+)")
RE_UTC = re.compile(r"^UTC:\s*(.+)$")
RE_ACC = re.compile(r"Accel X:\s*" + NUM + r"\s*Y:\s*" + NUM + r"\s*Z:\s*" + NUM)
RE_GYR = re.compile(r"Gyro\s+X:\s*" + NUM + r"\s*Y:\s*" + NUM + r"\s*Z:\s*" + NUM)
RE_TEMP = re.compile(r"Temp:\s*" + NUM)


def build_record(kind, lines, rssi, snr):
    rec = {"kind": kind, "ts": time.time(), "rssi": rssi, "snr": snr}
    if kind == "mpu":
        for ln in lines:
            m = RE_ACC.search(ln)
            if m:
                rec["accel"] = [float(v) for v in m.groups()]
            m = RE_GYR.search(ln)
            if m:
                rec["gyro"] = [float(v) for v in m.groups()]
            m = RE_TEMP.search(ln)
            if m:
                rec["temp"] = float(m.group(1))
        return rec

    # accident alert
    first = lines[0] if lines else "Accident"
    rec["title"] = first[:60]
    rec["major"] = "major" in first.lower()
    rec["gps_fix"] = False
    for ln in lines:
        m = RE_LAT.match(ln)
        if m:
            rec["lat"] = float(m.group(1))
        m = RE_LON.match(ln)
        if m:
            rec["lon"] = float(m.group(1))
        m = RE_SPEED.match(ln)
        if m:
            rec["speed"] = float(m.group(1))
        m = RE_ALT.match(ln)
        if m:
            rec["alt"] = float(m.group(1))
        m = RE_HDOP.match(ln)
        if m:
            rec["hdop"] = float(m.group(1))
        m = RE_SAT.match(ln)
        if m:
            rec["sats"] = int(m.group(1))
        m = RE_UTC.match(ln)
        if m:
            rec["utc"] = m.group(1)[:30]
    if "lat" in rec and "lon" in rec:
        rec["gps_fix"] = True
    return rec


class ReceiverParser:
    """Turns the receiver's printed lines into records."""

    def __init__(self, on_record):
        self.on_record = on_record
        self.kind = None
        self.lines = []

    def feed(self, raw):
        line = raw.strip()
        if not line:
            return
        if "ACCIDENT ALERT RECEIVED" in line:
            self.kind, self.lines = "alert", []
            return
        if "MPU SENSOR DATA" in line:
            self.kind, self.lines = "mpu", []
            return
        if self.kind is None or set(line) == {"="}:
            return
        m = RE_RSSI.search(line)
        if m:
            rec = build_record(self.kind, self.lines, float(m.group(1)), float(m.group(2)))
            self.kind, self.lines = None, []
            self.on_record(rec)
            return
        self.lines.append(line)


def handle_record(rec):
    with LOCK:
        STATE["packet_count"] += 1
        STATE["last_packet_ts"] = rec["ts"]
        if rec["kind"] == "mpu":
            STATE["mpu"] = rec
        else:
            STATE["alert_count"] += 1
            STATE["alerts"].insert(0, rec)
            del STATE["alerts"][MAX_ALERTS:]
    if rec["kind"] == "alert":
        where = "%.6f, %.6f" % (rec["lat"], rec["lon"]) if rec["gps_fix"] else "no GPS fix"
        print("[ALERT] %s | %s | RSSI %s dBm" % (rec["title"], where, rec["rssi"]))
        log_alert(rec)
    else:
        print("[car] sensor packet received")


def log_alert(rec):
    new_file = not os.path.exists(LOG_FILE)
    try:
        with open(LOG_FILE, "a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["received_at", "type", "lat", "lon", "speed_kmh",
                            "satellites", "rssi_dbm", "snr"])
            w.writerow([datetime.fromtimestamp(rec["ts"]).strftime("%Y-%m-%d %H:%M:%S"),
                        "MAJOR" if rec["major"] else "ACCIDENT",
                        rec.get("lat", ""), rec.get("lon", ""), rec.get("speed", ""),
                        rec.get("sats", ""), rec["rssi"], rec["snr"]])
    except OSError as e:
        print("[log] could not write %s: %s" % (LOG_FILE, e))


# ----------------------------------------------------------------------
#  Serial reader and demo generator
# ----------------------------------------------------------------------
def set_connected(ok, port):
    with LOCK:
        STATE["connected"] = ok
        STATE["port"] = port


def serial_loop(port, baud):
    parser = ReceiverParser(handle_record)
    while True:
        try:
            with serial.Serial(port, baud, timeout=1) as ser:
                set_connected(True, port)
                print("[serial] connected to %s" % port)
                while True:
                    raw = ser.readline()
                    if raw:
                        parser.feed(raw.decode("utf-8", errors="ignore"))
        except Exception as e:  # unplugged, port busy, etc.
            set_connected(False, port)
            print("[serial] %s - retrying in 3 s (is the Arduino Serial Monitor closed?)" % e)
            time.sleep(3)


def demo_loop():
    """Feeds fake receiver output through the SAME parser, to try the page."""
    parser = ReceiverParser(handle_record)
    set_connected(True, "DEMO")
    n = 0
    while True:
        rssi = random.randint(-85, -60)
        block = [
            "", "=" * 40, "           MPU SENSOR DATA", "=" * 40, "MPU Data",
            "Accel X: %.2f Y: %.2f Z: %.2f m/s2" % (random.uniform(-0.2, 0.2), random.uniform(0.4, 0.8), random.uniform(9.5, 9.8)),
            "Gyro  X: 0.04 Y: 0.00 Z: -0.03 rad/s", "Temp: 30.5 C",
            "RSSI: %d dBm   |   SNR: 9.75" % rssi, "=" * 40,
        ]
        for ln in block:
            parser.feed(ln)
        time.sleep(2)
        if n % 2 == 0:                      # an alert every other round (~16 s)
            k = n // 2
            lat = 12.9716 + random.uniform(-0.002, 0.002)
            lon = 77.5946 + random.uniform(-0.002, 0.002)
            fix = (k % 3 != 2)              # every third alert has no GPS fix
            major = (k % 3 == 1)            # every third alert is "Major accident"
            block = ["", "=" * 40, "        ACCIDENT ALERT RECEIVED", "=" * 40,
                     "Major accident" if major else "Accident is Detected"]
            if fix:
                block += ["LAT: %.6f" % lat, "LONG: %.6f" % lon, "SPEED (km/h): 0.00",
                          "ALT (m): 910.30", "HDOP: 1.20", "Satellites: 7",
                          "UTC: 2026/10/9,7:30:12",
                          "Maps: https://www.google.com/maps?q=%.6f,%.6f" % (lat, lon)]
            else:
                block += ["No GPS Fix yet"]
            block += ["RSSI: %d dBm   |   SNR: 9.50" % rssi, "=" * 40]
            for ln in block:
                parser.feed(ln)
        n += 1
        time.sleep(6)


# ----------------------------------------------------------------------
#  Web server
# ----------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body, ctype = PAGE.encode("utf-8"), "text/html; charset=utf-8"
        elif self.path.startswith("/api/data"):
            with LOCK:
                payload = dict(STATE)
                payload["alerts"] = list(STATE["alerts"])
            payload["now"] = time.time()
            body, ctype = json.dumps(payload).encode("utf-8"), "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # keep the console quiet


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Accident Alert Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  :root { --bg:#f4f6f8; --card:#ffffff; --text:#1c2733; --muted:#5d6b7a; --line:#e1e6eb;
          --ok:#1f8a4c; --okbg:#e6f5ec; --bad:#c62828; --badbg:#fdeaea; --warn:#b26a00; --warnbg:#fff3df; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
         background:var(--bg); color:var(--text); }
  header { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;
           padding:14px 20px; background:var(--card); border-bottom:1px solid var(--line); }
  h1 { font-size:18px; margin:0; }
  .chips { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  .chip { font-size:13px; padding:5px 10px; border-radius:999px; border:1px solid var(--line); }
  .chip.ok { background:var(--okbg); color:var(--ok); border-color:#bfe3cd; }
  .chip.bad { background:var(--badbg); color:var(--bad); border-color:#f2c0c0; }
  button { font:inherit; font-size:13px; padding:5px 10px; border-radius:8px; border:1px solid var(--line);
           background:var(--card); color:var(--text); cursor:pointer; }
  main { max-width:1100px; margin:0 auto; padding:16px; }
  .banner { border-radius:12px; padding:18px 20px; margin-bottom:16px; }
  .banner h2 { margin:0 0 4px; font-size:24px; }
  .banner p { margin:0; font-size:15px; }
  .banner.ok { background:var(--okbg); color:var(--ok); }
  .banner.warn { background:var(--warnbg); color:var(--warn); }
  .banner.danger { background:var(--bad); color:#fff; animation:pulse 1s infinite alternate; }
  @keyframes pulse { from { opacity:1; } to { opacity:.78; } }
  .grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:16px; margin-bottom:16px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
  .card h3 { margin:0 0 10px; font-size:15px; }
  .row { display:flex; justify-content:space-between; gap:12px; padding:5px 0; border-bottom:1px solid var(--line); font-size:14px; }
  .row:last-child { border-bottom:none; }
  .row span:first-child { color:var(--muted); }
  #map { height:300px; border-radius:8px; background:#e9eef2; }
  .note { font-size:13px; color:var(--muted); margin-top:8px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th, td { text-align:left; padding:8px 6px; border-bottom:1px solid var(--line); }
  th { color:var(--muted); font-weight:600; font-size:13px; }
  .tablewrap { overflow-x:auto; }
  a { color:#1b5fb4; }
</style>
</head>
<body>
<header>
  <h1>Accident Alert Dashboard</h1>
  <div class="chips">
    <span id="chipSerial" class="chip bad">Receiver: ...</span>
    <span id="chipCar" class="chip bad">Car link: ...</span>
    <button id="soundBtn">Enable alert sound</button>
  </div>
</header>
<main>
  <div id="banner" class="banner ok">
    <h2 id="bannerTitle">Waiting for data...</h2>
    <p id="bannerSub"></p>
  </div>

  <div class="grid">
    <div class="card">
      <h3>Accident location</h3>
      <div id="map"></div>
      <div id="mapnote" class="note"></div>
    </div>
    <div class="card">
      <h3>Latest alert</h3>
      <div id="alertRows"></div>
    </div>
    <div class="card">
      <h3>Live car sensor data</h3>
      <div id="mpuRows"></div>
      <div class="note">The car sends this about every 10 seconds.</div>
    </div>
  </div>

  <div class="card">
    <h3>Alert history</h3>
    <div class="tablewrap">
      <table>
        <thead><tr><th>Time</th><th>Type</th><th>Location</th><th>Speed</th><th>Satellites</th><th>Signal</th><th>Map</th></tr></thead>
        <tbody id="history"></tbody>
      </table>
    </div>
    <div id="emptyHist" class="note">No alerts yet.</div>
  </div>
</main>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const $ = id => document.getElementById(id);
let map = null, marker = null, soundOn = false, audioCtx = null;
let lastCount = null, shownAlertTs = null;

function initMap() {
  if (!window.L) { $('mapnote').textContent = 'The map needs internet. Coordinates are shown in the alert details.'; return; }
  map = L.map('map').setView([20.59, 78.96], 4);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
}

function mapsUrl(lat, lon) { return 'https://www.google.com/maps?q=' + lat + ',' + lon; }
function fmtTime(ts) { return new Date(ts * 1000).toLocaleTimeString(); }
function ago(sec) {
  sec = Math.max(0, Math.round(sec));
  if (sec < 60) return sec + ' s';
  if (sec < 3600) return Math.floor(sec / 60) + ' min';
  return Math.floor(sec / 3600) + ' h';
}
function setChip(id, ok, text) { const e = $(id); e.className = 'chip ' + (ok ? 'ok' : 'bad'); e.textContent = text; }

// rows are built with textContent so nothing from the radio is ever run as HTML
function setRows(id, rows) {
  const box = $(id); box.textContent = '';
  rows.forEach(r => {
    const d = document.createElement('div'); d.className = 'row';
    const a = document.createElement('span'); a.textContent = r[0];
    const b = document.createElement('span'); b.textContent = r[1];
    d.appendChild(a); d.appendChild(b); box.appendChild(d);
  });
}
function linkCell(lat, lon) {
  const a = document.createElement('a');
  a.href = mapsUrl(lat, lon); a.target = '_blank'; a.rel = 'noopener'; a.textContent = 'Open';
  return a;
}
function beep() {
  if (!soundOn) return;
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.connect(g); g.connect(audioCtx.destination);
    o.frequency.value = 880; g.gain.value = 0.2;
    o.start(); setTimeout(() => o.stop(), 700);
  } catch (e) {}
}
$('soundBtn').onclick = () => {
  soundOn = !soundOn;
  $('soundBtn').textContent = soundOn ? 'Alert sound: ON' : 'Enable alert sound';
  if (soundOn) beep();
};

function render(d) {
  const now = d.now;
  setChip('chipSerial', d.connected, d.connected ? 'Receiver connected (' + d.port + ')' : 'Receiver not connected');
  const age = d.last_packet_ts ? now - d.last_packet_ts : null;
  const online = age !== null && age < 25;
  setChip('chipCar', online, online ? 'Car link online' : (age === null ? 'No car packets yet' : 'Car link lost (' + ago(age) + ')'));

  const a = d.alerts[0];
  const b = $('banner');
  if (!a) {
    b.className = 'banner ok';
    $('bannerTitle').textContent = 'No accident reported';
    $('bannerSub').textContent = online ? 'Monitoring the car. Last packet ' + ago(age) + ' ago.' : 'Waiting for the car...';
  } else {
    const s = now - a.ts, active = s < 300;
    b.className = 'banner ' + (active ? 'danger' : 'warn');
    $('bannerTitle').textContent = (active ? '' : 'Last alert: ') + (a.major ? 'MAJOR ACCIDENT' : 'ACCIDENT DETECTED');
    $('bannerSub').textContent = fmtTime(a.ts) + ' (' + ago(s) + ' ago)' + (a.gps_fix ? '' : ' - no GPS fix, location unknown');
  }

  if (a) {
    const rows = [['Received', fmtTime(a.ts)], ['Type', a.major ? 'Major accident' : 'Accident detected']];
    if (a.gps_fix) {
      rows.push(['Latitude', a.lat.toFixed(6)], ['Longitude', a.lon.toFixed(6)]);
      if (a.speed !== undefined) rows.push(['Speed', a.speed.toFixed(1) + ' km/h']);
      if (a.alt !== undefined) rows.push(['Altitude', a.alt.toFixed(1) + ' m']);
      if (a.sats !== undefined) rows.push(['Satellites', String(a.sats)]);
      if (a.utc) rows.push(['GPS time (UTC)', a.utc]);
    } else { rows.push(['Location', 'No GPS fix']); }
    rows.push(['Signal', a.rssi + ' dBm / SNR ' + a.snr]);
    setRows('alertRows', rows);
  } else { setRows('alertRows', [['Status', 'No alerts received']]); }

  if (a && a.gps_fix && map && shownAlertTs !== a.ts) {
    shownAlertTs = a.ts;
    const pos = [a.lat, a.lon];
    if (marker) marker.setLatLng(pos); else marker = L.marker(pos).addTo(map);
    map.setView(pos, 17);
    $('mapnote').textContent = '';
  } else if (a && !a.gps_fix && map) {
    $('mapnote').textContent = 'The latest alert has no GPS fix (GPS needs open sky).';
  }

  if (d.mpu) {
    const m = d.mpu, f = v => v.toFixed(2);
    const rows = [];
    if (m.accel) rows.push(['Accel X / Y / Z', m.accel.map(f).join(' / ') + ' m/s2']);
    if (m.gyro) rows.push(['Gyro X / Y / Z', m.gyro.map(f).join(' / ') + ' rad/s']);
    if (m.temp !== undefined) rows.push(['Temperature', m.temp.toFixed(1) + ' C']);
    rows.push(['Updated', ago(now - m.ts) + ' ago'], ['Signal', m.rssi + ' dBm / SNR ' + m.snr]);
    setRows('mpuRows', rows);
  } else { setRows('mpuRows', [['Status', 'No sensor packet yet']]); }

  const tb = $('history'); tb.textContent = '';
  d.alerts.forEach(x => {
    const tr = document.createElement('tr');
    const cells = [fmtTime(x.ts), x.major ? 'Major' : 'Accident',
      x.gps_fix ? x.lat.toFixed(5) + ', ' + x.lon.toFixed(5) : 'No GPS fix',
      x.speed !== undefined ? x.speed.toFixed(1) + ' km/h' : '-',
      x.sats !== undefined ? String(x.sats) : '-', x.rssi + ' dBm'];
    cells.forEach(t => { const td = document.createElement('td'); td.textContent = t; tr.appendChild(td); });
    const td = document.createElement('td');
    if (x.gps_fix) td.appendChild(linkCell(x.lat, x.lon)); else td.textContent = '-';
    tr.appendChild(td); tb.appendChild(tr);
  });
  $('emptyHist').style.display = d.alerts.length ? 'none' : 'block';

  if (lastCount !== null && d.alert_count > lastCount) { beep(); }
  lastCount = d.alert_count;
  document.title = (a && now - a.ts < 300) ? 'ALERT - Accident Dashboard' : 'Accident Alert Dashboard';
}

async function poll() {
  try {
    const r = await fetch('/api/data', { cache: 'no-store' });
    render(await r.json());
  } catch (e) {
    setChip('chipSerial', false, 'Dashboard server not reachable');
  }
}
initMap();
poll();
setInterval(poll, 1000);
</script>
</body>
</html>
"""


# ----------------------------------------------------------------------
def choose_port():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports found. Plug in the receiver and try again.")
        sys.exit(1)
    print("Serial ports found:")
    for i, p in enumerate(ports):
        print("  [%d] %s  -  %s" % (i, p.device, p.description))
    pick = input("Type the number of the RECEIVER's port: ").strip()
    try:
        return ports[int(pick)].device
    except (ValueError, IndexError):
        print("Not a valid choice.")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Live web page for the LoRa accident receiver")
    ap.add_argument("--port", help="receiver COM port, e.g. COM5 or /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to open it from a phone on the same WiFi")
    ap.add_argument("--http-port", type=int, default=8000)
    ap.add_argument("--demo", action="store_true", help="fake data, no hardware needed")
    args = ap.parse_args()

    if args.demo:
        threading.Thread(target=demo_loop, daemon=True).start()
    else:
        if serial is None:
            print("pyserial is not installed. Run:  pip install pyserial")
            sys.exit(1)
        port = args.port or choose_port()
        threading.Thread(target=serial_loop, args=(port, args.baud), daemon=True).start()

    server = ThreadingHTTPServer((args.host, args.http_port), Handler)
    print("Dashboard running:  http://localhost:%d   (press Ctrl+C to stop)" % args.http_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
