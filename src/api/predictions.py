"""Predictions CRUD + SSE endpoints.

Спека: docs/08-api-backend.md (§§5.2, 6).

Контракт:
    POST /predictions — создать прогноз, поставить в очередь ARQ
    GET /predictions/{id} — полный прогноз с заголовками
    GET /predictions/{id}/stream — SSE-стрим прогресса
    GET /predictions — список с пагинацией
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from src.api.dependencies import get_current_user
from src.db.models import PredictionStatus, User

logger = logging.getLogger("api.predictions")

router = APIRouter(prefix="/predictions")


# === Pydantic Schemas ===


class CreatePredictionRequest(BaseModel):
    outlet: str = Field(..., min_length=1, max_length=200)
    target_date: date = Field(...)
    preset: str = Field(default="full")


class CreatePredictionResponse(BaseModel):
    id: str
    status: str
    outlet: str
    target_date: date
    created_at: datetime
    progress_url: str
    result_url: str


class HeadlineSchema(BaseModel):
    rank: int
    headline_text: str
    first_paragraph: str
    confidence: float
    confidence_label: str
    category: str
    reasoning: str
    evidence_chain: list[dict[str, str]] = Field(default_factory=list)
    agent_agreement: str
    dissenting_views: list[dict[str, str]] = Field(default_factory=list)


class PipelineStepSchema(BaseModel):
    agent_name: str
    step_order: int
    status: str
    duration_ms: int | None
    llm_model_used: str | None
    llm_tokens_in: int
    llm_tokens_out: int
    llm_cost_usd: float


class PredictionDetailResponse(BaseModel):
    id: str
    outlet_name: str
    target_date: date
    status: str
    created_at: datetime
    completed_at: datetime | None
    total_duration_ms: int | None
    total_llm_cost_usd: float | None
    headlines: list[HeadlineSchema]
    pipeline_steps: list[PipelineStepSchema]
    error_message: str | None


class PredictionListItem(BaseModel):
    id: str
    outlet_name: str
    target_date: date
    status: str
    created_at: datetime
    total_duration_ms: int | None
    headlines_count: int


class PredictionListResponse(BaseModel):
    items: list[PredictionListItem]
    total: int
    limit: int
    offset: int


# === Endpoints ===


@router.post(
    "",
    response_model=CreatePredictionResponse,
    status_code=201,
    summary="Создать прогноз",
)
async def create_prediction(
    body: CreatePredictionRequest,
    request: Request,
    user: User | None = Depends(get_current_user),
) -> CreatePredictionResponse:
    """Создать новый прогноз и поставить в очередь ARQ."""
    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository

    prediction_id = str(uuid.uuid4())
    normalized = body.outlet.strip().lower()
    now = datetime.now(UTC)

    session_factory = request.app.state.session_factory
    arq_pool = request.app.state.arq_pool

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)

        settings = request.app.state.settings
        pipeline_config = {
            "delphi_rounds": settings.delphi_rounds,
            "delphi_agents": settings.delphi_agents,
            "max_event_threads": settings.max_event_threads,
            "max_headlines": settings.max_headlines_per_prediction,
            "quality_gate_min_score": settings.quality_gate_min_score,
        }

        await repo.create(
            id=prediction_id,
            outlet_name=body.outlet.strip(),
            outlet_normalized=normalized,
            target_date=body.target_date,
            pipeline_config=pipeline_config,
            user_id=user.id if user else None,
            preset=body.preset,
        )
        await session.commit()

    try:
        await arq_pool.enqueue_job("run_prediction_task", prediction_id)
        logger.info("Enqueued prediction %s", prediction_id)
    except Exception as exc:
        logger.error("Failed to enqueue prediction %s: %s", prediction_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Очередь задач недоступна. Попробуйте позже.",
        ) from exc

    return CreatePredictionResponse(
        id=prediction_id,
        status="pending",
        outlet=body.outlet.strip(),
        target_date=body.target_date,
        created_at=now,
        progress_url=f"/api/v1/predictions/{prediction_id}/stream",
        result_url=f"/api/v1/predictions/{prediction_id}",
    )


@router.get(
    "/{prediction_id}",
    response_model=PredictionDetailResponse,
    summary="Получить прогноз",
)
async def get_prediction(
    prediction_id: str,
    request: Request,
) -> PredictionDetailResponse:
    """Полная информация о прогнозе."""
    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository

    session_factory = request.app.state.session_factory

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)
        prediction = await repo.get_by_id(prediction_id)

        if prediction is None:
            raise HTTPException(
                status_code=404,
                detail=f"Прогноз {prediction_id} не найден.",
            )

        return PredictionDetailResponse(
            id=prediction.id,
            outlet_name=prediction.outlet_name,
            target_date=prediction.target_date,
            status=prediction.status.value,
            created_at=prediction.created_at,
            completed_at=prediction.completed_at,
            total_duration_ms=prediction.total_duration_ms,
            total_llm_cost_usd=prediction.total_llm_cost_usd,
            headlines=[
                HeadlineSchema(
                    rank=h.rank,
                    headline_text=h.headline_text,
                    first_paragraph=h.first_paragraph,
                    confidence=h.confidence,
                    confidence_label=h.confidence_label,
                    category=h.category,
                    reasoning=h.reasoning,
                    evidence_chain=h.evidence_chain or [],
                    agent_agreement=h.agent_agreement,
                    dissenting_views=h.dissenting_views or [],
                )
                for h in prediction.headlines
            ],
            pipeline_steps=[
                PipelineStepSchema(
                    agent_name=s.agent_name,
                    step_order=s.step_order,
                    status=s.status.value,
                    duration_ms=s.duration_ms,
                    llm_model_used=s.llm_model_used,
                    llm_tokens_in=s.llm_tokens_in,
                    llm_tokens_out=s.llm_tokens_out,
                    llm_cost_usd=s.llm_cost_usd,
                )
                for s in prediction.pipeline_steps
            ],
            error_message=prediction.error_message,
        )


@router.get(
    "/{prediction_id}/stream",
    summary="SSE-стрим прогресса",
)
async def stream_prediction_progress(
    prediction_id: str,
    request: Request,
) -> EventSourceResponse:
    """SSE-стрим прогресса через Redis pub/sub."""
    redis = request.app.state.redis
    channel_name = f"prediction:{prediction_id}:progress"

    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel_name)
        try:
            yield {
                "event": "connected",
                "data": json.dumps({"prediction_id": prediction_id}),
            }

            while True:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0),
                    timeout=120.0,
                )

                if message is not None and message["type"] == "message":
                    data = json.loads(message["data"])
                    event_type = data.get("event", "progress")
                    yield {
                        "event": event_type,
                        "data": json.dumps(data),
                    }
                    if event_type in ("completed", "error"):
                        break
                else:
                    yield {"comment": "keepalive"}

        except asyncio.TimeoutError:
            yield {
                "event": "timeout",
                "data": json.dumps({"message": "Connection timed out"}),
            }
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()

    return EventSourceResponse(event_generator(), media_type="text/event-stream")


@router.get(
    "",
    response_model=PredictionListResponse,
    summary="Список прогнозов",
)
async def list_predictions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
) -> PredictionListResponse:
    """Список прогнозов с пагинацией."""
    from src.db.engine import get_session
    from src.db.repositories import PredictionRepository

    status_filter = None
    if status is not None:
        try:
            status_filter = PredictionStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Невалидный статус: {status}. "
                f"Допустимые: {[s.value for s in PredictionStatus]}",
            )

    session_factory = request.app.state.session_factory

    async with get_session(session_factory) as session:
        repo = PredictionRepository(session)
        predictions, total = await repo.get_recent(
            limit=limit, offset=offset, status=status_filter
        )

        return PredictionListResponse(
            items=[
                PredictionListItem(
                    id=p.id,
                    outlet_name=p.outlet_name,
                    target_date=p.target_date,
                    status=p.status.value,
                    created_at=p.created_at,
                    total_duration_ms=p.total_duration_ms,
                    headlines_count=len(p.headlines),
                )
                for p in predictions
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
