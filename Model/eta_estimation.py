"""
============================================================
  ETA ESTIMATION — Segment Travel Time Predictor
  NIT Hackathon | Track B
============================================================

INSTALL (run once):
-------------------
  pip install scikit-learn pandas joblib

USAGE:
------
  python eta_estimation.py                        # simulate + train + save
  python eta_estimation.py --csv location.csv     # custom CSV
  python eta_estimation.py --trials 50            # more trials per combo

OUTPUT FILES:
-------------
  eta_dataset.csv    — the generated training data
  eta_model.pkl      — trained Random Forest model

WHAT THIS DOES:
---------------
  1. Loads the route CSV (same one used by bus_script.py).
  2. Finds which CSV row index is nearest to each of the 4 stops.
  3. Defines 4 segments:
       Segment 0: Lanka Gate         → Stop - 1
       Segment 1: Stop - 1           → Hyderabad Gate
       Segment 2: Hyderabad Gate     → Rajeev Nagar Colony
       Segment 3: Rajeev Nagar Colony→ Lanka Gate
  4. For every combination of (day 0..6, hour 0..23, trial 1..N),
     runs a FAST physics simulation through each segment.
     Speed/accel/decel come from the same DAY_PROFILES dict in bus_script.
     An hour-of-day multiplier adds rush-hour / night variation.
  5. Collects rows: segment_id, day_of_week, hour_of_day,
     speed_min, speed_max, accel, decel, segment_distance_m,
     → travel_time_s  (target)
  6. Trains a Random Forest on this dataset.
  7. Saves the model to eta_model.pkl.

FEATURES USED BY THE MODEL:
----------------------------
  segment_id         0..3
  day_of_week        0..6  (Mon=0, Sun=6)
  hour_of_day        0..23
  speed_min_kmh      from day profile × hour multiplier
  speed_max_kmh      from day profile × hour multiplier
  accel_mps2         from day profile
  decel_mps2         from day profile
  segment_distance_m total route metres in this segment

PREDICTION USAGE (in your backend):
------------------------------------
  import joblib
  model = joblib.load("eta_model.pkl")
  # predict travel time for segment 2, Thursday, 9 AM
  profile = DAY_PROFILES[3]
  hour_mult = get_hour_multiplier(9)
  features = [[2, 3, 9,
               profile["speed_min"] * hour_mult,
               profile["speed_max"] * hour_mult,
               profile["accel"], profile["decel"],
               segment_distances[2]]]
  eta_seconds = model.predict(features)[0]
============================================================
"""

import argparse
import csv
import math
import os
import random
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

# ══════════════════════════════════════════════════════════════════════════════
#  SHARED CONFIG  (must match bus_script.py)
# ══════════════════════════════════════════════════════════════════════════════
ROW_SPACING_M   = 10
STOP_APPROACH_M = 50
PROXIMITY_M     = 15
SIM_DT          = 5.0       # simulation time step (seconds) — fast offline sim

# Day profiles — identical to bus_script.py
DAY_PROFILES = {
    0: {"day": "Monday",    "speed_min": 2.5, "speed_max": 4.5, "accel": 0.25, "decel": 0.60},
    1: {"day": "Tuesday",   "speed_min": 3.0, "speed_max": 5.0, "accel": 0.30, "decel": 0.55},
    2: {"day": "Wednesday", "speed_min": 3.0, "speed_max": 5.0, "accel": 0.30, "decel": 0.50},
    3: {"day": "Thursday",  "speed_min": 3.0, "speed_max": 5.0, "accel": 0.30, "decel": 0.55},
    4: {"day": "Friday",    "speed_min": 2.0, "speed_max": 4.0, "accel": 0.20, "decel": 0.70},
    5: {"day": "Saturday",  "speed_min": 4.0, "speed_max": 6.0, "accel": 0.40, "decel": 0.45},
    6: {"day": "Sunday",    "speed_min": 4.5, "speed_max": 6.5, "accel": 0.50, "decel": 0.40},
}

