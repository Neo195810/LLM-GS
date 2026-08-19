from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")

from prog_policies.base.dsl import DSLParseError  # noqa: E402
from prog_policies.karel.dsl import KarelDSL  # noqa: E402
from prog_policies.search_space.latent_space import LatentSpace  # noqa: E402


def _bare_latent_space() -> LatentSpace:
    """Build a LatentSpace without running its heavy LEAPS-model __init__."""
    space = object.__new__(LatentSpace)
    space.dsl = KarelDSL()
    space.sigma = 0.25
    space.np_rng = np.random.RandomState(1)
    space.torch_device = torch.device("cpu")
    space.torch_rng = torch.Generator(device=space.torch_device)
    space.torch_rng.manual_seed(space.np_rng.randint(1000000))
    space.hidden_size = 4
    return space


def _decode_stub(outcomes: list[object]):
    remaining = iter(outcomes)

    def decode(individual: torch.Tensor) -> object:
        outcome = next(remaining)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    return decode


def test_initialize_individual_resamples_past_dsl_parse_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = _bare_latent_space()
    program = object()
    monkeypatch.setattr(
        space,
        "_decode",
        _decode_stub([DSLParseError("program", 0, "x", None, []), program]),
    )

    _, result = space.initialize_individual()

    assert result is program


def test_get_neighbors_resamples_past_dsl_parse_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = _bare_latent_space()
    program = object()
    monkeypatch.setattr(
        space,
        "_decode",
        _decode_stub([DSLParseError("program", 0, "x", None, []), program]),
    )

    [(_, result)] = space.get_neighbors(torch.zeros(4), k=1)

    assert result is program
