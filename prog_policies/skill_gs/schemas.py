from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SkillRecord:
    """A reusable DSL subtree plus metadata for retrieval and evaluation."""

    skill_id: str
    name: str
    description: str
    task_family: str
    dsl_source: str
    ast_json: dict[str, Any] = field(default_factory=dict)
    root_nonterminal: str = "StatementNode"
    semantic_tags: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    success_rate: float = 0.0
    mean_reward: float = 0.0
    num_evaluations: int = 0
    failure_signatures: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1

    @property
    def complexity(self) -> int:
        return len(self.dsl_source.split())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillRecord":
        return cls(**data)


@dataclass
class SkillQuery:
    """Retrieval request produced by the planner or critic."""

    task: str
    subgoal: str
    context_tags: list[str] = field(default_factory=list)
    required_preconditions: list[str] = field(default_factory=list)
    failure_signature: str | None = None
    root_nonterminal: str | None = None
    top_k: int = 3


@dataclass
class RetrievedSkill:
    skill: SkillRecord
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class SkillPlanStep:
    subgoal: str
    skill_id: str | None
    skill_name: str | None
    dsl_source: str | None
    reason: str


@dataclass
class SkillPlan:
    task: str
    subgoals: list[str]
    steps: list[SkillPlanStep]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Critique:
    success: bool
    failure_type: str
    failed_subgoal: str | None
    failed_node_id: int | None
    repair_operator: str
    repair_hint: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
