import os
import joblib
import warnings
from datetime import datetime
import threading

DAY_PROFILES = {
    0: {"day": "Monday",    "speed_min": 2.5, "speed_max": 4.5, "accel": 0.25, "decel": 0.60},
    1: {"day": "Tuesday",   "speed_min": 3.0, "speed_max": 5.0, "accel": 0.30, "decel": 0.55},
    2: {"day": "Wednesday", "speed_min": 3.0, "speed_max": 5.0, "accel": 0.30, "decel": 0.50},
    3: {"day": "Thursday",  "speed_min": 3.0, "speed_max": 5.0, "accel": 0.30, "decel": 0.55},
    4: {"day": "Friday",    "speed_min": 2.0, "speed_max": 4.0, "accel": 0.20, "decel": 0.70},
    5: {"day": "Saturday",  "speed_min": 4.0, "speed_max": 6.0, "accel": 0.40, "decel": 0.45},
    6: {"day": "Sunday",    "speed_min": 4.5, "speed_max": 6.5, "accel": 0.50, "decel": 0.40},
}

HOUR_MULTIPLIERS = {
    0: 1.30,  1: 1.35,  2: 1.40,  3: 1.40,  4: 1.35,  5: 1.20,   
    6: 1.00,  7: 0.80,  8: 0.65,  9: 0.70, 10: 0.85, 11: 0.90,   
   12: 0.85, 13: 0.90, 14: 0.95, 15: 0.90, 16: 0.80, 17: 0.65,   
   18: 0.60, 19: 0.70, 20: 0.85, 21: 0.95, 22: 1.10, 23: 1.20,   
}

class MLEstimator:
    def __init__(self):
        self.model_path = os.path.join(os.path.dirname(__file__), "..", "Model", "eta_model.pkl")
        self.model = None
        self._lock = threading.Lock()
        
        try:
            self.model = joblib.load(self.model_path)
        except Exception as e:
            print(f"Failed to load ML model: {e}")

    def predict_segment_time(self, segment_id, hour_of_day, day_of_week, segment_distance_m):
        """
        Returns estimated total time in seconds for a segment based on time and day.
        """
        base_time = 300 # Fallback 5 mins
        if self.model:
            profile = DAY_PROFILES.get(day_of_week, DAY_PROFILES[0])
            h_mult = HOUR_MULTIPLIERS.get(hour_of_day, 1.0)
            
            features = [[
                segment_id, 
                day_of_week, 
                hour_of_day,
                profile["speed_min"] * h_mult,
                profile["speed_max"] * h_mult,
                profile["accel"],
                profile["decel"],
                segment_distance_m
            ]]
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    prediction = self.model.predict(features)
                    return float(prediction[0])
                except Exception as e:
                    print(f"Prediction failed: {e}")
                    
        # Fallback heuristic if model fails or is missing
        multiplier = 1.0
        if 8 <= hour_of_day <= 10 or 17 <= hour_of_day <= 19:
            multiplier = 1.5
        if day_of_week >= 5:
            multiplier *= 0.8
            
        return base_time * multiplier

    def get_etas(self, current_segment_idx, distance_covered_km, route_manager):
        """
        Returns list of ETAs (in seconds) to all upcoming stops.
        """
        now = datetime.now()
        hour_of_day = now.hour
        day_of_week = now.weekday()
        
        etas = []
        current_accumulation = 0
        
        upcoming = route_manager.get_upcoming_stops(current_segment_idx)
        
        for stop_info in upcoming:
            seg_idx = stop_info['segment_idx']
            seg_total_dist_m = route_manager.segments[seg_idx]['total_distance_km'] * 1000
            
            total_seg_time = self.predict_segment_time(seg_idx, hour_of_day, day_of_week, seg_total_dist_m)
            
            if seg_idx == current_segment_idx:
                # Calculate based on percent of distance covered
                seg_total_dist = route_manager.segments[seg_idx]['total_distance_km']
                if seg_total_dist > 0:
                    percent_covered = min(distance_covered_km / seg_total_dist, 1.0)
                else:
                    percent_covered = 1.0
                
                remaining_time_on_segment = total_seg_time * (1.0 - percent_covered)
                current_accumulation += remaining_time_on_segment
            else:
                current_accumulation += total_seg_time
            
            etas.append({
                "stop_name": stop_info['stop_name'],
                "eta_seconds": int(current_accumulation)
            })
            
        return etas

ml_estimator = MLEstimator()
