from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Union, Callable

import numpy as np


class ProgramCallLimitExceeded(RuntimeError):
    """Raised before an attempted program call would exceed its policy limit."""


class BaseEnvironment(ABC):
    
    def __init__(self, actions: dict[str, Callable], bool_features: dict[str, Callable],
                 int_features: dict[str, Callable], state_shape: tuple[int, ...],
                 initial_state: Union[Any, None] = None, max_calls: int = 10000):
        self.actions = actions
        self.actions_list = list(actions.keys())
        self.bool_features = bool_features
        self.bool_features_list = list(bool_features.keys())
        self.int_features = int_features
        self.int_features_list = list(int_features.keys())
        self.max_calls = max_calls
        self.state_shape = state_shape
        self.num_calls: int = 0
        self.program_call_count: int = 0
        self.attempted_program_call_count: int = 0
        self.crashed: bool = False
        self.stop_reason: str | None = None
        if initial_state is not None:
            self.set_state(initial_state)
        else:
            self.set_state(self.default_state())

    def is_crashed(self) -> bool:
        return self.crashed
    
    def crash(self, reason: str = "environment_crash"):
        self.crashed = True
        self.stop_reason = reason

    def _register_program_call(self) -> None:
        """Count a call and stop before it can have side effects past the limit."""
        self.attempted_program_call_count += 1
        if self.attempted_program_call_count > self.max_calls:
            self.crash("call_limit_exhausted")
            raise ProgramCallLimitExceeded(
                f"Program call limit ({self.max_calls}) exceeded"
            )
        self.program_call_count += 1
        # ``num_calls`` is a compatibility name used by older callers.
        self.num_calls = self.program_call_count

    def get_bool_feature(self, feature: str):
        self._register_program_call()
        return self.bool_features[feature]()

    def get_int_feature(self, feature: str):
        self._register_program_call()
        return self.int_features[feature]()

    def run_action(self, action: str):
        self._register_program_call()
        self.actions[action]()
        
    def run_action_index(self, action_index: int):
        self._register_program_call()
        self.actions[self.actions_list[action_index]]()

    @abstractmethod
    def default_state(self):
        pass

    @abstractmethod
    def get_state(self):
        pass

    @abstractmethod
    def set_state(self):
        pass
    
    @abstractmethod
    def __eq__(self, other: BaseEnvironment) -> bool:
        pass

    @classmethod
    @abstractmethod
    def from_string(cls, state_str: str):
        pass


    @abstractmethod
    def to_image(self, grid_size: int = 100, root_dir: str = "./") -> np.ndarray:
        pass

    @abstractmethod
    def to_string_worldcoder_style(self, state: np.ndarray = None) -> str:
        # The prompt of Grid-based Environment is from the paper "WorldCoder" arXiv:2402.12275
        pass
    
    # For record
    @abstractmethod    
    def record_partial_state(self) -> str:
        pass
