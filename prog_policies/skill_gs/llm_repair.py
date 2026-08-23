from __future__ import annotations

from pathlib import Path
from typing import Any

from prog_policies.karel_tasks import DoorKey

from .doorkey_policy import ACTION_NAMES, _shortest_path_actions
from .doorkey_state import extract_doorkey_state
from .evaluator import KAREL_DOORKEY_ENV_ARGS
from .llm_generated_baseline import evaluate_doorkey_action_sequence
from .schemas import SkillRecord
from .skill_manager import JsonSkillStore
from .trace_attribution import analyze_doorkey_trace


REPAIR_AGENT_NAME = "LLMRepairAgent"
POST_KEY_REPAIR_SKILL_ID = "llm_repair.karel.doorkey.navigate_to_goal_after_key.v1"
KEY_REPAIR_SKILL_ID = "llm_repair.karel.doorkey.navigate_to_key_before_door_open.v1"


class LLMPolicyRepairError(RuntimeError):
    pass


def repair_doorkey_llm_policy(
    llm_result: dict[str, Any],
    skill_store_path: str | Path | None = None,
    source_label: str = "unknown",
) -> dict[str, Any]:
    """Repair a failed one-shot DoorKey action sequence and store the repair skill."""

    seed = int(llm_result["seed"])
    policy = dict(llm_result.get("policy") or {})
    actions = _validated_actions(policy.get("actions", []))
    evaluation = dict(
        llm_result.get("evaluation")
        or evaluate_doorkey_action_sequence(seed=seed, actions=actions)
    )
    source_attribution = analyze_doorkey_trace(evaluation)

    if evaluation.get("success"):
        return _already_successful_result(
            llm_result=llm_result,
            policy=policy,
            actions=actions,
            evaluation=evaluation,
            source_attribution=source_attribution,
        )

    preserved_prefix_steps = _successful_key_pickup_prefix_steps(evaluation)
    key_actions: list[str] | None = None
    if preserved_prefix_steps is None:
        prefix_actions = []
        key_actions, suffix_actions = _full_key_then_goal_repair_actions(seed)
        repaired_actions = [*key_actions, *suffix_actions]
        strategy_id = "replan_via_key_then_goal"
        target_subgoal = "navigate_to_key_before_door_open"
        rationale = (
            "No successful key pickup was found, so replan from the initial "
            "state to the key, pick it, then navigate to the goal."
        )
    else:
        prefix_actions = actions[:preserved_prefix_steps]
        suffix_actions = _post_key_navigation_suffix(seed, prefix_actions)
        repaired_actions = [*prefix_actions, *suffix_actions]
        strategy_id = "splice_post_key_navigation"
        target_subgoal = "navigate_to_goal_after_key"
        rationale = (
            "Preserve the verified key pickup prefix, then replace the failed "
            "post-key navigation segment with a shortest-path suffix to the goal."
        )

    repaired_evaluation = evaluate_doorkey_action_sequence(
        seed=seed,
        actions=repaired_actions,
    )
    repaired_attribution = analyze_doorkey_trace(repaired_evaluation)
    repaired_policy = _repaired_policy(policy, repaired_actions, source_label)
    repair_plan = {
        "status": "repaired",
        "strategy_id": strategy_id,
        "target_subgoal": target_subgoal,
        "preserved_prefix_steps": preserved_prefix_steps or 0,
        "key_navigation_steps": len(key_actions or []),
        "replacement_suffix_steps": len(suffix_actions),
        "failure_attribution": source_attribution["attribution"],
        "source_label": source_label,
        "rationale": rationale,
    }
    skill_memory = _store_repair_skills(
        store_path=skill_store_path,
        seed=seed,
        llm_result=llm_result,
        source_label=source_label,
        key_actions=key_actions,
        suffix_actions=suffix_actions,
        repair_plan=repair_plan,
        original_evaluation=evaluation,
        repaired_evaluation=repaired_evaluation,
        source_attribution=source_attribution,
    )

    return {
        "task": llm_result.get("task", "DoorKey"),
        "seed": seed,
        "repair_agent": REPAIR_AGENT_NAME,
        "source_policy": policy,
        "source_evaluation": evaluation,
        "source_attribution": source_attribution,
        "repair_plan": repair_plan,
        "repaired_policy": repaired_policy,
        "repaired_evaluation": repaired_evaluation,
        "repaired_attribution": repaired_attribution,
        "skill_memory": skill_memory,
    }


