"""Chronological splits with purge/embargo — no shuffling, no leakage."""
from __future__ import annotations

from dataclasses import dataclass


def chronological_indices(n: int, train_frac: float, val_frac: float) -> dict[str, tuple[int, int]]:
    """Return (start, end) exclusive ranges for train/val/test in time order."""
    if train_frac + val_frac >= 1.0:
        raise ValueError("train_frac + val_frac must be < 1.0")
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    return {"train": (0, train_end), "val": (train_end, val_end), "test": (val_end, n)}


@dataclass
class WalkForwardConfig:
    initial_train: int  # bars of initial training window
    test_size: int  # bars per test fold
    step: int | None = None  # default = test_size (non-overlapping folds)
    embargo: int = 12  # bars removed between train end and test start
    min_train: int = 1000

    def __post_init__(self):
        if self.step is None:
            self.step = self.test_size


def walk_forward_folds(n: int, cfg: WalkForwardConfig) -> list[dict[str, tuple[int, int]]]:
    """Expanding-window folds: train [0, t-embargo), test [t, t+test_size)."""
    folds = []
    train_end = cfg.initial_train
    while train_end + cfg.embargo + cfg.test_size <= n:
        test_start = train_end + cfg.embargo
        folds.append({"train": (0, train_end), "test": (test_start, test_start + cfg.test_size)})
        train_end = test_start + cfg.test_size
    return folds


def purge_train_indices(test_start: int, embargo: int) -> tuple[int, int]:
    """Train indices that are safe w.r.t. a test window starting at test_start.

    Labels use `embargo` future bars, so any train sample at index >= test_start - embargo
    would leak label information into the test window (purge/embargo rule).
    """
    return (0, max(0, test_start - embargo))


def sub_train_val_split(train: tuple[int, int], val_frac: float = 0.2) -> dict[str, tuple[int, int]]:
    """Split a train range into subtrain/subval, both respecting the same chronological order."""
    start, end = train
    cut = start + int((end - start) * (1.0 - val_frac))
    return {"subtrain": (start, cut), "subval": (cut, end)}


def purged_subtrain_subval(
    train: tuple[int, int],
    val: tuple[int, int],
    embargo: int,
) -> dict[str, tuple[int, int]]:
    """Train/validation regions purged at BOTH boundaries by the label horizon.

    Labels at bar i use prices up to i+embargo, so the last `embargo` bars of
    each region would leak their label into the next region. Those bars are
    dropped from the earlier region (never from the later one, which stays a
    strict out-of-sample target).

    Raises ValueError when a region becomes empty (not enough data for a
    leak-free split — callers must not silently train on leaking data).
    """
    sub_start, train_end = train
    _, val_end = val
    subtrain = (sub_start, max(sub_start, train_end - embargo))
    subval = (train_end, max(train_end, val_end - embargo))
    if subtrain[1] - subtrain[0] < 1:
        raise ValueError(f"Empty purged subtrain region: {subtrain}")
    if subval[1] - subval[0] < 1:
        raise ValueError(f"Empty purged subval region: {subval} (need more data)")
    return {"subtrain": subtrain, "subval": subval}
