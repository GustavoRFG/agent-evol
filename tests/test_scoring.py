"""Tests for the scoring helpers."""

from agenteval.core.schemas import WeaknessCode
from agenteval.core.scoring import clamp_score, compute_basic_score


def test_clamp_score_within_range():
    assert clamp_score(0.5) == 0.5


def test_clamp_score_above_max():
    assert clamp_score(1.5) == 1.0


def test_clamp_score_below_min():
    assert clamp_score(-0.5) == 0.0


def test_clamp_score_at_bounds():
    assert clamp_score(0.0) == 0.0
    assert clamp_score(1.0) == 1.0


def test_basic_score_all_tests_passed():
    assert compute_basic_score(True, True) == 1.0


def test_basic_score_no_tests_passed():
    assert compute_basic_score(False, False) == 0.0


def test_basic_score_only_public_passed():
    assert compute_basic_score(True, False) == 0.5


def test_basic_score_only_hidden_passed():
    assert compute_basic_score(False, True) == 0.5


def test_basic_score_weakness_penalty_applied():
    score = compute_basic_score(
        True, True, [WeaknessCode.INST, WeaknessCode.LAZY]
    )
    # 1.0 - 2 * 0.1
    assert score == 0.8


def test_basic_score_never_goes_negative():
    score = compute_basic_score(
        False, False, [WeaknessCode.INST, WeaknessCode.FALSE]
    )
    assert score == 0.0


def test_basic_score_never_exceeds_max():
    score = compute_basic_score(
        True, True, public_weight=0.9, hidden_weight=0.9
    )
    assert score == 1.0


def test_basic_score_accepts_any_iterable_of_weaknesses():
    # A generator is consumed correctly (count-based, not len-based).
    weaknesses = (w for w in [WeaknessCode.TOOL])
    assert compute_basic_score(True, True, weaknesses) == 0.9