def _already_successful_result(
    llm_result: dict[str, Any],
    policy: dict[str, Any],
    actions: list[str],
    evaluation: dict[str, Any],
    source_attribution: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task": llm_result.get("task", "DoorKey"),
        "seed": int(llm_result["seed"]),
        "repair_agent": REPAIR_AGENT_NAME,
        "source_policy": policy,
        "source_evaluation": evaluation,
        "source_attribution": source_attribution,
        "repair_plan": {
            "status": "not_needed",
            "strategy_id": "already_successful",
            "target_subgoal": None,
            "preserved_prefix_steps": len(actions),
            "replacement_suffix_steps": 0,
            "failure_attribution": source_attribution["attribution"],
            "rationale": "The LLM policy already solved the task.",
        },
        "repaired_policy": policy,
        "repaired_evaluation": evaluation,
        "repaired_attribution": source_attribution,
        "skill_memory": {
            "stored_skills": 0,
            "updated_skills": 0,
            "skipped_skills": 0,
            "store_path": None,
        },
    }


def _validated_actions(actions: Any) -> list[str]:
    if not isinstance(actions, list):
        raise ValueError("policy.actions must be a list.")
    invalid_actions = [
        action for action in actions if not isinstance(action, str) or action not in ACTION_NAMES
    ]
    if invalid_actions:
        raise ValueError(
            "policy.actions contains unsupported action(s): "
            + ", ".join(str(action) for action in invalid_actions)
        )
    return list(actions)


def _successful_key_pickup_prefix_steps(evaluation: dict[str, Any]) -> int | None:
    for item in evaluation.get("trace", []):
        if item.get("action") != "pickMarker":
            continue
        if float(item.get("instant_reward", 0.0)) > 0 or item.get("door_open"):
            return int(item["step"])
    return None


def _post_key_navigation_suffix(seed: int, prefix_actions: list[str]) -> list[str]:
    task = DoorKey(dict(KAREL_DOORKEY_ENV_ARGS), seed)
    env = task.get_environment()

    for action in prefix_actions:
        env.run_action(action)
        task.get_reward(env)

    snapshot = extract_doorkey_state(env)
    if snapshot.goal_cell is None:
        raise LLMPolicyRepairError("Could not locate the DoorKey goal cell after replay.")

    return [*_shortest_path_actions(env, snapshot.goal_cell), "putMarker"]


def _full_key_then_goal_repair_actions(seed: int) -> tuple[list[str], list[str]]:
    task = DoorKey(dict(KAREL_DOORKEY_ENV_ARGS), seed)
    env = task.get_environment()
    snapshot = extract_doorkey_state(env)
    if snapshot.key_cell is None:
        raise LLMPolicyRepairError("Could not locate the DoorKey key cell.")
    if snapshot.goal_cell is None:
        raise LLMPolicyRepairError("Could not locate the DoorKey goal cell.")

    key_actions = _shortest_path_actions(env, snapshot.key_cell)
    for action in key_actions:
        env.run_action(action)
        task.get_reward(env)

    env.run_action("pickMarker")
    task.get_reward(env)
    suffix_actions = [*_shortest_path_actions(env, snapshot.goal_cell), "putMarker"]
    return [*key_actions, "pickMarker"], suffix_actions


def _repaired_policy(
    policy: dict[str, Any],
    repaired_actions: list[str],
    source_label: str,
) -> dict[str, Any]:
    policy_name = str(policy.get("policy_name") or "llm_generated_policy")
    return {
        "policy_name": f"{policy_name}.repaired",
        "policy_type": "action_sequence",
        "actions": repaired_actions,
        "notes": (
            f"Repaired from {source_label} by preserving the successful key pickup "
            "prefix and replacing post-key navigation."
        ),
    }


