"""Tests for src.db.repositories — all repository classes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from src.db.models import PredictionStatus

# ── PredictionRepository ────────────────────────────────────────────


class TestPredictionCreate:
    async def test_create_prediction(self, test_session, make_prediction_data):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        data = make_prediction_data()
        pred = await repo.create(**data)
        await test_session.commit()

        assert pred.id == data["id"]
        assert pred.outlet_name == "TASS"
        assert pred.outlet_normalized == "tass"

    async def test_create_prediction_status_is_pending(self, test_session, make_prediction_data):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        pred = await repo.create(**make_prediction_data())
        await test_session.commit()

        assert pred.status == PredictionStatus.PENDING


class TestPredictionGetById:
    async def test_get_by_id_returns_prediction(self, test_session, make_prediction_data):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        data = make_prediction_data()
        await repo.create(**data)
        await test_session.commit()

        found = await repo.get_by_id(data["id"])
        assert found is not None
        assert found.id == data["id"]

    async def test_get_by_id_not_found_returns_none(self, test_session):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        assert await repo.get_by_id("nonexistent") is None


class TestPredictionUpdateStatus:
    async def test_update_status_changes_status(self, test_session, make_prediction_data):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        data = make_prediction_data()
        await repo.create(**data)
        await test_session.commit()

        await repo.update_status(data["id"], PredictionStatus.COLLECTING)
        await test_session.commit()

        pred = await repo.get_by_id(data["id"])
        assert pred.status == PredictionStatus.COLLECTING

    async def test_update_status_completed_sets_completed_at(
        self, test_session, make_prediction_data
    ):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        data = make_prediction_data()
        await repo.create(**data)
        await test_session.commit()

        await repo.update_status(data["id"], PredictionStatus.COMPLETED, total_duration_ms=60000)
        await test_session.commit()

        pred = await repo.get_by_id(data["id"])
        assert pred.completed_at is not None
        assert pred.total_duration_ms == 60000

    async def test_update_status_failed_with_error(self, test_session, make_prediction_data):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        data = make_prediction_data()
        await repo.create(**data)
        await test_session.commit()

        await repo.update_status(data["id"], PredictionStatus.FAILED, error_message="boom")
        await test_session.commit()

        pred = await repo.get_by_id(data["id"])
        assert pred.error_message == "boom"
        assert pred.completed_at is not None


class TestPredictionGetRecent:
    async def test_get_recent_returns_items_and_total(self, test_session, make_prediction_data):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        for _ in range(3):
            await repo.create(**make_prediction_data(id=str(uuid.uuid4())))
        await test_session.commit()

        items, total = await repo.get_recent()
        assert total == 3
        assert len(items) == 3

    async def test_get_recent_with_limit_and_offset(self, test_session, make_prediction_data):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        for _ in range(5):
            await repo.create(**make_prediction_data(id=str(uuid.uuid4())))
        await test_session.commit()

        items, total = await repo.get_recent(limit=2, offset=1)
        assert total == 5
        assert len(items) == 2

    async def test_get_recent_with_status_filter(self, test_session, make_prediction_data):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        pid1 = str(uuid.uuid4())
        pid2 = str(uuid.uuid4())
        await repo.create(**make_prediction_data(id=pid1))
        await repo.create(**make_prediction_data(id=pid2))
        await test_session.commit()

        await repo.update_status(pid1, PredictionStatus.COMPLETED)
        await test_session.commit()

        items, total = await repo.get_recent(status=PredictionStatus.COMPLETED)
        assert total == 1
        assert items[0].id == pid1

    async def test_get_recent_limit_capped_at_100(self, test_session, make_prediction_data):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        await repo.create(**make_prediction_data())
        await test_session.commit()

        items, total = await repo.get_recent(limit=999)
        assert len(items) <= 100


class TestPredictionSaveHeadlines:
    async def test_save_headlines(self, test_session, make_prediction_data, make_headline_data):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        data = make_prediction_data()
        await repo.create(**data)
        await test_session.commit()

        headlines = await repo.save_headlines(
            data["id"],
            [make_headline_data(rank=1), make_headline_data(rank=2)],
        )
        await test_session.commit()

        assert len(headlines) == 2
        assert headlines[0].prediction_id == data["id"]


class TestPredictionReplaceHeadlines:
    async def test_replace_headlines_deletes_old_and_inserts_new(
        self, test_session, make_prediction_data, make_headline_data
    ):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        data = make_prediction_data()
        await repo.create(**data)
        await test_session.commit()

        # Save initial headlines
        await repo.save_headlines(
            data["id"],
            [make_headline_data(rank=1, headline_text="Draft 1")],
        )
        await test_session.commit()

        # Replace with new headlines
        new_headlines = await repo.replace_headlines(
            data["id"],
            [
                make_headline_data(rank=1, headline_text="Final 1"),
                make_headline_data(rank=2, headline_text="Final 2"),
            ],
        )
        await test_session.commit()

        assert len(new_headlines) == 2
        # Verify old headline is gone
        pred = await repo.get_by_id(data["id"])
        assert len(pred.headlines) == 2
        texts = {h.headline_text for h in pred.headlines}
        assert "Draft 1" not in texts
        assert "Final 1" in texts
        assert "Final 2" in texts

    async def test_replace_headlines_empty_list_deletes_all(
        self, test_session, make_prediction_data, make_headline_data
    ):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        data = make_prediction_data()
        await repo.create(**data)
        await test_session.commit()

        await repo.save_headlines(data["id"], [make_headline_data(rank=1)])
        await test_session.commit()

        result = await repo.replace_headlines(data["id"], [])
        await test_session.commit()

        assert result == []
        pred = await repo.get_by_id(data["id"])
        assert len(pred.headlines) == 0


class TestPredictionSavePipelineStep:
    async def test_save_pipeline_step(self, test_session, make_prediction_data, make_step_data):
        from src.db.repositories import PredictionRepository

        repo = PredictionRepository(test_session)
        data = make_prediction_data()
        await repo.create(**data)
        await test_session.commit()

        step = await repo.save_pipeline_step(data["id"], make_step_data())
        await test_session.commit()

        assert step.prediction_id == data["id"]
        assert step.agent_name == "news_scout"


# ── OutletRepository ────────────────────────────────────────────────


class TestOutletGetByName:
    async def test_get_by_name_found(self, test_session, make_outlet_data):
        from src.db.models import Outlet
        from src.db.repositories import OutletRepository

        repo = OutletRepository(test_session)
        test_session.add(Outlet(**make_outlet_data()))
        await test_session.commit()

        result = await repo.get_by_name("bbc russian")
        assert result is not None
        assert result.name == "BBC Russian"

    async def test_get_by_name_not_found(self, test_session):
        from src.db.repositories import OutletRepository

        repo = OutletRepository(test_session)
        assert await repo.get_by_name("nonexistent") is None


class TestOutletSearch:
    async def test_search_returns_matching(self, test_session, make_outlet_data):
        from src.db.models import Outlet
        from src.db.repositories import OutletRepository

        repo = OutletRepository(test_session)
        test_session.add(Outlet(**make_outlet_data()))
        test_session.add(Outlet(**make_outlet_data(name="TASS", normalized_name="tass")))
        await test_session.commit()

        results = await repo.search("bbc")
        assert len(results) == 1
        assert results[0].name == "BBC Russian"

    async def test_search_empty_results(self, test_session):
        from src.db.repositories import OutletRepository

        repo = OutletRepository(test_session)
        results = await repo.search("nonexistent")
        assert results == []

    async def test_search_limit_capped_at_50(self, test_session):
        from src.db.repositories import OutletRepository

        repo = OutletRepository(test_session)
        results = await repo.search("test", limit=999)
        assert len(results) <= 50


class TestOutletUpsert:
    async def test_upsert_creates_new(self, test_session, make_outlet_data):
        from src.db.repositories import OutletRepository

        repo = OutletRepository(test_session)
        outlet = await repo.upsert(make_outlet_data())
        await test_session.commit()

        assert outlet.name == "BBC Russian"
        assert outlet.id is not None

    async def test_upsert_updates_existing(self, test_session, make_outlet_data):
        from src.db.repositories import OutletRepository

        repo = OutletRepository(test_session)
        await repo.upsert(make_outlet_data())
        await test_session.commit()

        updated = await repo.upsert(make_outlet_data(website_url="https://bbc.com/russian"))
        await test_session.commit()

        assert updated.website_url == "https://bbc.com/russian"


# ── UserRepository ─────────────────────────────────────────────────


class TestUserCreate:
    async def test_create_user_returns_user(self, test_session, make_user_data):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        data = make_user_data()
        user = await repo.create(
            id=data["id"], email=data["email"], hashed_password=data["hashed_password"]
        )
        await test_session.commit()

        assert user.id == data["id"]
        assert user.email == data["email"]
        assert user.is_active is True

    async def test_create_user_duplicate_email_raises(self, test_session, make_user_data):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        data = make_user_data()
        await repo.create(
            id=data["id"], email=data["email"], hashed_password=data["hashed_password"]
        )
        await test_session.commit()

        with pytest.raises(IntegrityError):
            await repo.create(
                id=str(uuid.uuid4()),
                email=data["email"],
                hashed_password="other-hash",
            )
            await test_session.flush()


class TestUserGetByEmail:
    async def test_get_by_email_found(self, test_session, make_user_data):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        data = make_user_data()
        await repo.create(
            id=data["id"], email=data["email"], hashed_password=data["hashed_password"]
        )
        await test_session.commit()

        user = await repo.get_by_email(data["email"])
        assert user is not None
        assert user.id == data["id"]

    async def test_get_by_email_not_found(self, test_session):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        assert await repo.get_by_email("nobody@example.com") is None


class TestUserGetById:
    async def test_get_by_id_found(self, test_session, make_user_data):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        data = make_user_data()
        await repo.create(
            id=data["id"], email=data["email"], hashed_password=data["hashed_password"]
        )
        await test_session.commit()

        user = await repo.get_by_id(data["id"])
        assert user is not None
        assert user.email == data["email"]

    async def test_get_by_id_not_found(self, test_session):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        assert await repo.get_by_id("nonexistent") is None


class TestUserAPIKeyCreate:
    async def test_create_api_key(self, test_session, make_user_data):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        data = make_user_data()
        await repo.create(
            id=data["id"], email=data["email"], hashed_password=data["hashed_password"]
        )
        await test_session.commit()

        key = await repo.create_api_key(
            user_id=data["id"],
            provider="openrouter",
            encrypted_key="encrypted-value",
            label="My Key",
        )
        await test_session.commit()

        assert key.provider == "openrouter"
        assert key.user_id == data["id"]
        assert key.label == "My Key"

    async def test_create_duplicate_provider_raises(self, test_session, make_user_data):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        data = make_user_data()
        await repo.create(
            id=data["id"], email=data["email"], hashed_password=data["hashed_password"]
        )
        await test_session.commit()

        await repo.create_api_key(user_id=data["id"], provider="openrouter", encrypted_key="enc1")
        await test_session.commit()

        with pytest.raises(IntegrityError):
            await repo.create_api_key(
                user_id=data["id"], provider="openrouter", encrypted_key="enc2"
            )
            await test_session.flush()


class TestUserAPIKeyList:
    async def test_list_keys_returns_user_keys(self, test_session, make_user_data):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        data = make_user_data()
        await repo.create(
            id=data["id"], email=data["email"], hashed_password=data["hashed_password"]
        )
        await repo.create_api_key(user_id=data["id"], provider="openrouter", encrypted_key="enc")
        await test_session.commit()

        keys = await repo.get_api_keys(data["id"])
        assert len(keys) == 1
        assert keys[0].provider == "openrouter"

    async def test_list_keys_empty(self, test_session, make_user_data):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        data = make_user_data()
        await repo.create(
            id=data["id"], email=data["email"], hashed_password=data["hashed_password"]
        )
        await test_session.commit()

        keys = await repo.get_api_keys(data["id"])
        assert keys == []


class TestUserAPIKeyDelete:
    async def test_delete_key_removes_it(self, test_session, make_user_data):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        data = make_user_data()
        await repo.create(
            id=data["id"], email=data["email"], hashed_password=data["hashed_password"]
        )
        key = await repo.create_api_key(
            user_id=data["id"], provider="openrouter", encrypted_key="enc"
        )
        await test_session.commit()

        deleted = await repo.delete_api_key(key.id, data["id"])
        await test_session.commit()

        assert deleted is True
        keys = await repo.get_api_keys(data["id"])
        assert keys == []

    async def test_delete_nonexistent_returns_false(self, test_session, make_user_data):
        from src.db.repositories import UserRepository

        repo = UserRepository(test_session)
        deleted = await repo.delete_api_key(9999, "no-user")
        assert deleted is False


# ── FeedSourceRepository ──────────────────────────────────────────


class TestFeedSourceCreate:
    async def test_create_feed_source(self, test_session, make_outlet_data, make_feed_source_data):
        from src.db.models import Outlet
        from src.db.repositories import FeedSourceRepository

        outlet = Outlet(**make_outlet_data())
        test_session.add(outlet)
        await test_session.commit()

        repo = FeedSourceRepository(test_session)
        feed_data = make_feed_source_data()
        feed = await repo.create(outlet_id=outlet.id, rss_url=feed_data["rss_url"])
        await test_session.commit()

        assert feed.id is not None
        assert feed.outlet_id == outlet.id
        assert feed.rss_url == feed_data["rss_url"]
        assert feed.is_active is True
        assert feed.error_count == 0

    async def test_create_duplicate_url_raises(
        self, test_session, make_outlet_data, make_feed_source_data
    ):
        from src.db.models import Outlet
        from src.db.repositories import FeedSourceRepository

        outlet = Outlet(**make_outlet_data())
        test_session.add(outlet)
        await test_session.commit()

        repo = FeedSourceRepository(test_session)
        feed_data = make_feed_source_data()
        await repo.create(outlet_id=outlet.id, rss_url=feed_data["rss_url"])
        await test_session.commit()

        with pytest.raises(IntegrityError):
            await repo.create(outlet_id=outlet.id, rss_url=feed_data["rss_url"])
            await test_session.flush()


class TestFeedSourceActiveFeeds:
    async def test_get_active_feeds(self, test_session, make_outlet_data):
        from src.db.models import FeedSource, Outlet
        from src.db.repositories import FeedSourceRepository

        outlet = Outlet(**make_outlet_data())
        test_session.add(outlet)
        await test_session.flush()

        test_session.add(FeedSource(outlet_id=outlet.id, rss_url="https://a.com/rss"))
        test_session.add(
            FeedSource(outlet_id=outlet.id, rss_url="https://b.com/rss", is_active=False)
        )
        await test_session.commit()

        repo = FeedSourceRepository(test_session)
        active = await repo.get_active_feeds()
        assert len(active) == 1
        assert active[0].rss_url == "https://a.com/rss"

    async def test_get_active_by_outlet(self, test_session, make_outlet_data):
        from src.db.models import FeedSource, Outlet
        from src.db.repositories import FeedSourceRepository

        o1 = Outlet(**make_outlet_data(name="A", normalized_name="a"))
        o2 = Outlet(**make_outlet_data(name="B", normalized_name="b"))
        test_session.add_all([o1, o2])
        await test_session.flush()

        test_session.add(FeedSource(outlet_id=o1.id, rss_url="https://a.com/rss"))
        test_session.add(FeedSource(outlet_id=o2.id, rss_url="https://b.com/rss"))
        await test_session.commit()

        repo = FeedSourceRepository(test_session)
        feeds = await repo.get_active_by_outlet(o1.id)
        assert len(feeds) == 1
        assert feeds[0].outlet_id == o1.id


class TestFeedSourceCircuitBreaker:
    async def test_increment_error_increments_count(self, test_session, make_outlet_data):
        from src.db.models import FeedSource, Outlet
        from src.db.repositories import FeedSourceRepository

        outlet = Outlet(**make_outlet_data())
        test_session.add(outlet)
        await test_session.flush()

        feed = FeedSource(outlet_id=outlet.id, rss_url="https://err.com/rss")
        test_session.add(feed)
        await test_session.commit()

        repo = FeedSourceRepository(test_session)
        await repo.increment_error(feed.id)
        await test_session.commit()

        await test_session.refresh(feed)
        assert feed.error_count == 1
        assert feed.is_active is True

    async def test_increment_error_deactivates_at_threshold(self, test_session, make_outlet_data):
        from src.db.models import FeedSource, Outlet
        from src.db.repositories import FeedSourceRepository

        outlet = Outlet(**make_outlet_data())
        test_session.add(outlet)
        await test_session.flush()

        feed = FeedSource(outlet_id=outlet.id, rss_url="https://err5.com/rss", error_count=4)
        test_session.add(feed)
        await test_session.commit()

        repo = FeedSourceRepository(test_session)
        await repo.increment_error(feed.id)
        await test_session.commit()

        await test_session.refresh(feed)
        assert feed.error_count == 5
        assert feed.is_active is False

    async def test_reset_errors_reactivates(self, test_session, make_outlet_data):
        from src.db.models import FeedSource, Outlet
        from src.db.repositories import FeedSourceRepository

        outlet = Outlet(**make_outlet_data())
        test_session.add(outlet)
        await test_session.flush()

        feed = FeedSource(
            outlet_id=outlet.id, rss_url="https://reset.com/rss", error_count=5, is_active=False
        )
        test_session.add(feed)
        await test_session.commit()

        repo = FeedSourceRepository(test_session)
        await repo.reset_errors(feed.id)
        await test_session.commit()

        await test_session.refresh(feed)
        assert feed.error_count == 0
        assert feed.is_active is True


class TestFeedSourceUpdateFetchState:
    async def test_update_fetch_state(self, test_session, make_outlet_data):
        from src.db.models import FeedSource, Outlet
        from src.db.repositories import FeedSourceRepository

        outlet = Outlet(**make_outlet_data())
        test_session.add(outlet)
        await test_session.flush()

        feed = FeedSource(outlet_id=outlet.id, rss_url="https://state.com/rss")
        test_session.add(feed)
        await test_session.commit()

        now = datetime.now(UTC)
        repo = FeedSourceRepository(test_session)
        await repo.update_fetch_state(
            feed.id, etag='"abc"', last_modified="Sat, 01 Jan 2026", last_fetched=now
        )
        await test_session.commit()

        await test_session.refresh(feed)
        assert feed.etag == '"abc"'
        assert feed.last_modified == "Sat, 01 Jan 2026"
        assert feed.last_fetched is not None


# ── RawArticleRepository ─────────────────────────────────────────


class TestRawArticleUpsertBatch:
    async def test_upsert_batch_inserts_new(self, test_session, make_raw_article_data):
        from src.db.repositories import RawArticleRepository

        repo = RawArticleRepository(test_session)
        articles = [make_raw_article_data(), make_raw_article_data()]
        inserted = await repo.upsert_batch(articles)
        await test_session.commit()

        assert inserted == 2

    async def test_upsert_batch_skips_duplicates(self, test_session, make_raw_article_data):
        from src.db.repositories import RawArticleRepository

        repo = RawArticleRepository(test_session)
        article = make_raw_article_data()
        await repo.upsert_batch([article])
        await test_session.commit()

        # Insert same article again
        inserted = await repo.upsert_batch([article])
        await test_session.commit()

        assert inserted == 0

    async def test_upsert_batch_empty_list_returns_zero(self, test_session):
        from src.db.repositories import RawArticleRepository

        repo = RawArticleRepository(test_session)
        inserted = await repo.upsert_batch([])
        assert inserted == 0


class TestRawArticleGetRecent:
    async def test_get_recent_by_outlet(self, test_session, make_raw_article_data):
        from src.db.repositories import RawArticleRepository

        repo = RawArticleRepository(test_session)
        await repo.upsert_batch(
            [
                make_raw_article_data(source_outlet="tass"),
                make_raw_article_data(source_outlet="tass"),
                make_raw_article_data(source_outlet="bbc"),
            ]
        )
        await test_session.commit()

        results = await repo.get_recent_by_outlet("tass")
        assert len(results) == 2
        assert all(r.source_outlet == "tass" for r in results)

    async def test_get_recent_by_outlet_respects_limit(self, test_session, make_raw_article_data):
        from src.db.repositories import RawArticleRepository

        repo = RawArticleRepository(test_session)
        await repo.upsert_batch([make_raw_article_data(source_outlet="tass") for _ in range(5)])
        await test_session.commit()

        results = await repo.get_recent_by_outlet("tass", limit=2)
        assert len(results) == 2


class TestRawArticleDeleteOlderThan:
    async def test_delete_older_than_removes_old(self, test_session):
        from src.db.models import FetchMethod, RawArticle
        from src.db.repositories import RawArticleRepository

        # Insert an old article directly (bypassing upsert to set created_at)
        old_article = RawArticle(
            url="https://old.com/1",
            title="Old article",
            source_outlet="tass",
            fetch_method=FetchMethod.RSS,
            created_at=datetime.now(UTC) - timedelta(days=60),
        )
        test_session.add(old_article)
        new_article = RawArticle(
            url="https://new.com/1",
            title="New article",
            source_outlet="tass",
            fetch_method=FetchMethod.RSS,
            created_at=datetime.now(UTC),
        )
        test_session.add(new_article)
        await test_session.commit()

        repo = RawArticleRepository(test_session)
        deleted = await repo.delete_older_than(30)
        await test_session.commit()

        assert deleted == 1

        # Verify the new article still exists
        remaining = await repo.get_recent_by_outlet("tass")
        assert len(remaining) == 1
        assert remaining[0].title == "New article"


class TestRawArticlePendingTextExtraction:
    async def test_get_pending_text_extraction(self, test_session):
        from src.db.models import FetchMethod, RawArticle
        from src.db.repositories import RawArticleRepository

        # One with cleaned_text, one without
        test_session.add(
            RawArticle(
                url="https://a.com/1",
                title="Has text",
                source_outlet="tass",
                fetch_method=FetchMethod.RSS,
                cleaned_text="Extracted text here",
            )
        )
        test_session.add(
            RawArticle(
                url="https://b.com/1",
                title="No text",
                source_outlet="tass",
                fetch_method=FetchMethod.RSS,
                cleaned_text=None,
            )
        )
        await test_session.commit()

        repo = RawArticleRepository(test_session)
        pending = await repo.get_pending_text_extraction()
        assert len(pending) == 1
        assert pending[0].title == "No text"


class TestRawArticleUpdateCleanedText:
    async def test_update_cleaned_text(self, test_session):
        from src.db.models import FetchMethod, RawArticle
        from src.db.repositories import RawArticleRepository

        article = RawArticle(
            url="https://upd.com/1",
            title="To update",
            source_outlet="tass",
            fetch_method=FetchMethod.RSS,
        )
        test_session.add(article)
        await test_session.commit()

        repo = RawArticleRepository(test_session)
        await repo.update_cleaned_text(article.id, "Extracted content")
        await test_session.commit()

        await test_session.refresh(article)
        assert article.cleaned_text == "Extracted content"
