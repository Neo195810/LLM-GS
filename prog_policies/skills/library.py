"""A persistent, embedding-retrieved skill memory for programmatic policies.

Skills are JSON records rather than pickles so that they are inspectable, portable and
safe to share between experiments.  A skill is always a syntactically valid complete
DSL program: subtrees are wrapped in ``DEF run`` before being stored.
"""
from __future__ import annotations

import json
import math
import re
from urllib.error import URLError
from urllib.request import Request, urlopen
from pathlib import Path
from typing import Iterable

from prog_policies.base import dsl_nodes


class SkillLibrary:
    """Extract, rank and persist verified DSL fragments.

    Skills are retrieved with cosine similarity over Ollama embeddings.  Vectors are
    kept beside their metadata in JSON, making the library portable and avoiding a
    separate vector-database service for the small task collections in LLM-GS.
    """

    VERSION = 1

    def __init__(
        self,
        path: str | Path,
        environment: str,
        embedding_model: str = "nomic-embed-text",
        embedding_url: str = "http://localhost:11434",
        embedding_fn=None,
    ) -> None:
        self.path = Path(path)
        self.environment = environment
        self.embedding_model = embedding_model
        self.embedding_url = embedding_url.rstrip("/")
        self.embedding_fn = embedding_fn
        self.records = self._load()

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("version") != self.VERSION:
                raise ValueError("unsupported skill library version")
            return payload.get("skills", [])
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            raise ValueError(f"Cannot read skill library {self.path}: {exc}") from exc

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps({"version": self.VERSION, "skills": self.records}, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)

    def _embed(self, text: str) -> list[float]:
        if self.embedding_fn is not None:
            return list(self.embedding_fn(text))
        payload = json.dumps({"model": self.embedding_model, "input": text}).encode("utf-8")
        request = Request(
            f"{self.embedding_url}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                vectors = json.loads(response.read().decode("utf-8"))["embeddings"]
            return list(vectors[0])
        except (URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Embedding failed with Ollama model '{self.embedding_model}'. "
                f"Start Ollama and run: ollama pull {self.embedding_model}"
            ) from exc

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            raise ValueError("Skill embedding dimensions do not match the query embedding.")
        denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
        return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0

    @staticmethod
    def _record_text(record: dict) -> str:
        return "\n".join((
            "Task(s): " + ", ".join(record.get("source_tasks", [])),
            "Task context: " + record.get("source_task_context", ""),
            "Skill: " + record.get("description", ""),
            "DSL program: " + record["dsl_program"],
        ))

    @staticmethod
    def _description(node: dsl_nodes.BaseNode, dsl) -> str:
        text = dsl.parse_node_to_str(node)
        actions = re.findall(r"\b(move|turnLeft|turnRight|pickMarker|putMarker|forward|left|right|pickup|drop|toggle)\b", text)
        controls = []
        if "WHILE" in text:
            controls.append("loop")
        if "IF" in text:
            controls.append("conditional")
        if "REPEAT" in text:
            controls.append("repeat")
        pieces = ", ".join(controls) if controls else "action sequence"
        action_text = ", ".join(dict.fromkeys(actions)) or "navigation"
        return f"Verified {pieces} using {action_text}."

    @staticmethod
    def _complete_program(node: dsl_nodes.BaseNode, dsl) -> str:
        if isinstance(node, dsl_nodes.Program):
            return dsl.parse_node_to_str(node)
        return "DEF run m( " + dsl.parse_node_to_str(node) + " m)"

    def extract_and_store(self, program, reward: float, task: str, dsl, task_context: str = "") -> int:
        """Store the whole solution plus non-trivial statement subtrees.

        This is called only after the candidate has been evaluated by the actual task
        environments, so every stored record inherits that verification result.
        """
        candidates: list[tuple[str, dsl_nodes.BaseNode]] = [("program", program)]
        for node in program.get_all_nodes():
            if isinstance(node, dsl_nodes.StatementNode) and not isinstance(
                node, (dsl_nodes.Program, dsl_nodes.Action, dsl_nodes.Concatenate)
            ) and node.is_complete():
                candidates.append(("fragment", node))

        added = 0
        existing = {r["dsl_program"]: r for r in self.records if r.get("environment") == self.environment}
        for kind, node in candidates:
            dsl_program = self._complete_program(node, dsl)
            if dsl_program in existing:
                record = existing[dsl_program]
                record["best_reward"] = max(record["best_reward"], float(reward))
                record["uses"] = record.get("uses", 1) + 1
                if task not in record["source_tasks"]:
                    record["source_tasks"].append(task)
                    record.pop("embedding", None)
                continue
            record = {
                "environment": self.environment,
                "kind": kind,
                "description": self._description(node, dsl),
                "dsl_program": dsl_program,
                "best_reward": float(reward),
                "source_tasks": [task],
                "source_task_context": task_context,
                "uses": 1,
            }
            record["embedding"] = self._embed(self._record_text(record))
            self.records.append(record)
            existing[dsl_program] = record
            added += 1
        self._save()
        return added

    def retrieve(self, task: str, task_context: str = "", limit: int = 3) -> list[dict]:
        """Return same-environment verified skills by embedding cosine similarity."""
        query_embedding = self._embed(f"Task: {task}\nTask context: {task_context}")
        scored = []
        changed = False
        for record in self.records:
            if record.get("environment") != self.environment:
                continue
            if "embedding" not in record:
                record["embedding"] = self._embed(self._record_text(record))
                changed = True
            scored.append((self._cosine_similarity(query_embedding, record["embedding"]), record))
        if changed:
            self._save()
        results = []
        for score, record in sorted(scored, key=lambda item: (-item[0], item[1]["dsl_program"]))[:limit]:
            result = dict(record)
            result["retrieval_score"] = score
            results.append(result)
        return results

    @staticmethod
    def prompt_block(skills: Iterable[dict]) -> str:
        skills = list(skills)
        if not skills:
            return ""
        lines = ["\nVerified reusable DSL skills (adapt or compose them; output a complete program):"]
        for index, skill in enumerate(skills, 1):
            lines.extend((f"Skill {index}: {skill['description']}", skill["dsl_program"]))
        return "\n".join(lines)