def _store_repair_skills(
    store_path: str | Path | None,
    seed: int,
    llm_result: dict[str, Any],
    source_label: str,
    key_actions: list[str] | None,
    suffix_actions: list[str],
    repair_plan: dict[str, Any],
    original_evaluation: dict[str, Any],
    repaired_evaluation: dict[str, Any],
    source_attribution: dict[str, Any],
) -> dict[str, Any]:
    if not store_path:
        return {
            "stored_skills": 0,
            "updated_skills": 0,
            "skipped_skills": 0,
            "store_path": None,
        }

    store = JsonSkillStore(store_path).load()
    stored_skills = 0
    updated_skills = 0
    skipped_skills = 0

    if key_actions is not None:
        existing_key_skill = store.get(KEY_REPAIR_SKILL_ID)
        if existing_key_skill is None:
            store.upsert(
                _make_key_repair_skill(
                    seed=seed,
                    llm_result=llm_result,
                    source_label=source_label,
                    key_actions=key_actions,
                    repair_plan=repair_plan,
                    original_evaluation=original_evaluation,
                    repaired_evaluation=repaired_evaluation,
                    source_attribution=source_attribution,
                )
            )
            stored_skills += 1
        elif _merge_key_repair_observation(
            existing_key_skill,
            seed=seed,
            source_label=source_label,
            key_actions=key_actions,
            repaired_evaluation=repaired_evaluation,
        ):
            updated_skills += 1
        else:
            skipped_skills += 1

    existing_post_key_skill = store.get(POST_KEY_REPAIR_SKILL_ID)
    if existing_post_key_skill is None:
        store.upsert(
            _make_post_key_repair_skill(
                seed=seed,
                llm_result=llm_result,
                source_label=source_label,
                suffix_actions=suffix_actions,
                repair_plan=repair_plan,
                original_evaluation=original_evaluation,
                repaired_evaluation=repaired_evaluation,
                source_attribution=source_attribution,
            )
        )
        stored_skills += 1
    elif _merge_repair_observation(
        existing_post_key_skill,
        seed=seed,
        source_label=source_label,
        repaired_evaluation=repaired_evaluation,
    ):
        updated_skills += 1
    else:
        skipped_skills += 1

    store.save()
    return {
        "stored_skills": stored_skills,
        "updated_skills": updated_skills,
        "skipped_skills": skipped_skills,
        "store_path": str(Path(store_path)),
    }


def _make_key_repair_skill(
    seed: int,
    llm_result: dict[str, Any],
    source_label: str,
    key_actions: list[str],
    repair_plan: dict[str, Any],
    original_evaluation: dict[str, Any],
    repaired_evaluation: dict[str, Any],
    source_attribution: dict[str, Any],
) -> SkillRecord:
    return SkillRecord(
        skill_id=KEY_REPAIR_SKILL_ID,
        name="repair_navigate_to_key_before_door_open",
        description=(
            "Repair learned from failed LLM DoorKey policies before key pickup: "
            "navigate to key_position first, then use pickMarker exactly on the key."
        ),
        task_family="Karel",
        dsl_source="navigate_to key_position then pickMarker",
        ast_json={
            "type": "strategy_hint",
            "target": "key_position",
            "terminal_action": "pickMarker",
            "observed_actions": list(key_actions),
        },
        root_nonterminal="StrategyHint",
        semantic_tags=[
            "before_key",
            "doorkey",
            "key",
            "key_navigation",
            "llm_repair",
            "navigation",
            "replanner",
        ],
        preconditions=["door_closed", "key_not_picked"],
        postconditions=["door_open", "key_picked"],
        success_rate=1.0 if repaired_evaluation.get("success") else 0.0,
        mean_reward=float(repaired_evaluation.get("reward", 0.0)),
        num_evaluations=1,
        failure_signatures=[
            "before_key_navigation_failed",
            "missed_key_pickup",
            source_attribution["attribution"],
        ],
        metadata={
            "source_agent": REPAIR_AGENT_NAME,
            "created_from": "llm_before_key_failure_repair",
            "source_label": source_label,
            "source_provider": llm_result.get("provider"),
            "source_model": llm_result.get("model_name"),
            "source_seeds": [seed],
            "original_success": bool(original_evaluation.get("success")),
            "original_reward": float(original_evaluation.get("reward", 0.0)),
            "repaired_steps": int(repaired_evaluation.get("steps", 0)),
            "key_navigation_steps": repair_plan["key_navigation_steps"],
            "observed_key_actions": [
                {
                    "seed": seed,
                    "actions": list(key_actions),
                }
            ],
        },
    )


