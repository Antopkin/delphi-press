"""Репозитории — инкапсуляция всей логики работы с БД.

Спека: docs/08-api-backend.md (§4).

Контракт:
    PredictionRepository: CRUD для прогнозов, headlines, pipeline steps.
    OutletRepository: поиск и upsert для каталога СМИ.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Headline,
    Outlet,
    PipelineStep,
    PipelineStepStatus,
    Prediction,
    PredictionStatus,
    User,
    UserAPIKey,
)

logger = logging.getLogger("db.repositories")


class PredictionRepository:
    """CRUD-операции для прогнозов."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        id: str,
        outlet_name: str,
        outlet_normalized: str,
        target_date: Any,
        pipeline_config: dict[str, Any] | None = None,
        user_id: str | None = None,
        preset: str = "full",
    ) -> Prediction:
        """Создание нового прогноза."""
        prediction = Prediction(
            id=id,
            outlet_name=outlet_name,
            outlet_normalized=outlet_normalized,
            target_date=target_date,
            status=PredictionStatus.PENDING,
            pipeline_config=pipeline_config,
            user_id=user_id,
            preset=preset,
        )
        self.session.add(prediction)
        await self.session.flush()
        logger.info("Created prediction %s for outlet '%s'", id, outlet_name)
        return prediction

    async def get_by_id(self, prediction_id: str) -> Prediction | None:
        """Получение прогноза по ID."""
        result = await self.session.execute(
            select(Prediction).where(Prediction.id == prediction_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        prediction_id: str,
        status: PredictionStatus,
        *,
        error_message: str | None = None,
        total_duration_ms: int | None = None,
        total_llm_cost_usd: float | None = None,
    ) -> None:
        """Обновление статуса прогноза."""
        values: dict[str, Any] = {"status": status}

        if status in (PredictionStatus.COMPLETED, PredictionStatus.FAILED):
            values["completed_at"] = datetime.now(UTC)

        if error_message is not None:
            values["error_message"] = error_message
        if total_duration_ms is not None:
            values["total_duration_ms"] = total_duration_ms
        if total_llm_cost_usd is not None:
            values["total_llm_cost_usd"] = total_llm_cost_usd

        await self.session.execute(
            update(Prediction).where(Prediction.id == prediction_id).values(**values)
        )
        logger.info("Updated prediction %s status to %s", prediction_id, status.value)

    async def get_recent(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: PredictionStatus | None = None,
    ) -> tuple[Sequence[Prediction], int]:
        """Список последних прогнозов с пагинацией."""
        limit = min(limit, 100)

        query = select(Prediction).order_by(Prediction.created_at.desc())
        count_query = select(func.count(Prediction.id))

        if status is not None:
            query = query.where(Prediction.status == status)
            count_query = count_query.where(Prediction.status == status)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        predictions = result.scalars().all()

        return predictions, total

    async def save_headlines(
        self,
        prediction_id: str,
        headlines_data: list[dict[str, Any]],
    ) -> list[Headline]:
        """Массовое сохранение заголовков прогноза."""
        headlines = []
        for data in headlines_data:
            headline = Headline(
                prediction_id=prediction_id,
                rank=data["rank"],
                headline_text=data["headline_text"],
                first_paragraph=data.get("first_paragraph", ""),
                confidence=data["confidence"],
                confidence_label=data.get("confidence_label", ""),
                category=data.get("category", ""),
                reasoning=data.get("reasoning", ""),
                evidence_chain=data.get("evidence_chain"),
                dissenting_views=data.get("dissenting_views"),
                agent_agreement=data.get("agent_agreement", ""),
            )
            self.session.add(headline)
            headlines.append(headline)

        await self.session.flush()
        logger.info("Saved %d headlines for prediction %s", len(headlines), prediction_id)
        return headlines

    async def save_pipeline_step(
        self,
        prediction_id: str,
        step_data: dict[str, Any],
    ) -> PipelineStep:
        """Сохранение метрик одного шага пайплайна."""
        step = PipelineStep(
            prediction_id=prediction_id,
            agent_name=step_data["agent_name"],
            step_order=step_data["step_order"],
            status=PipelineStepStatus(step_data["status"]),
            started_at=step_data.get("started_at"),
            completed_at=step_data.get("completed_at"),
            duration_ms=step_data.get("duration_ms"),
            llm_model_used=step_data.get("llm_model_used"),
            llm_tokens_in=step_data.get("llm_tokens_in", 0),
            llm_tokens_out=step_data.get("llm_tokens_out", 0),
            llm_cost_usd=step_data.get("llm_cost_usd", 0.0),
            input_summary=step_data.get("input_summary"),
            output_summary=step_data.get("output_summary"),
            output_data=step_data.get("output_data"),
            error_message=step_data.get("error_message"),
        )
        self.session.add(step)
        await self.session.flush()
        return step


class OutletRepository:
    """CRUD-операции для каталога СМИ."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_name(self, normalized_name: str) -> Outlet | None:
        """Получение СМИ по нормализованному имени."""
        result = await self.session.execute(
            select(Outlet).where(Outlet.normalized_name == normalized_name)
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> Sequence[Outlet]:
        """Поиск СМИ для автокомплита (LIKE)."""
        limit = min(limit, 50)
        pattern = f"%{query.lower()}%"

        result = await self.session.execute(
            select(Outlet)
            .where(Outlet.normalized_name.like(pattern))
            .order_by(Outlet.name)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def upsert(self, data: dict[str, Any]) -> Outlet:
        """Создание или обновление записи СМИ."""
        normalized = data["normalized_name"]
        existing = await self.get_by_name(normalized)

        if existing is not None:
            for key, value in data.items():
                if key not in ("id", "created_at") and hasattr(existing, key):
                    setattr(existing, key, value)
            await self.session.flush()
            logger.info("Updated outlet '%s'", normalized)
            return existing

        outlet = Outlet(**{k: v for k, v in data.items() if k != "id" and hasattr(Outlet, k)})
        self.session.add(outlet)
        await self.session.flush()
        logger.info("Created outlet '%s'", normalized)
        return outlet


class UserRepository:
    """CRUD-операции для пользователей и их API-ключей."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        id: str,
        email: str,
        hashed_password: str,
    ) -> User:
        """Создание нового пользователя."""
        user = User(id=id, email=email, hashed_password=hashed_password)
        self.session.add(user)
        await self.session.flush()
        logger.info("Created user %s (%s)", id, email)
        return user

    async def get_by_email(self, email: str) -> User | None:
        """Поиск пользователя по email."""
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> User | None:
        """Поиск пользователя по ID."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_api_key(
        self,
        *,
        user_id: str,
        provider: str,
        encrypted_key: str,
        label: str = "",
    ) -> UserAPIKey:
        """Добавление зашифрованного API-ключа."""
        key = UserAPIKey(
            user_id=user_id,
            provider=provider,
            encrypted_key=encrypted_key,
            label=label,
        )
        self.session.add(key)
        await self.session.flush()
        logger.info("Created API key for user %s, provider %s", user_id, provider)
        return key

    async def get_api_keys(self, user_id: str) -> Sequence[UserAPIKey]:
        """Список API-ключей пользователя."""
        result = await self.session.execute(
            select(UserAPIKey).where(UserAPIKey.user_id == user_id).order_by(UserAPIKey.created_at)
        )
        return list(result.scalars().all())

    async def get_api_key_by_id(self, key_id: int, user_id: str) -> UserAPIKey | None:
        """Получение ключа по ID (с проверкой владельца)."""
        result = await self.session.execute(
            select(UserAPIKey).where(
                UserAPIKey.id == key_id,
                UserAPIKey.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_api_key(self, key_id: int, user_id: str) -> bool:
        """Удаление ключа. Возвращает True если ключ найден и удалён."""
        key = await self.get_api_key_by_id(key_id, user_id)
        if key is None:
            return False
        await self.session.delete(key)
        await self.session.flush()
        logger.info("Deleted API key %d for user %s", key_id, user_id)
        return True
