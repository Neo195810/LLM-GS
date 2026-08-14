"""A narrow, deterministic TextWorld pilot at the V2 adapter boundary."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import textworld  # type: ignore[import-untyped]
from textworld.core import EnvInfos  # type: ignore[import-untyped]
from textworld.generator.game import Event, Quest  # type: ignore[import-untyped]

from llm_gs.contracts import CandidateProgram, EpisodeResult

_RULE = re.compile(
    r"WHEN (not_has_key|has_key|chest_unlocked|chest_open) DO "
    r"(take_key|unlock_chest|open_chest)"
)
_COMMANDS = {
    "take_key": "take key",
    "unlock_chest": "unlock chest with key",
    "open_chest": "open chest",
}
_QUEST_ID = "fixed-key-chest-v1"
_GAME_DIRECTORY: TemporaryDirectory[str] | None = None


@dataclass(frozen=True)
class TextWorldPilotLimits:
    max_actions: int


@dataclass(frozen=True)
class PilotRule:
    predicate: str
    action: str


def parse_program(source: str) -> tuple[PilotRule, ...]:
    """Parse the complete bounded V2 TextWorld pilot DSL, never free text."""
    parts = [part.strip() for part in source.split(";") if part.strip()]
    if not 1 <= len(parts) <= 3:
        raise ValueError("TextWorldPilot requires one to three rules")
    rules: list[PilotRule] = []
    for part in parts:
        match = _RULE.fullmatch(part)
        if match is None:
            raise ValueError("TextWorldPilot contains an unrecognized predicate or action")
        rules.append(PilotRule(*match.groups()))
    if len({rule.action for rule in rules}) != len(rules):
        raise ValueError("TextWorldPilot may not repeat an action")
    return tuple(rules)


def canonical_source(source: str) -> str:
    return "; ".join(f"WHEN {rule.predicate} DO {rule.action}" for rule in parse_program(source))


class TextWorldPilotAdapter:
    """Execute the frozen key-and-chest quest in a compiled TextWorld game."""

    def evaluate(
        self, candidate: CandidateProgram, seed: int, limits: TextWorldPilotLimits
    ) -> EpisodeResult:
        rules = parse_program(candidate.source)
        if limits.max_actions < 1:
            raise ValueError("TextWorldPilot max_actions must be positive")
        environment = textworld.start(_game_file(), request_infos=_REQUEST_INFOS)
        environment.seed(seed)
        state = environment.reset()
        trace: list[str] = []
        failure_reason: str | None = None
        try:
            for rule in rules:
                if len(trace) >= limits.max_actions:
                    failure_reason = "action_limit_reached"
                    break
                if _predicate_holds(rule.predicate, state.facts):
                    command = _COMMANDS[rule.action]
                    state, _, done = environment.step(command)
                    trace.append(command)
                    if state.last_action is None:
                        failure_reason = "invalid_action"
                        break
                    if done:
                        break

            won = bool(state.won)
            lost = bool(state.lost)
            if not won and failure_reason is None:
                failure_reason = "quest_lost" if lost else "quest_incomplete"
            evidence: dict[str, object] = {
                "version": 1,
                "quest_id": _QUEST_ID,
                "textworld_version": textworld.__version__,
                "seed": seed,
                "vocabulary": ["key", "chest"],
                "predicates": ["not_has_key", "has_key", "chest_unlocked", "chest_open"],
                "actions": sorted(_COMMANDS),
                "commands": trace,
                "facts": _render_facts(state.facts),
                "win_facts": _render_fact_sets(state.win_facts),
                "fail_facts": _render_fact_sets(state.fail_facts),
                "won": won,
                "lost": lost,
                "score": state.score,
            }
            terminal_state = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
            if won:
                return EpisodeResult(
                    outcome="success",
                    normalized_progress=1.0,
                    evaluation_evidence=evidence,
                    terminal_state=terminal_state,
                )
            return EpisodeResult(
                outcome="partial_completion",
                normalized_progress=_progress(state.facts),
                failure_type="task_failure",
                failure_reason=failure_reason,
                evaluation_evidence=evidence,
                terminal_state=terminal_state,
            )
        finally:
            environment.close()


_REQUEST_INFOS = EnvInfos(
    facts=True,
    win_facts=True,
    fail_facts=True,
    won=True,
    lost=True,
    score=True,
    last_action=True,
)


@lru_cache(maxsize=1)
def _game_file() -> str:
    """Build one frozen Inform7 game per process and keep it for replays."""
    global _GAME_DIRECTORY
    _GAME_DIRECTORY = TemporaryDirectory(prefix="llm-gs-textworld-")
    maker = textworld.GameMaker()
    vault = maker.new_room("vault")
    maker.set_player(vault)
    key = maker.new(type="k", name="key")
    vault.add(key)
    chest = maker.new(type="c", name="chest")
    chest.add_property("locked")
    chest.add_fact("match", key, chest)
    vault.add(chest)
    maker.quests = [
        Quest(
            win_events=[Event(conditions={maker.new_fact("open", chest)})],
            fail_events=[Event(conditions={maker.new_fact("in", key, chest)})],
        )
    ]
    maker.set_walkthrough(["take key", "unlock chest with key", "open chest"])
    return str(maker.compile(str(Path(_GAME_DIRECTORY.name) / f"{_QUEST_ID}.z8")))


def _predicate_holds(predicate: str, facts: Any) -> bool:
    has_key = _has_fact(facts, "in", "key", "I")
    chest_open = _has_fact(facts, "open", "chest")
    chest_unlocked = chest_open or _has_fact(facts, "closed", "chest")
    values = {
        "not_has_key": not has_key,
        "has_key": has_key,
        "chest_unlocked": chest_unlocked,
        "chest_open": chest_open,
    }
    return values[predicate]


def _has_fact(facts: Any, name: str, *arguments: str) -> bool:
    return any(
        fact.name == name and tuple(argument.name for argument in fact.arguments) == arguments
        for fact in facts
    )


def _render_facts(facts: Any) -> list[str]:
    return sorted(_render_fact(fact) for fact in facts)


def _render_fact_sets(fact_sets: Any) -> list[str]:
    """Flatten TextWorld's quest/alternative/fact nesting for stable evidence."""
    return sorted(
        _render_fact(fact)
        for quest_facts in fact_sets
        for alternative in quest_facts
        for fact in alternative
    )


def _render_fact(fact: Any) -> str:
    return f"{fact.name}({', '.join(argument.name for argument in fact.arguments)})"


def _progress(facts: Any) -> float:
    return sum(
        (
            _has_fact(facts, "in", "key", "I"),
            _has_fact(facts, "closed", "chest") or _has_fact(facts, "open", "chest"),
            _has_fact(facts, "open", "chest"),
        )
    ) / 3