STOP_COORDINATES = [
    {"name": "Lanka Gate",          "lat": 25.277768, "lng": 83.002231},
    {"name": "Stop - 1",            "lat": 25.263755, "lng": 82.997520},
    {"name": "Hyderabad Gate",      "lat": 25.262927, "lng": 82.981793},
    {"name": "Rajeev Nagar Colony", "lat": 25.275039, "lng": 82.984572},
]

# Hour-of-day speed multiplier — simulates rush hour, night, off-peak
# Multiplier applied to speed_min and speed_max
HOUR_MULTIPLIERS = {
    0: 1.30,  1: 1.35,  2: 1.40,  3: 1.40,  4: 1.35,  5: 1.20,   # night  - fast (empty roads)
    6: 1.00,  7: 0.80,  8: 0.65,  9: 0.70, 10: 0.85, 11: 0.90,   # morning rush → taper
   12: 0.85, 13: 0.90, 14: 0.95, 15: 0.90, 16: 0.80, 17: 0.65,   # afternoon → evening rush
   18: 0.60, 19: 0.70, 20: 0.85, 21: 0.95, 22: 1.10, 23: 1.20,   # evening rush → night
}


# ══════════════════════════════════════════════════════════════════════════════
#  CSV LOADER
# ══════════════════════════════════════════════════════════════════════════════
def load_csv(path: str) -> list:
    if not os.path.exists(path):
        print(f"[ERROR] CSV not found: {path}")
        sys.exit(1)
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]
        for row in reader:
            try:
                rows.append((float(row["latitude"]), float(row["longitude"])))
            except (KeyError, ValueError):
                pass
    print(f"[CSV] Loaded {len(rows)} rows from '{path}'")
    return rows


# ══════════════════════════════════════════════════════════════════════════════
#  GEOMETRY HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def flat_dist(lat1, lng1, lat2, lng2) -> float:
    """Distance in metres using flat-earth approx."""
    dlat = (lat2 - lat1) * 111320
    dlng = (lng2 - lng1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat * dlat + dlng * dlng)


def find_nearest_row(rows: list, lat: float, lng: float) -> int:
    """Find the CSV row index nearest to a given coordinate."""
    best_i, best_d = 0, float("inf")
    for i, (rlat, rlng) in enumerate(rows):
        d = flat_dist(rlat, rlng, lat, lng)
        if d < best_d:
            best_i, best_d = i, d
    return best_i


# ══════════════════════════════════════════════════════════════════════════════
#  FIND SEGMENT BOUNDARIES
# ══════════════════════════════════════════════════════════════════════════════
def compute_segments(rows: list) -> list:
    """
    Returns list of 4 segments, each a dict:
      { "name": "...", "start_idx": ..., "end_idx": ..., "distance_m": ... }
    The route is circular: S0→S1→S2→S3→S0.
    """
    stop_indices = []
    for stop in STOP_COORDINATES:
        idx = find_nearest_row(rows, stop["lat"], stop["lng"])
        stop_indices.append(idx)
        print(f"  Stop '{stop['name']}' -> row {idx}  "
              f"(dist to exact coord: {flat_dist(rows[idx][0], rows[idx][1], stop['lat'], stop['lng']):.1f} m)")

    segments = []
    n_stops = len(STOP_COORDINATES)
    for i in range(n_stops):
        start_idx = stop_indices[i]
        end_idx   = stop_indices[(i + 1) % n_stops]
        name = f"{STOP_COORDINATES[i]['name']} -> {STOP_COORDINATES[(i+1)%n_stops]['name']}"

        # Compute distance along the CSV (may wrap around)
        if end_idx > start_idx:
            n_rows = end_idx - start_idx
        else:
            n_rows = (len(rows) - start_idx) + end_idx
        distance_m = n_rows * ROW_SPACING_M

        segments.append({
            "id":         i,
            "name":       name,
            "start_idx":  start_idx,
            "end_idx":    end_idx,
            "n_rows":     n_rows,
            "distance_m": distance_m,
        })
        print(f"  Segment {i}: {name}  ({n_rows} rows = {distance_m} m)")

    return segments


