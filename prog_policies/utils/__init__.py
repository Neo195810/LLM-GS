KAREL_TASK_NAME_LIST = [
    "StairClimber",
    "StairClimberSparse",
    "Maze",
    "MazeSparse",
    "FourCorners",
    "FourCornersSparse",
    "TopOff",
    "TopOffSparse",
    "Harvester",
    "HarvesterSparse",
    "CleanHouse",
    "CleanHouseSparse",
    "DoorKey",
    "OneStroke",
    "Seeder",
    "Snake",
    "WallAvoider",
    "PathFollow",
]

MINIGRID_TASK_NAME_LIST = ["LavaGap", "RedBlueDoor", "PutNear"]


def get_env_name(task_name: str) -> str:
    """
    Get the environment name based on the task name.

    Args:
        task_name (str): The name of the task.

    Returns:
        str: The environment name.
    """
    if task_name in KAREL_TASK_NAME_LIST:
        return "karel"
    elif task_name in MINIGRID_TASK_NAME_LIST:
        return "minigrid"
    else:
        raise ValueError(f"Unknown task name: {task_name}")
