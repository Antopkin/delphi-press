"""Tests for src.db.models — ORM models and enums."""

from __future__ import annotations


# ── Enums ───────────────────────────────────────────────────────────


def test_prediction_status_enum_values():
    from src.db.models import PredictionStatus

    values = {s.value for s in PredictionStatus}
    expected = {
        "pending",
        "collecting",
        "analyzing",
        "forecasting",
        "generating",
        "completed",
        "failed",
    }
    assert values == expected


def test_pipeline_step_status_enum_values():
    from src.db.models import PipelineStepStatus

    values = {s.value for s in PipelineStepStatus}
    expected = {"running", "completed", "failed", "skipped"}
    assert values == expected


# ── Model columns ──────────────────────────────────────────────────


def test_prediction_has_expected_columns():
    from src.db.models import Prediction

    cols = {c.name for c in Prediction.__table__.columns}
    required = {
        "id",
        "outlet_name",
        "outlet_normalized",
        "target_date",
        "status",
        "created_at",
        "completed_at",
        "total_duration_ms",
        "total_llm_cost_usd",
        "error_message",
        "pipeline_config",
    }
    assert required.issubset(cols)


def test_headline_has_expected_columns():
    from src.db.models import Headline

    cols = {c.name for c in Headline.__table__.columns}
    required = {
        "id",
        "prediction_id",
        "rank",
        "headline_text",
        "first_paragraph",
        "confidence",
        "confidence_label",
        "category",
        "reasoning",
        "evidence_chain",
        "dissenting_views",
        "agent_agreement",
    }
    assert required.issubset(cols)


def test_pipeline_step_has_expected_columns():
    from src.db.models import PipelineStep

    cols = {c.name for c in PipelineStep.__table__.columns}
    required = {
        "id",
        "prediction_id",
        "agent_name",
        "step_order",
        "status",
        "duration_ms",
        "llm_model_used",
        "llm_tokens_in",
        "llm_tokens_out",
        "llm_cost_usd",
        "output_data",
        "error_message",
    }
    assert required.issubset(cols)


def test_outlet_has_expected_columns():
    from src.db.models import Outlet

    cols = {c.name for c in Outlet.__table__.columns}
    required = {
        "id",
        "name",
        "normalized_name",
        "country",
        "language",
        "political_leaning",
        "rss_feeds",
        "website_url",
        "style_description",
        "editorial_focus",
        "sample_headlines",
    }
    assert required.issubset(cols)


# ── Relationships ───────────────────────────────────────────────────


def test_prediction_has_headlines_relationship():
    from src.db.models import Prediction

    assert "headlines" in Prediction.__mapper__.relationships


def test_prediction_has_pipeline_steps_relationship():
    from src.db.models import Prediction

    assert "pipeline_steps" in Prediction.__mapper__.relationships


def test_headline_has_prediction_relationship():
    from src.db.models import Headline

    assert "prediction" in Headline.__mapper__.relationships


# ── Constraints ─────────────────────────────────────────────────────


def test_outlet_normalized_name_is_unique():
    from src.db.models import Outlet

    col = Outlet.__table__.c.normalized_name
    assert col.unique is True
