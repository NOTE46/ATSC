import json
import threading
from pathlib import Path

# Module-level state tracking
_wait_counts = {}
_last_lane = None
_control_lock = threading.Lock()


def _load_priorities():
    """Read emergency_priority from config.json with fallback."""
    cfg_path = Path(__file__).resolve().parent / "config.json"
    default_prio = {"ambulance": 2, "firetruck": 1, "none": 0}
    if not cfg_path.exists():
        return default_prio
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        prio = cfg.get("emergency_priority")
        if isinstance(prio, dict):
            return prio
        return default_prio
    except Exception:
        return default_prio


def reset_control():
    """Reset internal wait-count and last-lane state."""
    global _wait_counts, _last_lane
    with _control_lock:
        _wait_counts.clear()
        _last_lane = None


def controlfun(data, lanes):
    """
    Select active green lane using 3-tier priority controller:
    - Tier 1: Emergency Override (highest lane_prio, density, wait_count)
    - Tier 2: Anti-Starvation Queue (cooldown & wait_counts >= lanes with traffic)
    - Tier 3: Weighted Density Score (density + wait*3, or fair rotation on zero traffic)
    """
    global _wait_counts, _last_lane

    with _control_lock:
        if lanes <= 0:
            return {"lane_no": 0, "signal": "Green"}

        # Ensure all lanes exist in _wait_counts
        for i in range(lanes):
            if i not in _wait_counts:
                _wait_counts[i] = 0

        priorities = _load_priorities()

        # Extract normalized lane attributes
        densities = {}
        lane_prios = {}

        for i in range(lanes):
            lane_info = None
            if isinstance(data, dict):
                lane_info = data.get(i)
                if lane_info is None and str(i) in data:
                    lane_info = data[str(i)]
            elif isinstance(data, (list, tuple)):
                if 0 <= i < len(data):
                    lane_info = data[i]

            if not isinstance(lane_info, dict):
                lane_info = {}

            densities[i] = max(0, int(lane_info.get("density", 0)))

            # Determine emergency priority
            etype = str(lane_info.get("emergency_type", "")).strip().lower()
            if etype in priorities and etype != "none":
                lane_prios[i] = priorities[etype]
            elif lane_info.get("ambulance"):
                lane_prios[i] = priorities.get("ambulance", 2)
            elif lane_info.get("emergency"):
                lane_prios[i] = priorities.get("ambulance", 2)
            elif etype == "none":
                lane_prios[i] = priorities.get("none", 0)
            else:
                lane_prios[i] = 0

        winner = None

        # Tier 1 (Emergency Override): Lanes with priority > 0
        emergency_lanes = [i for i in range(lanes) if lane_prios[i] > 0]
        if emergency_lanes:
            # Winner selected by highest (lane_prio, density, wait_count)
            # Tie-breaker: lowest lane index (-i)
            winner = max(
                emergency_lanes,
                key=lambda i: (lane_prios[i], densities[i], _wait_counts.get(i, 0), -i)
            )

        # Tier 2 & Tier 3: When no emergency
        if winner is None:
            # Apply cooldown: _last_lane excluded if other lanes have density > 0
            other_traffic = any(
                densities[j] > 0 for j in range(lanes) if j != _last_lane
            )
            if _last_lane is not None and other_traffic:
                candidate_lanes = [i for i in range(lanes) if i != _last_lane]
            else:
                candidate_lanes = list(range(lanes))

            # Tier 2 (Anti-Starvation Queue):
            # Starving lanes with _wait_counts[i] >= lanes and density > 0
            starving_lanes = [
                i for i in candidate_lanes
                if _wait_counts.get(i, 0) >= lanes and densities[i] > 0
            ]
            if starving_lanes:
                # Winner selected by highest (_wait_counts[i], density)
                # Tie-breaker: lowest lane index (-i)
                winner = max(
                    starving_lanes,
                    key=lambda i: (_wait_counts.get(i, 0), densities[i], -i)
                )

        # Tier 3 (Weighted Density Score)
        if winner is None:
            all_zero = all(densities[i] == 0 for i in range(lanes))
            if all_zero:
                # If all densities are 0 and _last_lane is not None, rotate to (_last_lane + 1) % lanes
                if _last_lane is not None:
                    winner = (_last_lane + 1) % lanes
                else:
                    winner = 0
            else:
                # Winner selected by highest (density + (_wait_counts[i] * 3), _wait_counts[i])
                # Tie-breaker: lowest lane index (-i)
                winner = max(
                    candidate_lanes,
                    key=lambda i: (
                        densities[i] + (_wait_counts.get(i, 0) * 3),
                        _wait_counts.get(i, 0),
                        -i
                    )
                )

        # Counter updates:
        # Reset winner wait count to 0, record _last_lane = winner,
        # and increment _wait_counts[i] += 1 for all other lanes with density > 0
        _wait_counts[winner] = 0
        _last_lane = winner
        for i in range(lanes):
            if i != winner and densities[i] > 0:
                _wait_counts[i] = _wait_counts.get(i, 0) + 1

        return {
            "lane_no": winner,
            "signal": "Green"
        }