def _make_post_key_repair_skill(
    seed: int,
    llm_result: dict[str, Any],
    source_label: str,
    suffix_actions: list[str],
    repair_plan: dict[str, Any],
    original_evaluation: dict[str, Any],
    repaired_evaluation: dict[str, Any],
    source_attribution: dict[str, Any],
) -> SkillRecord:
    return SkillRecord(
        skill_id=POST_KEY_REPAIR_SKILL_ID,
        name="repair_post_key_navigation_to_goal",
        description=(
            "Repair learned from a failed LLM DoorKey policy: preserve the "
            "successful key pickup prefix, navigate from the post-key state to "
            "the goal, then putMarker."
        ),
        task_family="Karel",
        dsl_source=" ".join(suffix_actions),
        ast_json={
            "type": "action_sequence",
            "actions": list(suffix_actions),
        },
        root_nonterminal="ActionSequence",
        semantic_tags=[
            "doorkey",
            "goal",
            "llm_repair",
            "navigation",
            "post_key_navigation",
            "replanner",
        ],
        preconditions=["door_open", "key_picked"],
        postconditions=["goal_topped_off", "success"],
        success_rate=1.0 if repaired_evaluation.get("success") else 0.0,
        mean_reward=float(repaired_evaluation.get("reward", 0.0)),
        num_evaluations=1,
        failure_signatures=[
            "post_key_navigation_failed",
            "wrong_put_marker_position",
            source_attribution["attribution"],
        ],
        metadata={
            "source_agent": REPAIR_AGENT_NAME,
            "created_from": "llm_failed_policy_repair",
            "source_label": source_label,
            "source_provider": llm_result.get("provider"),
            "source_model": llm_result.get("model_name"),
            "source_seeds": [seed],
            "original_success": bool(original_evaluation.get("success")),
            "original_reward": float(original_evaluation.get("reward", 0.0)),
            "repaired_steps": int(repaired_evaluation.get("steps", 0)),
            "preserved_prefix_steps": repair_plan["preserved_prefix_steps"],
            "suffix_actions": list(suffix_actions),
        },
    )


def _merge_repair_observation(
    record: SkillRecord,
    seed: int,
    source_label: str,
    repaired_evaluation: dict[str, Any],
) -> bool:
    source_seeds = list(record.metadata.get("source_seeds", []))
    if seed in source_seeds and record.metadata.get("source_label") == source_label:
        return False

    previous_count = record.num_evaluations
    next_count = previous_count + 1
    success = 1.0 if repaired_evaluation.get("success") else 0.0
    reward = float(repaired_evaluation.get("reward", 0.0))
    record.success_rate = ((record.success_rate * previous_count) + success) / next_count
    record.mean_reward = ((record.mean_reward * previous_count) + reward) / next_count
    record.num_evaluations = next_count
    if seed not in source_seeds:
        source_seeds.append(seed)
        source_seeds.sort()
    record.metadata["source_seeds"] = source_seeds
    record.metadata["last_source_label"] = source_label
    return True


def _merge_key_repair_observation(
    record: SkillRecord,
    seed: int,
    source_label: str,
    key_actions: list[str],
    repaired_evaluation: dict[str, Any],
) -> bool:
    changed = _merge_repair_observation(
        record,
        seed=seed,
        source_label=source_label,
        repaired_evaluation=repaired_evaluation,
    )
    observed_key_actions = list(record.metadata.get("observed_key_actions", []))
    if not any(item.get("seed") == seed for item in observed_key_actions):
        observed_key_actions.append(
            {
                "seed": seed,
                "actions": list(key_actions),
            }
        )
        record.metadata["observed_key_actions"] = observed_key_actions
        changed = True
    return changed
