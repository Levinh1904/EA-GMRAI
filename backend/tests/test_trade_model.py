"""Walk-forward split invariants (no test/holdout leakage)."""
from __future__ import annotations

from app.ml.trade_model import HOLDOUT_BARS, make_folds


def test_four_contiguous_test_folds_and_untouched_holdout():
    n = 23056
    folds, n_dev = make_folds(n)
    assert len(folds) == 4
    assert n_dev == n - min(HOLDOUT_BARS, n // 20)
    assert folds[0]["test"][0] > folds[0]["sel"][1]
    for a, b in zip(folds, folds[1:]):
        assert a["test"][1] == b["test"][0]
    assert folds[-1]["test"][1] == n_dev
    for f in folds:
        assert f["train"][1] < f["es"][0]
        assert f["es"][1] < f["sel"][0]
        assert f["sel"][1] < f["test"][0]
