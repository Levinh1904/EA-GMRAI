"""Chronological splits + purge/embargo — leakage guards."""
import pytest

from app.ml.splits import (
    WalkForwardConfig,
    chronological_indices,
    purge_train_indices,
    sub_train_val_split,
    walk_forward_folds,
)


def test_chronological_disjoint_and_ordered():
    split = chronological_indices(1000, 0.6, 0.2)
    train, val, test = split["train"], split["val"], split["test"]
    assert train == (0, 600)
    assert val == (600, 800)
    assert test == (800, 1000)
    assert train[1] <= val[0] <= val[1] <= test[0]


def test_chronological_rejects_full_cover():
    with pytest.raises(ValueError):
        chronological_indices(1000, 0.7, 0.5)


def test_purge_embargo():
    # embargo = label horizon h: train must end at least h bars before test start
    assert purge_train_indices(100, 12) == (0, 88)


def test_walk_forward_folds():
    n = 3000
    cfg = WalkForwardConfig(initial_train=1500, test_size=500, embargo=12)
    folds = walk_forward_folds(n, cfg)
    assert folds, "expected at least one fold"
    prev_test_end = -1
    for f in folds:
        train, test = f["train"], f["test"]
        assert train == (0, test[0] - cfg.embargo), "train must be purged by embargo"
        assert test[1] - test[0] == cfg.test_size
        assert test[0] > prev_test_end, "test folds must not overlap"
        prev_test_end = test[1]
    assert folds[-1]["test"][1] <= n


def test_walk_forward_too_small():
    n = 1000
    cfg = WalkForwardConfig(initial_train=2000, test_size=500, embargo=12)
    assert walk_forward_folds(n, cfg) == []


def test_subtrain_subval():
    sub = sub_train_val_split((0, 1000), 0.2)
    assert sub["subtrain"] == (0, 800)
    assert sub["subval"] == (800, 1000)