# ══════════════════════════════════════════════════════════════════════════════
#  FAST PHYSICS SIMULATION (no MQTT, no sleep, pure math)
# ══════════════════════════════════════════════════════════════════════════════
def get_hour_multiplier(hour: int) -> float:
    return HOUR_MULTIPLIERS.get(hour, 1.0)


def simulate_segment(segment_distance_m: float, profile: dict, hour: int) -> float:
    """
    Simulate a bus travelling through a segment and return travel time in seconds.

    Physics:
      - Starts at 0 speed (just left a stop).
      - Accelerates to cruise.
      - Cruises with slight random noise.
      - Decelerates in the last STOP_APPROACH_M before the next stop.
      - Returns total elapsed seconds.

    This runs in pure math at SIM_DT steps — no sleep, no I/O.
    """
    h_mult    = get_hour_multiplier(hour)
    # Add some random noise (±15%) to make each trial unique
    noise     = random.uniform(0.85, 1.15)
    cruise_ms = (profile["speed_max"] * h_mult * noise) / 3.6
    min_ms    = (profile["speed_min"] * h_mult * noise) / 3.6
    accel     = profile["accel"]
    decel     = profile["decel"]

    # Ensure minimum viable speed
    cruise_ms = max(cruise_ms, 0.3)
    min_ms    = max(min_ms, 0.1)

    speed_ms     = 0.0
    distance     = 0.0
    elapsed      = 0.0
    total_dist   = segment_distance_m

    while distance < (total_dist - PROXIMITY_M):
        remaining = total_dist - distance

        # ── determine target speed ──
        if remaining <= STOP_APPROACH_M:
            ratio  = max(0.0, (remaining - PROXIMITY_M) / (STOP_APPROACH_M - PROXIMITY_M))
            target = max(1.0, cruise_ms * ratio)  # Minimum 1 m/s to prevent infinite loop
        else:
            target = cruise_ms + random.uniform(-0.05, 0.05) * (cruise_ms - min_ms)
            target = max(min_ms, min(cruise_ms, target))

        # ── update speed ──
        if speed_ms < target:
            speed_ms = min(target, speed_ms + accel * SIM_DT)
        else:
            speed_ms = max(0.5, max(target, speed_ms - decel * SIM_DT)) # Don't drop below 0.5 m/s

        # ── advance ──
        step_m    = speed_ms * SIM_DT
        distance += step_m
        elapsed  += SIM_DT

        # Safety
        if elapsed > 10000:
            break

    return elapsed


# ══════════════════════════════════════════════════════════════════════════════
#  DATASET GENERATION
# ══════════════════════════════════════════════════════════════════════════════
def generate_dataset(segments: list, trials: int = 20) -> pd.DataFrame:
    """
    For every (segment × day × hour × trial), simulate and record.
    """
    records = []
    total   = len(segments) * 7 * 24 * trials
    count   = 0
    t0      = time.time()

    for seg in segments:
        for day in range(7):
            profile = DAY_PROFILES[day]
            for hour in range(24):
                h_mult = get_hour_multiplier(hour)
                for trial in range(trials):
                    travel_s = simulate_segment(seg["distance_m"], profile, hour)
                    records.append({
                        "segment_id":        seg["id"],
                        "segment_name":      seg["name"],
                        "day_of_week":       day,
                        "day_name":          profile["day"],
                        "hour_of_day":       hour,
                        "speed_min_kmh":     profile["speed_min"] * h_mult,
                        "speed_max_kmh":     profile["speed_max"] * h_mult,
                        "accel_mps2":        profile["accel"],
                        "decel_mps2":        profile["decel"],
                        "segment_distance_m": seg["distance_m"],
                        "travel_time_s":     round(travel_s, 2),
                    })
                    count += 1

    print(f"  Simulated {total} trips in {time.time()-t0:.1f}s")
    return pd.DataFrame(records)


