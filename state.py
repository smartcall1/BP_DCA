import json
from pathlib import Path

STATE_FILE = Path(__file__).parent / "state.json"


def load() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"total_invested_usdc": 0.0, "total_bp_purchased": 0.0}


def update(invested_usdc: float, bp_purchased: float) -> dict:
    s = load()
    s["total_invested_usdc"] += invested_usdc
    s["total_bp_purchased"] += bp_purchased
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2)
    return s


def avg_cost(s: dict) -> float:
    if s["total_bp_purchased"] <= 0:
        return 0.0
    return s["total_invested_usdc"] / s["total_bp_purchased"]
