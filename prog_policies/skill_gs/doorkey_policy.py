from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from prog_policies.karel import KarelEnvironment

from .doorkey_state import extract_doorkey_state


ACTION_NAMES = {"move", "turnLeft", "turnRight", "pickMarker", "putMarker"}
MOVE_DELTAS = {
    0: (-1, 0),
    1: (0, 1),
    2: (1, 0),
    3: (0, -1),
}


class NoDoorKeyPathError(RuntimeError):
    pass


@dataclass
class DoorKeyFixedPolicy:
    key_cell: tuple[int, int]
    goal_cell: tuple[int, int]

    @classmethod
    def from_environment(cls, env: KarelEnvironment) -> "DoorKeyFixedPolicy":
        snapshot = extract_doorkey_state(env)
        if snapshot.key_cell is None:
            raise ValueError("Could not locate DoorKey key marker in the left chamber.")
        if snapshot.goal_cell is None:
            raise ValueError("Could not locate DoorKey goal marker in the right chamber.")
        return cls(key_cell=snapshot.key_cell, goal_cell=snapshot.goal_cell)

    def next_action(self, env: KarelEnvironment) -> str | None:
        if env.markers_grid[self.key_cell[0], self.key_cell[1]] > 0:
            if _agent_cell(env) == self.key_cell:
                return "pickMarker"
            return _shortest_path_actions(env, self.key_cell)[0]

        if _agent_cell(env) == self.goal_cell:
            return "putMarker"

        return _shortest_path_actions(env, self.goal_cell)[0]


def _agent_cell(env: KarelEnvironment) -> tuple[int, int]:
    row, col, _ = env.get_hero_pos()
    return int(row), int(col)


def _shortest_path_actions(
    env: KarelEnvironment, target: tuple[int, int]
) -> list[str]:
    start = tuple(int(value) for value in env.get_hero_pos())
    queue = deque([(start, [])])
    visited = {start}

    while queue:
        state, actions = queue.popleft()
        row, col, direction = state
        if (row, col) == target:
            return actions

        for action, next_state in _neighbors(env, state):
            if next_state in visited:
                continue
            visited.add(next_state)
            queue.append((next_state, [*actions, action]))

    raise NoDoorKeyPathError(f"No safe path to target cell {target}.")


def _neighbors(env: KarelEnvironment, state: tuple[int, int, int]):
    row, col, direction = state

    yield "turnLeft", (row, col, (direction - 1) % 4)
    yield "turnRight", (row, col, (direction + 1) % 4)

    delta_row, delta_col = MOVE_DELTAS[direction]
    next_row = row + delta_row
    next_col = col + delta_col
    if env.is_clear(next_row, next_col):
        yield "move", (next_row, next_col, direction)
