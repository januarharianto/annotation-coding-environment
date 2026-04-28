"""Tests for agreement_verdict module."""

import pytest

from ace.services.agreement_types import AgreementResult, CodeMetrics
from ace.services.agreement_verdict import (
    CodeVerdict,
    OverallVerdict,
    classify_code,
    classify_overall,
)


def _make_metrics(
    ac1: float | None = 0.85,
    alpha: float | None = 0.80,
    agree: float = 0.90,
    n_positions: int = 200,
    n_sources: int = 5,
    cohens_kappa: float | None = 0.80,
    congers_kappa: float | None = 0.80,
    brennan_prediger: float | None = 0.80,
) -> CodeMetrics:
    return CodeMetrics(
        percent_agreement=agree,
        n_positions=n_positions,
        n_sources=n_sources,
        cohens_kappa=cohens_kappa,
        krippendorffs_alpha=alpha,
        fleiss_kappa=None,
        congers_kappa=congers_kappa,
        gwets_ac1=ac1,
        brennan_prediger=brennan_prediger,
    )


def _make_result(
    overall_ac1: float | None,
    per_code_ac1s: dict[str, float | None],
) -> tuple[AgreementResult, dict[str, CodeVerdict]]:
    """Build a minimal AgreementResult and classify per-code verdicts."""
    per_code: dict[str, CodeMetrics] = {}
    for name, ac1 in per_code_ac1s.items():
        per_code[name] = _make_metrics(ac1=ac1)

    overall = _make_metrics(ac1=overall_ac1)

    result = AgreementResult(
        overall=overall,
        per_code=per_code,
        per_source={},
        pairwise={},
        n_coders=2,
        n_sources=5,
        n_codes=len(per_code),
    )
    code_verdicts = {name: classify_code(m) for name, m in per_code.items()}
    return result, code_verdicts


# --- classify_code tests ---


def test_reliable_code():
    m = _make_metrics(ac1=0.91)
    v = classify_code(m)
    assert v.status == "reliable"
    assert v.colour == "green"
    assert v.paradox is False


def test_tentative_code():
    m = _make_metrics(ac1=0.72)
    v = classify_code(m)
    assert v.status == "tentative"
    assert v.colour == "amber"


def test_unreliable_code():
    m = _make_metrics(ac1=0.41)
    v = classify_code(m)
    assert v.status == "unreliable"
    assert v.colour == "red"


def test_insufficient_data():
    m = _make_metrics(ac1=0.90, n_positions=30)
    v = classify_code(m)
    assert v.status == "insufficient"
    assert v.colour == "grey"


def test_paradox_detected():
    # AC1 >= 0.70, alpha < 0.60, agree >= 0.85 → paradox
    m = _make_metrics(ac1=0.88, alpha=0.41, agree=0.93)
    v = classify_code(m)
    assert v.paradox is True
    assert v.status == "reliable"
    assert "artefact" in v.guidance


def test_no_paradox_when_ac1_low():
    # AC1 < 0.70 → paradox condition not met even with high agree and low alpha
    m = _make_metrics(ac1=0.55, alpha=0.30, agree=0.86)
    v = classify_code(m)
    assert v.paradox is False


def test_ac1_none_falls_to_insufficient():
    m = _make_metrics(ac1=None)
    v = classify_code(m)
    assert v.status == "insufficient"
    assert v.colour == "grey"


# --- classify_overall tests ---


def test_overall_green_all_reliable():
    result, verdicts = _make_result(0.88, {"Code A": 0.85, "Code B": 0.90})
    ov = classify_overall(result, verdicts)
    assert ov.colour == "green"
    assert "strong" in ov.paragraphs[0].lower()


def test_overall_green_with_amber():
    result, verdicts = _make_result(0.82, {"Code A": 0.85, "Code B": 0.70})
    ov = classify_overall(result, verdicts)
    assert ov.colour == "green"
    # amber code name should appear in one of the paragraphs
    assert any("Code B" in p for p in ov.paragraphs)


def test_overall_amber_no_reds():
    result, verdicts = _make_result(0.65, {"Code A": 0.85, "Code B": 0.70})
    ov = classify_overall(result, verdicts)
    assert ov.colour == "amber"
    assert not any("red" in p.lower() and "flagged" in p.lower() for p in ov.paragraphs)


def test_overall_amber_with_reds():
    result, verdicts = _make_result(0.65, {"Code A": 0.85, "Code B": 0.70, "Code C": 0.40})
    ov = classify_overall(result, verdicts)
    assert ov.colour == "amber"
    # red code name should appear in one of the paragraphs
    assert any("Code C" in p for p in ov.paragraphs)


def test_overall_red():
    result, verdicts = _make_result(0.40, {"Code A": 0.38, "Code B": 0.42})
    ov = classify_overall(result, verdicts)
    assert ov.colour == "red"
    assert any("revision" in p.lower() or "revise" in p.lower() for p in ov.paragraphs)


def test_overall_grey():
    result, verdicts = _make_result(None, {"Code A": 0.85})
    ov = classify_overall(result, verdicts)
    assert ov.colour == "grey"
