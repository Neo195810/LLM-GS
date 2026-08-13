def get_env_name(task_name: str) -> str:
    """
    Get the environment name based on the task name.

    Args:
        task_name (str): The name of the task.

    Returns:
        str: The environment name.
    """
    # Import task registries lazily.  Besides avoiding a BaseTask import cycle during
    # DSL construction, this lets Karel-only experiments run without Minigrid extras.
    from ..karel_tasks import TASK_NAME_LIST as KAREL_TASK_NAME_LIST

    if task_name in KAREL_TASK_NAME_LIST:
        return "karel"
    from ..minigrid_tasks import TASK_NAME_LIST as MINIGRID_TASK_NAME_LIST
    if task_name in MINIGRID_TASK_NAME_LIST:
        return "minigrid"
    else:
        raise ValueError(f"Unknown task name: {task_name}")
