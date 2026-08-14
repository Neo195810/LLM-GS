from __future__ import annotations

from dataclasses import dataclass

from prog_policies.karel import KarelEnvironment


@dataclass(frozen=True)
class DoorKeyState:
    agent: tuple[int, int, int]
    key_cell: tuple[int, int] | None
    goal_cell: tuple[int, int] | None
    wall_column: int
    door_open: bool


def extract_doorkey_state(env: KarelEnvironment) -> DoorKeyState:
    """Read the Karel DoorKey layout from the boolean state tensor."""

    hero_row, hero_col, hero_dir = env.get_hero_pos()
    wall_column = _find_divider_wall_column(env)
    marker_cells = _marker_cells(env)
    key_cell = _first_cell(cell for cell in marker_cells if cell[1] < wall_column)
    goal_cell = _first_cell(cell for cell in marker_cells if cell[1] > wall_column)

    return DoorKeyState(
        agent=(int(hero_row), int(hero_col), int(hero_dir)),
        key_cell=key_cell,
        goal_cell=goal_cell,
        wall_column=wall_column,
        door_open=_door_open(env, wall_column),
    )


def _find_divider_wall_column(env: KarelEnvironment) -> int:
    _, height, width = env.state_shape
    interior_columns = range(1, width - 1)
    return max(
        interior_columns,
        key=lambda col: int(env.state[4, 1 : height - 1, col].sum()),
    )


def _marker_cells(env: KarelEnvironment) -> list[tuple[int, int]]:
    rows, cols = env.markers_grid.shape
    return [
        (int(row), int(col))
        for row in range(rows)
        for col in range(cols)
        if env.markers_grid[row, col] > 0
    ]


def _door_open(env: KarelEnvironment, wall_column: int) -> bool:
    _, height, _ = env.state_shape
    return any(not env.state[4, row, wall_column] for row in range(1, height - 1))


def _first_cell(cells) -> tuple[int, int] | None:
    for cell in cells:
        return cell
    return None
