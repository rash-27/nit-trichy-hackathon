"""
============================================================
  BUS IoT SIMULATOR — Resilient Transport Tracking System
  NIT Hackathon | Track B | Problem Statement SIH 2025
============================================================

INSTALL (run once):
-------------------
  pip install paho-mqtt

STARTING THE SCRIPT:
--------------------
  python bus_script.py
  python bus_script.py --broker 192.168.1.10 --port 1883

SHELL COMMANDS (type after the >>> prompt):
-------------------------------------------
  add <bus_id> <csv_file>     Register and start a bus
      Example:  add bus1 route1.csv
                add bus2 routes/bus2.csv

  <bus_id> -t <seconds>       Put a bus into THROTTLE mode for N seconds.
      Example:  bus1 -t 30
      Behaviour: Collects GPS points every NORMAL_INTERVAL seconds.
                 At end of throttle period, sends ALL collected points
                 as one bundled MQTT message, then returns to NORMAL.

  <bus_id> -o <seconds>       Put a bus into OFFLINE mode for N seconds.
      Example:  bus1 -o 60
      Behaviour: Collects GPS points every NORMAL_INTERVAL seconds.
                 At end of offline period, sends ALL collected points
                 as one recovery MQTT message, then returns to NORMAL.
      Note:     If the bus was in THROTTLE when -o is issued, the
                throttle buffer is carried over into the offline buffer.

  list                        Show all active buses and their states.
  quit                        Stop all buses and exit.

GLOBAL SETTINGS (edit at the top of this file):
------------------------------------------------
  BROKER          = "localhost"   MQTT broker address
  PORT            = 1883          MQTT broker port
  TOPIC           = "buses/location"
  NORMAL_INTERVAL = 2             Seconds between GPS pings (all states)
  ROW_SPACING_M   = 10            Metres between consecutive CSV rows

CSV FORMAT (latitude and longitude only):
-----------------------------------------
  latitude,longitude
  20.2961,85.8245
  ...
  Every row must be exactly ROW_SPACING_M metres from the next.

SPEED / ACCELERATION:
---------------------
  Speed is simulated automatically with smooth random drift.
  No manual speed control needed — the bus drives itself.
  Bounds: SPEED_MIN_KMH to SPEED_MAX_KMH (configurable below).

MQTT PAYLOAD FORMATS:
---------------------
  NORMAL    : {"bus_id", "lat", "lng", "speed_kmh", "distance_m", "timestamp"}
  THROTTLE  : {"bus_id", "type":"throttle", "count":N, "data":[...N points...]}
  OFFLINE   : {"bus_id", "type":"recovery", "count":N, "data":[...N points...]}
============================================================
"""

import csv
import json
import os
import random
import sys
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

import os
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
BROKER = os.getenv("MQTT_BROKER")
PORT = int(os.getenv("MQTT_PORT", "8883"))
TOPIC = os.getenv("MQTT_TOPIC")
CSV_FILE = "location.csv"
USERNAME = os.getenv("MQTT_USERNAME")
PASSWORD = os.getenv("MQTT_PASSWORD")

# ══════════════════════════════════════════════════════════════════════════════
#  GLOBAL CONFIG  ← edit these to change defaults
# ══════════════════════════════════════════════════════════════════════════════
NORMAL_INTERVAL = 2       # seconds between GPS pings in every state
ROW_SPACING_M   = 10      # metres between consecutive CSV rows (fixed)

SPEED_MIN_KMH   = 15.0    # random speed floor
SPEED_MAX_KMH   = 60.0    # random speed ceiling
ACCEL_PER_TICK  = 4.0     # max speed change per tick (km/h)  ← random drift

# ══════════════════════════════════════════════════════════════════════════════
#  STATE LABELS
# ══════════════════════════════════════════════════════════════════════════════
NORMAL   = "NORMAL"
THROTTLE = "THROTTLE"
OFFLINE  = "OFFLINE"

