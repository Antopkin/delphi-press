"""Tests for src.schemas.progress — ProgressStage, SSEProgressEvent."""

import pytest
from pydantic import ValidationError

from src.schemas.progress import (
    STAGE_LABELS,
    STAGE_PROGRESS_MAP,
    ProgressStage,
    SSEProgressEvent,
)

# ── ProgressStage ────────────────────────────────────────────────────


def test_progress_stage_has_12_values():
    assert len(ProgressStage) == 12


def test_progress_stage_map_keys_match_members():
    assert set(STAGE_PROGRESS_MAP.keys()) == set(ProgressStage)


def test_stage_labels_keys_match_members():
    assert set(STAGE_LABELS.keys()) == set(ProgressStage)


# ── SSEProgressEvent ─────────────────────────────────────────────────


def test_sse_progress_event_valid():
    evt = SSEProgressEvent(
        stage=ProgressStage.COLLECTION,
        message="Collecting data",
        progress=0.15,
    )
    assert evt.progress == 0.15


def test_sse_progress_event_progress_above_1_rejected():
    with pytest.raises(ValidationError):
        SSEProgressEvent(
            stage=ProgressStage.COLLECTION,
            message="Collecting data",
            progress=1.01,
        )


def test_sse_progress_event_progress_below_0_rejected():
    with pytest.raises(ValidationError):
        SSEProgressEvent(
            stage=ProgressStage.COLLECTION,
            message="Collecting data",
            progress=-0.1,
        )
