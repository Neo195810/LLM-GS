import numpy as np
import pytest
from minigrid.envs import EmptyEnv

from prog_policies.base import BaseEnvironment, BaseTask, ProgramCallLimitExceeded, dsl_nodes
from prog_policies.minigrid.wrapper import ProgramWrapper


class CountingEnvironment(BaseEnvironment):
    def __init__(self, max_calls: int = 2, explode: bool = False):
        self.state = 0
        self.explode = explode
        super().__init__(
            {"increment": self.increment},
            {"always": lambda: True, "explode": self.raise_error},
            {"one": lambda: 1},
            state_shape=(1,),
            max_calls=max_calls,
        )

    def default_state(self):
        return 0

    def get_state(self):
        return self.state

    def set_state(self, state):
        self.state = state

    def hash(self):
        return str(self.state)

    def increment(self):
        self.state += 1

    def raise_error(self):
        if self.explode:
            raise ValueError("unexpected runtime error")
        return True

    def to_image(self, grid_size: int = 100, root_dir: str = "./"):
        return np.zeros((1, 1, 3), dtype=np.uint8)

    def to_string_worldcoder_style(self, state=None):
        return str(self.state)

    def record_partial_state(self):
        return str(self.state)

    @classmethod
    def from_string(cls, state_str: str):
        return cls()

    def __eq__(self, other):
        return isinstance(other, CountingEnvironment) and self.state == other.state


class CountingTask(BaseTask):
    def generate_initial_environment(self, env_args):
        return CountingEnvironment(**env_args)

    def get_reward(self, environment):
        return False, 0.0


def repeated_action_program() -> dsl_nodes.Program:
    return dsl_nodes.Program.new(
        dsl_nodes.Repeat.new(
            dsl_nodes.ConstInt(3), dsl_nodes.Action("increment")
        )
    )


def test_indexed_action_uses_standard_action_execution_path() -> None:
    wrapper = ProgramWrapper(EmptyEnv(size=5), seed=0, crashable=True)
    wrapper.reset()

    wrapper.run_action_index(wrapper.actions_list.index("pickup"))

    assert wrapper.is_crashed()
    assert wrapper.stop_reason == "invalid_action"
    assert wrapper.program_call_count == 1


def test_minigrid_evaluation_stops_after_invalid_action_before_following_predicate() -> None:
    wrapper = ProgramWrapper(EmptyEnv(size=5), seed=0, crashable=True)
    program = dsl_nodes.Program.new(
        dsl_nodes.Concatenate.new(
            dsl_nodes.Action("pickup"),
            dsl_nodes.If.new(
                dsl_nodes.BoolFeature("front_is_clear"), dsl_nodes.Action("left")
            ),
        )
    )

    wrapper.evaluate_program(program)

    assert wrapper.stop_reason == "invalid_action"
    assert wrapper.program_call_count == 1
    assert wrapper.attempted_program_call_count == 1


def test_indexed_action_stops_before_the_call_after_the_limit() -> None:
    wrapper = ProgramWrapper(EmptyEnv(size=5), seed=0, max_calls=2)
    wrapper.reset()
    left_index = wrapper.actions_list.index("left")

    wrapper.run_action_index(left_index)
    wrapper.run_action_index(left_index)

    with pytest.raises(ProgramCallLimitExceeded):
        wrapper.run_action_index(left_index)

    assert wrapper.program_call_count == 2
    assert wrapper.attempted_program_call_count == 3
    assert wrapper.stop_reason == "call_limit_exhausted"


def test_minigrid_trace_absorbs_the_expected_call_limit_exception() -> None:
    wrapper = ProgramWrapper(EmptyEnv(size=5), seed=0, max_calls=2)
    program = dsl_nodes.Program.new(
        dsl_nodes.Repeat.new(dsl_nodes.ConstInt(3), dsl_nodes.Action("left"))
    )

    frames = wrapper.trace_program(program)

    assert len(frames) == 3
    assert wrapper.program_call_count == 2
    assert wrapper.attempted_program_call_count == 3
    assert wrapper.stop_reason == "call_limit_exhausted"


