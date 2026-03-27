"""Централизованные Pydantic-схемы для пайплайна Delphi Press.

Все публичные модели, dataclasses и enums реэкспортируются из этого модуля.
Исключение: agent.ScenarioType (Delphi-контекст) не реэкспортируется — используйте
``from src.schemas.agent import ScenarioType`` при необходимости. Из __init__
экспортируется events.ScenarioType (контекст траекторий).
"""

from src.schemas.agent import (
    AgentResult,
    AnonymizedPosition,
    ConsensusArea,
    CrossImpactFlag,
    DisputeArea,
    GapArea,
    MediatorSynthesis,
    PersonaAssessment,
    PredictionItem,
    StageResult,
)
from src.schemas.events import (
    CrossImpactEntry,
    CrossImpactMatrix,
    EconomicAssessment,
    EconomicIndicator,
    EditorialPosition,
    EventCertainty,
    EventThread,
    EventTrajectory,
    EventType,
    GeopoliticalAssessment,
    HeadlineStyle,
    MediaAssessment,
    NewsworthinessScore,
    OutletProfile,
    Scenario,
    ScenarioType,
    ScheduledEvent,
    SignalRecord,
    SignalSource,
    StrategicActor,
    ToneProfile,
    WritingStyle,
)
from src.schemas.headline import (
    AgreementLevel,
    CheckResult,
    ConfidenceLabel,
    DissentingView,
    FinalPrediction,
    FramingBrief,
    FramingStrategy,
    GateDecision,
    GeneratedHeadline,
    QualityScore,
    RankedPrediction,
)
from src.schemas.llm import (
    CostRecord,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ModelAssignment,
)
from src.schemas.pipeline import PipelineContext
from src.schemas.prediction import (
    HeadlineOutput,
    PredictionRequest,
    PredictionResponse,
)
from src.schemas.progress import (
    STAGE_LABELS,
    STAGE_PROGRESS_MAP,
    ProgressStage,
    SSEProgressEvent,
)

__all__ = [
    # agent.py
    "AgentResult",
    "StageResult",
    "PredictionItem",
    "PersonaAssessment",
    "AnonymizedPosition",
    "ConsensusArea",
    "DisputeArea",
    "GapArea",
    "CrossImpactFlag",
    "MediatorSynthesis",
    # events.py
    "SignalSource",
    "SignalRecord",
    "EventType",
    "EventCertainty",
    "ScheduledEvent",
    "ToneProfile",
    "HeadlineStyle",
    "WritingStyle",
    "EditorialPosition",
    "OutletProfile",
    "EventThread",
    "ScenarioType",
    "Scenario",
    "EventTrajectory",
    "CrossImpactEntry",
    "CrossImpactMatrix",
    "StrategicActor",
    "GeopoliticalAssessment",
    "EconomicIndicator",
    "EconomicAssessment",
    "NewsworthinessScore",
    "MediaAssessment",
    # headline.py
    "ConfidenceLabel",
    "AgreementLevel",
    "FramingStrategy",
    "GateDecision",
    "DissentingView",
    "RankedPrediction",
    "FramingBrief",
    "GeneratedHeadline",
    "CheckResult",
    "QualityScore",
    "FinalPrediction",
    # prediction.py
    "PredictionRequest",
    "HeadlineOutput",
    "PredictionResponse",
    # pipeline.py
    "PipelineContext",
    # progress.py
    "ProgressStage",
    "SSEProgressEvent",
    "STAGE_PROGRESS_MAP",
    "STAGE_LABELS",
    # llm.py
    "MessageRole",
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "CostRecord",
    "ModelAssignment",
]
