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

# ── Speed physics — per day-of-week profiles ─────────────────────────────────
DAY_PROFILES = {
    0: {"day": "Monday",    "speed_min": 2.5, "speed_max": 4.5, "accel": 0.25, "decel": 0.60},
    1: {"day": "Tuesday",   "speed_min": 3.0, "speed_max": 5.0, "accel": 0.30, "decel": 0.55},
    2: {"day": "Wednesday", "speed_min": 3.0, "speed_max": 5.0, "accel": 0.30, "decel": 0.50},
    3: {"day": "Thursday",  "speed_min": 3.0, "speed_max": 5.0, "accel": 0.30, "decel": 0.55},
    4: {"day": "Friday",    "speed_min": 2.0, "speed_max": 4.0, "accel": 0.20, "decel": 0.70},
    5: {"day": "Saturday",  "speed_min": 4.0, "speed_max": 6.0, "accel": 0.40, "decel": 0.45},
    6: {"day": "Sunday",    "speed_min": 4.5, "speed_max": 6.5, "accel": 0.50, "decel": 0.40},
}

# ── Stop behaviour ────────────────────────────────────────────────────────────
STOP_COORDINATES = [
    {"name": "Lanka Gate",          "lat": 25.277768, "lng": 83.002231},
    {"name": "Stop - 1",            "lat": 25.263755, "lng": 82.997520},
    {"name": "Hyderabad Gate",      "lat": 25.262927, "lng": 82.981793},
    {"name": "Rajeev Nagar Colony", "lat": 25.275039, "lng": 82.984572},
]
STOP_DURATION    = 300     # seconds to wait at each intermediate stop (5 min)
STOP_APPROACH_M  = 50      # metres ahead of a stop to start braking
PROXIMITY_M      = 15      # metres — "at stop" threshold

# ── Round-trip restart ────────────────────────────────────────────────────────
RESTART_INTERVAL = 7200    # 2-hour cycle between departure times (seconds)

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
        self.dist_rem      = 0.0   # sub-row remainder accumulator (metres)

        # Physics — start at minimum speed
        self.speed_ms      = 2.5 / 3.6  # Default start speed (Monday min)
        self.speed_kmh     = 2.5

        # Stop tracking
        self.at_stop       = False
        self.last_stop_name = None

        # Round-trip timing
        self.route_start_time = time.time()

        # FSM
        self.state          = NORMAL
        self.state_duration = 0.0   # total seconds for current non-normal period
        self.state_elapsed  = 0.0   # seconds elapsed in this period
        self.buffer         = []    # collected points during THROTTLE / OFFLINE

        self.lock    = threading.Lock()
        self.running = True
        self.thread  = threading.Thread(target=self._loop, daemon=True, name=bus_id)
        self.thread.start()

    # ── geometry ──────────────────────────────────────────────────────────────
    def _dist_m(self, lat1, lng1, lat2, lng2) -> float:
        """Flat-earth distance in metres (accurate enough for <5 km)."""
        dlat = (lat2 - lat1) * 111320
        dlng = (lng2 - lng1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
        return math.sqrt(dlat**2 + dlng**2)

    def _nearest_stop(self) -> tuple:
        """Return (distance_m, stop_dict) for the closest stop."""
        curr = self.rows[self.row_idx % len(self.rows)]
        best_d, best_s = float("inf"), None
        for stop in STOP_COORDINATES:
            d = self._dist_m(curr["lat"], curr["lng"], stop["lat"], stop["lng"])
            if d < best_d:
                best_d, best_s = d, stop
        return best_d, best_s

    # ── physics helpers ───────────────────────────────────────────────────────
    @staticmethod
    def _day_profile() -> dict:
        """Return the speed/accel profile for the current day of the week."""
        return DAY_PROFILES[datetime.now().weekday()]

    def _update_speed(self, dist_to_stop: float):
        """Accelerate toward cruise or decelerate toward stop, using today's profile."""
        profile   = self._day_profile()
        cruise_ms = profile["speed_max"] / 3.6
        min_ms    = profile["speed_min"] / 3.6
        accel     = profile["accel"]
        decel     = profile["decel"]
        dt        = NORMAL_INTERVAL

        if dist_to_stop <= STOP_APPROACH_M:
            ratio  = max(0.0, (dist_to_stop - PROXIMITY_M) / (STOP_APPROACH_M - PROXIMITY_M))
            target = cruise_ms * ratio
        else:
            target = cruise_ms + random.uniform(-0.05, 0.05) * (cruise_ms - min_ms)
            target = max(min_ms, min(cruise_ms, target))

        if self.speed_ms < target:
            self.speed_ms = min(target, self.speed_ms + accel * dt)
        else:
            self.speed_ms = max(0.0, max(target, self.speed_ms - decel * dt))
        
        self.speed_kmh = self.speed_ms * 3.6

    def _advance(self) -> bool:
        """Move row_idx forward based on current speed. Returns True if route wrapped."""
        dist = self.speed_ms * NORMAL_INTERVAL
        self.dist_rem   += dist
        self.distance_m += dist

        steps = int(self.dist_rem / ROW_SPACING_M)
        self.dist_rem -= steps * ROW_SPACING_M

        self.row_idx += steps
        if self.row_idx >= len(self.rows):
            self.row_idx = self.row_idx % len(self.rows)
            return True        # route complete
        return False

    def _point(self, status="Running 1") -> dict:
        r       = self.rows[self.row_idx % len(self.rows)]
        profile = self._day_profile()
        return {
            "bus_id":      self.bus_id,
            "lat":         r["lat"],
            "lng":         r["lng"],
            "speed_kmh":   round(self.speed_kmh, 2),
            "status":      status,
            "day_of_week": profile["day"],
            "timestamp":   int(time.time()),
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

            # ── proximity check ──────────────────────────────────────────────
            dist_to_stop, nearest_stop = self._nearest_stop()
            self._update_speed(dist_to_stop)

            if (dist_to_stop < PROXIMITY_M
                    and not self.at_stop
                    and nearest_stop["name"] != self.last_stop_name):

                # Arrived at stop
                self.at_stop    = True
                self.speed_ms   = 0.0
                self.speed_kmh  = 0.0
                self.last_stop_name = nearest_stop["name"]

                self._info(f"🛑 {nearest_stop['name']} — waiting {STOP_DURATION}s", "r")
                pub(self.client, self._point(status="Running 0"))
                time.sleep(STOP_DURATION)

                self.at_stop  = False
                self._info(f"🟢 Departing {nearest_stop['name']}", "g")
                continue  # re-evaluate without advancing position

            pt = self._point(status="Running 1")

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

            route_complete = self._advance()

            if route_complete:
                # ── round-trip complete: smart wait ───────────────────────────
                next_departure = self.route_start_time + RESTART_INTERVAL
                wait_s         = max(0.0, next_departure - time.time())
                self.last_stop_name = None          # reset stops for next trip

                if wait_s > 0:
                    dep_str = datetime.fromtimestamp(next_departure).strftime("%H:%M:%S")
                    self._info(
                        f"🏁 Route complete. Next departure at {dep_str} "
                        f"({wait_s:.0f}s away).", "b"
                    )
                    time.sleep(wait_s)
                else:
                    self._info("🏁 Route complete. Departing immediately.", "g")

                self.route_start_time = time.time()   # reset clock for next trip
            else:
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
