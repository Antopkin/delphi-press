"""Tests for src.db.repositories — PredictionRepository, OutletRepository."""

from __future__ import annotations

import uuid

import pytest

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
