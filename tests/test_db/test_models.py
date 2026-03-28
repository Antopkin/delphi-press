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


# ── User / UserAPIKey models ──────────────────────────────────────


def test_user_has_expected_columns():
    from src.db.models import User

    cols = {c.name for c in User.__table__.columns}
    required = {"id", "email", "hashed_password", "is_active", "created_at"}
    assert required.issubset(cols)


def test_user_email_is_unique():
    from src.db.models import User

    col = User.__table__.c.email
    assert col.unique is True


def test_user_has_api_keys_relationship():
    from src.db.models import User

    assert "api_keys" in User.__mapper__.relationships


def test_user_has_predictions_relationship():
    from src.db.models import User

    assert "predictions" in User.__mapper__.relationships


def test_user_api_key_has_expected_columns():
    from src.db.models import UserAPIKey

    cols = {c.name for c in UserAPIKey.__table__.columns}
    required = {
        "id",
        "user_id",
        "provider",
        "encrypted_key",
        "label",
        "is_active",
        "created_at",
        "last_used_at",
    }
    assert required.issubset(cols)


def test_user_api_key_has_user_relationship():
    from src.db.models import UserAPIKey

    assert "user" in UserAPIKey.__mapper__.relationships


def test_user_api_key_has_unique_constraint_user_provider():
    from src.db.models import UserAPIKey

    constraints = [c for c in UserAPIKey.__table__.constraints if hasattr(c, "columns")]
    unique_cols = set()
    for c in constraints:
        col_names = {col.name for col in c.columns}
        if "user_id" in col_names and "provider" in col_names:
            unique_cols = col_names
    assert unique_cols == {"user_id", "provider"}


# ── Prediction user link ──────────────────────────────────────────


def test_prediction_has_user_id_column():
    from src.db.models import Prediction

    cols = {c.name for c in Prediction.__table__.columns}
    assert "user_id" in cols
    assert "preset" in cols


def test_prediction_user_id_is_nullable():
    from src.db.models import Prediction

    col = Prediction.__table__.c.user_id
    assert col.nullable is True


def test_prediction_has_user_relationship():
    from src.db.models import Prediction

    assert "user" in Prediction.__mapper__.relationships


# ── FetchMethod enum ─────────────────────────────────────────────


def test_fetch_method_enum_values():
    from src.db.models import FetchMethod

    values = {m.value for m in FetchMethod}
    expected = {"rss", "search", "scrape"}
    assert values == expected


# ── FeedSource model ─────────────────────────────────────────────


def test_feed_source_has_expected_columns():
    from src.db.models import FeedSource

    cols = {c.name for c in FeedSource.__table__.columns}
    required = {
        "id",
        "outlet_id",
        "rss_url",
        "etag",
        "last_modified",
        "last_fetched",
        "error_count",
        "is_active",
        "created_at",
    }
    assert required.issubset(cols)


def test_feed_source_rss_url_is_unique():
    from src.db.models import FeedSource

    col = FeedSource.__table__.c.rss_url
    assert col.unique is True


def test_feed_source_has_outlet_relationship():
    from src.db.models import FeedSource

    assert "outlet" in FeedSource.__mapper__.relationships


def test_outlet_has_feed_sources_relationship():
    from src.db.models import Outlet

    assert "feed_sources" in Outlet.__mapper__.relationships


def test_feed_source_outlet_id_has_fk():
    from src.db.models import FeedSource

    col = FeedSource.__table__.c.outlet_id
    fks = {fk.target_fullname for fk in col.foreign_keys}
    assert "outlets.id" in fks


# ── RawArticle model ────────────────────────────────────────────


def test_raw_article_has_expected_columns():
    from src.db.models import RawArticle

    cols = {c.name for c in RawArticle.__table__.columns}
    required = {
        "id",
        "url",
        "title",
        "summary",
        "cleaned_text",
        "published_at",
        "source_outlet",
        "language",
        "categories",
        "fetch_method",
        "created_at",
    }
    assert required.issubset(cols)


def test_raw_article_url_is_unique():
    from src.db.models import RawArticle

    col = RawArticle.__table__.c.url
    assert col.unique is True


def test_raw_article_has_composite_index():
    from src.db.models import RawArticle

    index_names = {idx.name for idx in RawArticle.__table__.indexes}
    assert "ix_raw_articles_outlet_published" in index_names


def test_raw_article_created_at_has_index():
    from src.db.models import RawArticle

    col = RawArticle.__table__.c.created_at
    assert col.index is True