@pytest.mark.parametrize(
    "call",
    [
        lambda env: env.run_action("increment"),
        lambda env: env.get_bool_feature("always"),
        lambda env: env.get_int_feature("one"),
        lambda env: env.run_action_index(0),
    ],
)
def test_all_base_environment_call_paths_stop_before_n_plus_one(call) -> None:
    environment = CountingEnvironment(max_calls=2)
    call(environment)
    call(environment)
    state_after_limit = environment.state

    with pytest.raises(ProgramCallLimitExceeded):
        call(environment)

    assert environment.state == state_after_limit
    assert environment.program_call_count == 2
    assert environment.attempted_program_call_count == 3
    assert environment.stop_reason == "call_limit_exhausted"


def test_nested_repeat_while_and_if_stop_at_the_call_limit() -> None:
    program = dsl_nodes.Program.new(
        dsl_nodes.Repeat.new(
            dsl_nodes.ConstInt(3),
            dsl_nodes.While.new(
                dsl_nodes.ConstBool(True),
                dsl_nodes.If.new(
                    dsl_nodes.ConstBool(True), dsl_nodes.Action("increment")
                ),
            ),
        )
    )
    environment = CountingEnvironment(max_calls=2)

    with pytest.raises(ProgramCallLimitExceeded):
        list(program.run_generator(environment))

    assert environment.state == 2
    assert environment.stop_reason == "call_limit_exhausted"


@pytest.mark.parametrize("condition", [True, False])
def test_if_else_branches_cannot_continue_after_the_call_limit(condition: bool) -> None:
    program = dsl_nodes.Program.new(
        dsl_nodes.Repeat.new(
            dsl_nodes.ConstInt(3),
            dsl_nodes.ITE.new(
                dsl_nodes.ConstBool(condition),
                dsl_nodes.Action("increment"),
                dsl_nodes.Action("increment"),
            ),
        )
    )
    environment = CountingEnvironment(max_calls=2)

    with pytest.raises(ProgramCallLimitExceeded):
        list(program.run_generator(environment))

    assert environment.state == 2
    assert environment.stop_reason == "call_limit_exhausted"


def test_repeated_state_is_classified_as_stalled_not_limit() -> None:
    program = dsl_nodes.Program.new(
        dsl_nodes.While.new(dsl_nodes.ConstBool(True), dsl_nodes.Action("increment"))
    )
    environment = CountingEnvironment(max_calls=10)
    environment.actions["increment"] = lambda: None

    assert list(program.run_generator(environment)) == [program.children[0].children[1]]
    assert environment.stop_reason == "stalled_policy"
    assert environment.program_call_count == 1


def test_base_task_generator_consumers_absorb_only_limit_exceptions() -> None:
    task = CountingTask(env_args={"max_calls": 2})
    program = repeated_action_program()

    assert task.evaluate_program(program) == 0.0
    assert task.evaluate_and_assign_credit(program)[0] == 0.0
    assert task.record_evaluate_program(program)[0] == 0.0
    assert len(task.trace_program(program, save=False)) == 2


def test_unexpected_runtime_exceptions_propagate_from_evaluation() -> None:
    task = CountingTask(env_args={"explode": True})
    program = dsl_nodes.Program.new(
        dsl_nodes.If.new(dsl_nodes.BoolFeature("explode"), dsl_nodes.Action("increment"))
    )

    with pytest.raises(ValueError, match="unexpected runtime error"):
        task.evaluate_program(program)


def test_program_wrapper_propagates_unexpected_runtime_exceptions() -> None:
    wrapper = ProgramWrapper(EmptyEnv(size=5), seed=0)
    wrapper.bool_features["explode"] = lambda: (_ for _ in ()).throw(
        ValueError("unexpected runtime error")
    )
    wrapper.has_parameters["explode"] = False
    program = dsl_nodes.Program.new(
        dsl_nodes.If.new(dsl_nodes.BoolFeature("explode"), dsl_nodes.Action("left"))
    )

    with pytest.raises(ValueError, match="unexpected runtime error"):
        wrapper.evaluate_program(program)
