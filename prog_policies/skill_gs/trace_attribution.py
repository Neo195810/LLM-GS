from __future__ import annotations

from collections import Counter
from typing import Any


def analyze_doorkey_trace(
    evaluation: dict[str, Any],
    max_steps: int | None = None,
) -> dict[str, Any]:
    """Convert a DoorKey execution trace into deterministic attribution metrics."""

    trace = list(evaluation.get("trace", []))
    steps = int(evaluation.get("steps", len(trace)))
    reward = float(evaluation.get("reward", evaluation.get("best_reward", 0.0)))
    success = bool(evaluation.get("success", False))
    terminated = bool(evaluation.get("terminated", False))
    crashed = bool(evaluation.get("crashed", False))
    actions = [str(item.get("action", "")) for item in trace]
    action_counts = Counter(actions)
    turn_count = action_counts["turnLeft"] + action_counts["turnRight"]
    blocked_moves = sum(
        1
        for item in trace
        if item.get("action") == "move"
        and _xy(item.get("agent_before")) == _xy(item.get("agent_after"))
    )
    no_position_change = sum(
        1
        for item in trace
        if _xy(item.get("agent_before")) == _xy(item.get("agent_after"))
    )
    positions = [
        _xy(item.get("agent_after"))
        for item in trace
        if _xy(item.get("agent_after")) is not None
    ]
    states = [
        tuple(item.get("agent_after", []))
        for item in trace
        if item.get("agent_after") is not None
    ]
    door_open = bool(trace[-1].get("door_open", False)) if trace else False
    stage_at_end = _stage_at_end(success, reward, door_open, crashed)
    budget_exhausted = (
        max_steps is not None
        and steps >= max_steps
        and not terminated
        and not success
    )

    return {
        "steps": steps,
        "max_steps": max_steps,
        "budget_exhausted": budget_exhausted,
        "reward_at_end": reward,
        "terminated": terminated,
        "crashed": crashed,
        "stage_at_end": stage_at_end,
        "door_open_at_end": door_open,
        "action_counts": dict(action_counts),
        "move_count": action_counts["move"],
        "turn_count": turn_count,
        "turn_ratio": turn_count / steps if steps else 0.0,
        "blocked_moves": blocked_moves,
        "no_position_change_count": no_position_change,
        "unique_positions": len(set(positions)),
        "repeated_positions": len(positions) - len(set(positions)),
        "unique_states": len(set(states)),
        "repeated_states": len(states) - len(set(states)),
        "attribution": _attribute(
            success=success,
            crashed=crashed,
            budget_exhausted=budget_exhausted,
            blocked_moves=blocked_moves,
            stage_at_end=stage_at_end,
        ),
    }


def _xy(agent: Any) -> tuple[int, int] | None:
    if not isinstance(agent, (list, tuple)) or len(agent) < 2:
        return None
    return (int(agent[0]), int(agent[1]))


def _stage_at_end(
    success: bool,
    reward: float,
    door_open: bool,
    crashed: bool,
) -> str:
    if crashed:
        return "crashed"
    if success or reward >= 1.0:
        return "completed"
    if reward >= 0.5 or door_open:
        return "after_key_before_goal"
    return "before_key"


def _attribute(
    success: bool,
    crashed: bool,
    budget_exhausted: bool,
    blocked_moves: int,
    stage_at_end: str,
) -> str:
    if success:
        return "completed"
    if crashed:
        return "invalid_action_or_crash"
    if blocked_moves:
        return "blocked_motion"
    if budget_exhausted and stage_at_end == "after_key_before_goal":
        return "budget_cutoff_after_key"
    if budget_exhausted and stage_at_end == "before_key":
        return "budget_cutoff_before_key"
    if budget_exhausted:
        return "budget_cutoff"
    return f"incomplete_{stage_at_end}"