# ══════════════════════════════════════════════════════════════════════════════
#  TERMINAL COLOURS
# ══════════════════════════════════════════════════════════════════════════════
C = {
    "g": "\033[92m", "y": "\033[93m", "r": "\033[91m",
    "c": "\033[96m", "b": "\033[1m",  "x": "\033[0m",
}
def clr(txt, col): return f"{C.get(col,'')}{txt}{C['x']}"


# ══════════════════════════════════════════════════════════════════════════════
#  CSV LOADER
# ══════════════════════════════════════════════════════════════════════════════
def load_csv(path: str) -> list:
    if not os.path.exists(path):
        print(clr(f"[ERROR] CSV not found: {path}", "r"))
        return None
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]
        for i, row in enumerate(reader):
            try:
                rows.append({
                    "lat": float(row["latitude"]),
                    "lng": float(row["longitude"]),
                })
            except (KeyError, ValueError):
                pass
    if not rows:
        print(clr(f"[ERROR] No valid rows in {path}", "r"))
        return None
    print(clr(f"  Loaded {len(rows)} rows  ≈ {(len(rows)-1)*ROW_SPACING_M/1000:.2f} km", "c"))
    return rows


# ══════════════════════════════════════════════════════════════════════════════
#  MQTT
# ══════════════════════════════════════════════════════════════════════════════
def make_client() -> mqtt.Client:
    import ssl
    client = mqtt.Client(client_id="bus_simulator_shell", clean_session=True)

    # TLS — required for HiveMQ Cloud (port 8883)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS)

    # Credentials — required for HiveMQ Cloud
    if USERNAME:
        client.username_pw_set(USERNAME, PASSWORD)
    else:
        print(clr("[WARN] USERNAME is empty — HiveMQ Cloud will reject the connection.", "y"))
        print(clr("       Set USERNAME and PASSWORD in the globals at the top of this file.", "y"))

    client.on_connect    = lambda c, u, f, rc: print(
        clr(f"[MQTT] Connected to {BROKER}:{PORT}", "g") if rc == 0
        else clr(f"[MQTT] Connect failed rc={rc} (wrong credentials or TLS issue?)", "r")
    )
    client.on_disconnect = lambda c, u, rc: print(clr(f"[MQTT] Disconnected rc={rc}", "y"))

    try:
        client.connect(BROKER, PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(clr(f"[MQTT] Could not connect: {e} — running without broker.", "y"))
    return client


def pub(client: mqtt.Client, payload: dict) -> bool:
    try:
        r = client.publish(TOPIC, json.dumps(payload), qos=1)
        return r.rc == mqtt.MQTT_ERR_SUCCESS
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  BUS  (one thread per bus)
# ══════════════════════════════════════════════════════════════════════════════
class Bus:
    def __init__(self, bus_id: str, rows: list, client: mqtt.Client):
        self.bus_id     = bus_id
        self.rows       = rows
        self.client     = client

        self.row_idx    = 0
        self.distance_m = 0.0
        self.speed_kmh  = random.uniform(SPEED_MIN_KMH, SPEED_MAX_KMH)

        # FSM
        self.state          = NORMAL
        self.state_duration = 0.0   # total seconds for current non-normal period
        self.state_elapsed  = 0.0   # seconds elapsed in this period
        self.buffer         = []    # collected points during THROTTLE / OFFLINE

        self.lock    = threading.Lock()
        self.running = True
        self.thread  = threading.Thread(target=self._loop, daemon=True, name=bus_id)
        self.thread.start()

    # ── physics helpers ───────────────────────────────────────────────────────
    def _drift_speed(self):
        """Smoothly random-walk the speed within [SPEED_MIN, SPEED_MAX]."""
        delta = random.uniform(-ACCEL_PER_TICK, ACCEL_PER_TICK)
        self.speed_kmh = max(SPEED_MIN_KMH, min(SPEED_MAX_KMH, self.speed_kmh + delta))

    def _advance(self):
        """Move row_idx forward based on current speed."""
        if self.speed_kmh <= 0:
            return
        dist = (self.speed_kmh / 3.6) * NORMAL_INTERVAL   # metres this tick
        step = max(1, round(dist / ROW_SPACING_M))
        self.distance_m += step * ROW_SPACING_M
        self.row_idx = (self.row_idx + step) % len(self.rows)

    def _point(self) -> dict:
        r = self.rows[self.row_idx % len(self.rows)]
        return {
            "bus_id":    self.bus_id,
            "lat":       r["lat"],
            "lng":       r["lng"],
            "speed_kmh": random.randint(35, 45),
            "timestamp": int(time.time()),
        }

    # ── state commands (called from shell thread) ─────────────────────────────
    def set_throttle(self, duration: float):
        with self.lock:
            # Fresh throttle — always start a new buffer
            self.buffer         = []
            self.state          = THROTTLE
            self.state_duration = duration
            self.state_elapsed  = 0.0
        self._info(f"→ THROTTLE for {duration}s", "y")

    def set_offline(self, duration: float):
        with self.lock:
            # If coming from THROTTLE, carry the buffer over (merge)
            if self.state != THROTTLE:
                self.buffer = []
            self.state          = OFFLINE
            self.state_duration = duration
            self.state_elapsed  = 0.0
        self._info(f"→ OFFLINE for {duration}s  (buffer kept: {len(self.buffer)} pts)", "r")

    # ── logging ───────────────────────────────────────────────────────────────
    def _info(self, msg: str, col: str = "c"):
        ts = datetime.now().strftime("%H:%M:%S")
        sc = {"NORMAL": "g", "THROTTLE": "y", "OFFLINE": "r"}.get(self.state, "c")
        tag = clr(f"[{self.bus_id}][{self.state:8s}]", sc)
        print(f"[{ts}] {tag} {clr(msg, col)}")

    # ── flush buffer ──────────────────────────────────────────────────────────
    def _flush(self, ended_state: str):
        n = len(self.buffer)
        if n == 0:
            return
        # Send the buffer as a plain JSON list of point dicts
        ok = pub(self.client, self.buffer)
        status = clr(f"✓ sent {n} pts", "g") if ok else clr(f"✗ failed ({n} pts lost)", "r")
        self._info(f"[FLUSH {ended_state}] {status}", "g" if ok else "r")
        self.buffer = []

    # ── main loop (runs in its own thread) ────────────────────────────────────
    def _loop(self):
        while self.running:
            with self.lock:
                state    = self.state
                duration = self.state_duration

            pt = self._point()

            if state == NORMAL:
                ok = pub(self.client, pt)
                self._info(
                    f"lat={pt['lat']:.5f} lng={pt['lng']:.5f} "
                    f"spd={pt['speed_kmh']} km/h  "
                    + (clr("✓", "g") if ok else clr("✗", "r"))
                )

            else:  # THROTTLE or OFFLINE — collect
                with self.lock:
                    self.buffer.append(pt)
                    self.state_elapsed += NORMAL_INTERVAL
                    elapsed = self.state_elapsed
                    ended   = elapsed >= duration

                self._info(
                    f"[{'T' if state==THROTTLE else 'O'} {elapsed:.0f}/{duration:.0f}s] "
                    f"buffered={len(self.buffer)}  "
                    f"lat={pt['lat']:.5f} lng={pt['lng']:.5f}"
                )

                if ended:
                    self._flush(state)
                    with self.lock:
                        self.state         = NORMAL
                        self.state_elapsed = 0.0
                        self.state_duration= 0.0
                    self._info("→ back to NORMAL", "g")

            self._drift_speed()
            self._advance()
            time.sleep(NORMAL_INTERVAL)

        self._info("Stopped.", "c")


# ══════════════════════════════════════════════════════════════════════════════
#  SHELL
# ══════════════════════════════════════════════════════════════════════════════
HELP = """
  add <id> <csv>   Start a bus  (e.g. add bus1 route.csv)
  <id> -t <secs>   Throttle mode for N seconds
  <id> -o <secs>   Offline mode  for N seconds
  list             Show all buses
  quit             Stop everything
"""

def shell(client: mqtt.Client):
    buses: dict[str, Bus] = {}

    print(clr("\n" + "═" * 50, "c"))
    print(clr("  BUS SIMULATOR SHELL  —  type 'help' for commands", "b"))
    print(clr("═" * 50 + "\n", "c"))

    while True:
        try:
            raw = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            raw = "quit"

        if not raw:
            continue

        parts = raw.split()
        cmd   = parts[0].lower()

        # ── help ──────────────────────────────────────────────────────────────
        if cmd == "help":
            print(HELP)

        # ── quit ──────────────────────────────────────────────────────────────
        elif cmd == "quit":
            print(clr("Stopping all buses...", "y"))
            for b in buses.values():
                b.running = False
            time.sleep(0.5)
            print(clr("Goodbye.", "c"))
            client.loop_stop()
            client.disconnect()
            sys.exit(0)

        # ── list ──────────────────────────────────────────────────────────────
        elif cmd == "list":
            if not buses:
                print("  No buses registered yet.")
            else:
                print(f"  {'ID':<10} {'STATE':<10} {'SPEED (km/h)':<15} {'DIST (m)':<12} {'BUF PTS'}")
                print("  " + "-" * 60)
                for bid, b in buses.items():
                    sc = {"NORMAL": "g", "THROTTLE": "y", "OFFLINE": "r"}.get(b.state, "c")
                    print(
                        f"  {clr(bid, 'b'):<10} {clr(b.state, sc):<10} "
                        f"{b.speed_kmh:<15.1f} {b.distance_m:<12.0f} {len(b.buffer)}"
                    )

        # ── add <id> <csv> ─────────────────────────────────────────────────────
        elif cmd == "add":
            if len(parts) != 3:
                print("  Usage: add <bus_id> <csv_file>")
                continue
            bid, csv_path = parts[1], parts[2]
            if bid in buses:
                print(clr(f"  Bus '{bid}' already running. Use 'list' to check.", "y"))
                continue
            rows = load_csv(csv_path)
            if rows is None:
                continue
            buses[bid] = Bus(bid, rows, client)
            print(clr(f"  Bus '{bid}' started  ({len(rows)} route points).", "g"))

        # ── <bus_id> -t <secs>  /  <bus_id> -o <secs> ────────────────────────
        elif len(parts) == 3 and parts[1] in ("-t", "-o"):
            bid, flag, val = parts[0], parts[1], parts[2]
            if bid not in buses:
                print(clr(f"  Unknown bus '{bid}'. Use 'add' first.", "r"))
                continue
            try:
                duration = float(val)
                if duration <= 0:
                    raise ValueError
            except ValueError:
                print("  Duration must be a positive number (seconds).")
                continue
            if flag == "-t":
                buses[bid].set_throttle(duration)
            else:
                buses[bid].set_offline(duration)

        else:
            print(clr(f"  Unknown command: '{raw}'.  Type 'help'.", "y"))


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Bus IoT Simulator Shell — HiveMQ Cloud")
    ap.add_argument("--broker",   default=BROKER,   help="MQTT broker hostname")
    ap.add_argument("--port",     default=PORT,     type=int, help="MQTT port (8883 for TLS)")
    ap.add_argument("--username", default=USERNAME, help="HiveMQ Cloud username")
    ap.add_argument("--password", default=PASSWORD, help="HiveMQ Cloud password")
    ns = ap.parse_args()

    BROKER   = ns.broker
    PORT     = ns.port
    USERNAME = ns.username
    PASSWORD = ns.password

    client = make_client()
    shell(client)