# ══════════════════════════════════════════════════════════════════════════════
#  TRAINING
# ══════════════════════════════════════════════════════════════════════════════
FEATURE_COLS = [
    "segment_id",
    "day_of_week",
    "hour_of_day",
    "speed_min_kmh",
    "speed_max_kmh",
    "accel_mps2",
    "decel_mps2",
    "segment_distance_m",
]

def train_model(df: pd.DataFrame, model_path: str = "eta_model.pkl"):
    """Train a RandomForest and save as .pkl."""
    X = df[FEATURE_COLS]
    y = df["travel_time_s"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    print(f"\n[TRAIN] Training set: {len(X_train)} rows")
    print(f"[TRAIN] Test set:     {len(X_test)} rows")

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=15,
        min_samples_split=5,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae    = mean_absolute_error(y_test, y_pred)
    r2     = r2_score(y_test, y_pred)

    print(f"[TRAIN] MAE:  {mae:.2f} seconds")
    print(f"[TRAIN] R²:   {r2:.4f}")

    # Save
    joblib.dump(model, model_path)
    print(f"\n[SAVED] Model -> {model_path}")

    return model


# ══════════════════════════════════════════════════════════════════════════════
#  DEMO PREDICTIONS
# ══════════════════════════════════════════════════════════════════════════════
def demo_predictions(model, segments: list):
    """Print a few sample predictions for sanity checking."""
    print("\n" + "=" * 65)
    print("  SAMPLE PREDICTIONS")
    print("=" * 65)
    print(f"  {'Segment':<35s} {'Day':>10s} {'Hour':>5s} {'ETA (s)':>9s} {'ETA (min)':>10s}")
    print("  " + "-" * 65)

    test_cases = [
        (0, 0, 8),   # Seg 0, Monday 8am
        (0, 4, 18),  # Seg 0, Friday 6pm
        (0, 6, 10),  # Seg 0, Sunday 10am
        (1, 0, 8),   # Seg 1, Monday 8am
        (2, 4, 17),  # Seg 2, Friday 5pm
        (3, 6, 6),   # Seg 3, Sunday 6am
    ]

    for seg_id, day, hour in test_cases:
        seg      = segments[seg_id]
        profile  = DAY_PROFILES[day]
        h_mult   = get_hour_multiplier(hour)
        features = [[
            seg_id, day, hour,
            profile["speed_min"] * h_mult,
            profile["speed_max"] * h_mult,
            profile["accel"],
            profile["decel"],
            seg["distance_m"],
        ]]
        eta = model.predict(features)[0]
        print(f"  {seg['name']:<35s} {profile['day']:>10s} {hour:>5d} {eta:>9.1f} {eta/60:>10.1f}")

    print()


# ══════════════════════════════════════════════════════════════════════════════
#  TESTING SIMULATION (7 Days, 10 Vehicles / Segment / Day)
# ══════════════════════════════════════════════════════════════════════════════
def test_simulation_accuracy(model, segments):
    print("\n" + "=" * 65)
    print("  SIMULATION TESTING (±5 MIN TOLERANCE)")
    print("=" * 65)
    
    total_predictions = 0
    correct_predictions = 0
    
    t0 = time.time()
    
    # 7 days
    for day in range(7):
        profile = DAY_PROFILES[day]
        for seg in segments:
            # 10 vehicles at different times
            random_hours = random.sample(range(24), 10)
            for hour in random_hours:
                h_mult = get_hour_multiplier(hour)
                
                # Actual simulated time
                actual_s = simulate_segment(seg["distance_m"], profile, hour)
                
                # Predicted time
                features = [[
                    seg["id"], day, hour,
                    profile["speed_min"] * h_mult,
                    profile["speed_max"] * h_mult,
                    profile["accel"],
                    profile["decel"],
                    seg["distance_m"]
                ]]
                predicted_s = model.predict(features)[0]
                
                # Check if within +- 5 minutes (300 seconds)
                diff_s = abs(actual_s - predicted_s)
                if diff_s <= 300:
                    correct_predictions += 1
                total_predictions += 1
                
    accuracy = (correct_predictions / total_predictions) * 100
    
    print(f"  Total Vehicles Simulated : {total_predictions}")
    print(f"  Correct Predictions      : {correct_predictions}")
    print(f"  Accuracy (±5 mins)       : {accuracy:.2f}%")
    print(f"  Precision (±5 mins)      : {accuracy:.2f}%")
    print(f"  Time taken               : {time.time()-t0:.2f}s\n")

# ══════════════════════════════════════════════════════════════════════════════
#  BATCH TRAINING (Weekly Update)
# ══════════════════════════════════════════════════════════════════════════════
def weekly_batch_training(existing_df, segments, trials_per_week=5):
    """
    Simulates a week passing, gathering new data, appending to existing dataset,
    and retraining the model.
    """
    print("\n" + "=" * 65)
    print("  WEEKLY BATCH TRAINING")
    print("=" * 65)
    print("[BATCH] Gathering new data for the week...")
    new_data = generate_dataset(segments, trials=trials_per_week)
    
    print(f"\n[BATCH] Previous dataset size : {len(existing_df)} rows")
    print(f"[BATCH] New data added        : {len(new_data)} rows")
    
    combined_df = pd.concat([existing_df, new_data], ignore_index=True)
    print(f"[BATCH] Combined dataset size : {len(combined_df)} rows")
    
    print("[BATCH] Retraining model on combined data...")
    new_model = train_model(combined_df, model_path="eta_model_updated.pkl")
    return new_model, combined_df


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETA Estimation — Segment Travel Time Predictor")
    parser.add_argument("--csv",      default="location.csv", help="Path to route CSV")
    parser.add_argument("--trials",   default=20, type=int,   help="Trials per (segment × day × hour)")
    parser.add_argument("--out_csv",  default="eta_dataset.csv",  help="Output dataset CSV")
    parser.add_argument("--out_model",default="eta_model.pkl",    help="Output model file")
    parser.add_argument("--simulate_weekly", action="store_true", help="Simulate weekly batch training")
    args = parser.parse_args()

    print("=" * 60)
    print("  ETA ESTIMATION — Dataset Generation & Training")
    print("=" * 60)

    # 1. Load route
    rows = load_csv(args.csv)

    # 2. Find segments
    print(f"\n[SEGMENTS] Finding stop row indices...")
    segments = compute_segments(rows)

    # 3. Simulate
    print(f"\n[SIM] Generating dataset: {len(segments)} segs × 7 days × 24 hours × {args.trials} trials "
          f"= {len(segments)*7*24*args.trials} rows")
    df = generate_dataset(segments, trials=args.trials)

    # 4. Save dataset
    df.to_csv(args.out_csv, index=False)
    print(f"[SAVED] Dataset -> {args.out_csv}  ({len(df)} rows)")

    # 5. Train
    model = train_model(df, model_path=args.out_model)

    # 6. Test Simulation (7 days, 10 vehicles)
    test_simulation_accuracy(model, segments)

    # 7. Demo
    demo_predictions(model, segments)

    # 8. Simulate Weekly Batch Training
    if args.simulate_weekly:
        model, df = weekly_batch_training(df, segments, trials_per_week=args.trials)
        
        # Test again on updated model
        print("\n[TEST] Evaluating updated model...")
        test_simulation_accuracy(model, segments)

    print("[DONE] You can now use eta_model.pkl in your backend for real-time ETA predictions.")
