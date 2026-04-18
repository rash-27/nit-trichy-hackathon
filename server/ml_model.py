from datetime import datetime

class MockMLEstimator:
    def __init__(self):
        # We define a base time in seconds for each segment acting as the "model output"
        # Since it's deterministic based on features as requested: segment_id, hour_of_day, day_of_week
        # We'll just define an average normal time and perturb it slightly.
        self.base_travel_times = {
            0: 300, # 5 mins
            1: 420, # 7 mins
            2: 240, # 4 mins
            3: 360  # 6 mins
        }

    def predict_segment_time(self, segment_id, hour_of_day, day_of_week):
        """
        Returns estimated total time in seconds for a segment based on time and day.
        """
        base_time = self.base_travel_times.get(segment_id, 300)
        
        # simple heuristic for traffic
        multiplier = 1.0
        if 8 <= hour_of_day <= 10 or 17 <= hour_of_day <= 19:
            multiplier = 1.5 # Rush hour
        if day_of_week >= 5: # Weekend (0=Mon, 6=Sun)
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
            total_seg_time = self.predict_segment_time(seg_idx, hour_of_day, day_of_week)
            
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

ml_estimator = MockMLEstimator()
