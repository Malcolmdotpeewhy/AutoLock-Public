import time
import math
import json

# Constants for mathematical model
PICK_WEIGHT = 5.0
BENCH_WEIGHT = 1.2
RECENCY_WEIGHT = 4.0
DECAY_RATE = 0.002
STABILITY_WEIGHT = 0.5
DECAY_CONSTANT_T = 72 * 3600  # 72 hours in seconds

class PreferenceModel:
    """
    Self-learning behavioral preference model for ARAM champions.
    Observational only: tracks picks, bench exposures, recency, and decay.
    """
    def __init__(self, config_manager, asset_manager=None):
        self.config = config_manager
        self.asset_manager = asset_manager
        self.state = self._load_state()

    def _load_state(self):
        # Default state
        default_state = {
            "enabled": True,
            "matches_tracked": 0,
            "champions": {},  # Map of champion_key -> data block
            "created_at": time.time(),
            "updated_at": time.time()
        }
        loaded_state = self.config.get("experimental_profile", {})

        # Merge loaded state into default state to ensure all keys exist
        state = default_state.copy()
        if isinstance(loaded_state, dict):
            state.update(loaded_state)

        # Ensure 'champions' is a dict
        if "champions" not in state or not isinstance(state["champions"], dict):
            state["champions"] = {}
        return state

    def save(self):
        self.state["updated_at"] = time.time()
        self.config.set("experimental_profile", self.state)

    def reset(self):
        self.state = {
            "enabled": True,
            "matches_tracked": 0,
            "champions": {},
            "created_at": time.time(),
            "updated_at": time.time()
        }
        self.save()

    def get_champion_data(self, champ_key):
        if champ_key not in self.state["champions"]:
            self.state["champions"][champ_key] = {
                "champion": champ_key,
                "score": 0.0,
                "picked_count": 0,
                "bench_seen_count": 0,
                "last_picked": None,
                "last_seen": None,
                "confidence": 0,
                "created_at": time.time(),
                "updated_at": time.time()
            }
        return self.state["champions"][champ_key]

    def update_after_match(self, picked_champ_id, bench_champ_ids):
        """
        Triggered exactly once at game start.
        picked_champ_id: int (Champion ID of locked pick)
        bench_champ_ids: list of ints (Champion IDs on bench)
        """
        if not self.state.get("enabled", True):
            return

        now = time.time()

        # Update Picked
        if picked_champ_id:
            picked_key = self._get_champ_key(picked_champ_id)
            if picked_key:
                c_data = self.get_champion_data(picked_key)
                c_data["picked_count"] += 1
                c_data["last_picked"] = now
                c_data["last_seen"] = now
                c_data["updated_at"] = now
                c_data["score"] += PICK_WEIGHT

        # Update Bench
        for cid in bench_champ_ids:
            b_key = self._get_champ_key(cid)
            if b_key:
                c_data = self.get_champion_data(b_key)
                c_data["bench_seen_count"] += 1
                c_data["last_seen"] = now
                c_data["updated_at"] = now
                c_data["score"] -= BENCH_WEIGHT

        if picked_champ_id or bench_champ_ids:
            self.state["matches_tracked"] += 1
            self.recalculate_scores(now)
            self.save()

    def _get_champ_key(self, champ_id):
        if self.asset_manager:
            # Try to get the string key
            key = self.asset_manager.id_to_key.get(champ_id)
            if key: return key
        return str(champ_id)

    def recalculate_scores(self, time_now=None):
        if time_now is None:
            time_now = time.time()

        for c_key, data in self.state["champions"].items():
            picked = data["picked_count"]
            bench = data["bench_seen_count"]
            
            # Confidence
            conf = picked + bench
            data["confidence"] = conf

            # Stability
            stability_bonus = math.log(conf + 1) * STABILITY_WEIGHT
            
            # Recency Priority
            recency_bonus = 0.0
            if data["last_picked"]:
                dt = time_now - data["last_picked"]
                # e^(-dt / T)
                recency_bonus = RECENCY_WEIGHT * math.exp(-max(0, dt) / DECAY_CONSTANT_T)

            # Decay Penalty
            age = 0.0
            if data["created_at"]:
                age = (time_now - data["created_at"]) / 3600.0 # age in hours
            decay_penalty = DECAY_RATE * conf * age

            # Final Math
            score = (picked * PICK_WEIGHT) - (bench * BENCH_WEIGHT) + recency_bonus - decay_penalty + stability_bonus
            
            data["score"] = score

    def export_data(self, filepath):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=4)
            return True
        except Exception as e:
            return False

    def import_data(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Validation
                if "champions" in data:
                    self.state = data
                    self.save()
                    return True
        except Exception as e:
            pass
        return False

    def get_ranked_list(self):
        """Returns sorted list of champion data blocks."""
        champs = list(self.state.get("champions", {}).values())
        champs.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return champs
