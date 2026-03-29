# 05 -- Delphi Pipeline: мультиагентное прогнозирование

> Реализует: `src/agents/forecasters/personas.py`, `delphi.py`, `mediator.py`, `judge.py`
> Стадии пайплайна: 4 (Delphi R1), 5 (Delphi R2 + Mediator), 6 (Judge)
> Зависимости: `src/schemas/agent.py`, `src/llm/providers.py`, `src/llm/router.py`

---

## 1. Обзор метода Дельфи

### 1.1 Классический метод

Метод Дельфи (Dalkey & Helmer, RAND Corporation, 1963) -- структурированная техника группового прогнозирования. Ключевые свойства:

- **Анонимность**: эксперты не знают, кто дал какую оценку
- **Итерация**: несколько раундов с обратной связью
- **Контролируемая обратная связь**: после каждого раунда участники получают агрегированную статистику группы
- **Статистическая агрегация**: финальный результат -- медиана/среднее группы, а не голосование

Доказанные преимущества: подавление эффекта якорения, снижение давления авторитета, более калиброванные вероятности по сравнению с одиночными экспертами (Rowe & Wright, 2001).

### 1.2 Наша адаптация: LLM-агенты как эксперты

Замена человеческих экспертов на LLM-агентов с чётко определёнными когнитивными профилями. Каждый агент:

- Имеет фиксированный системный промпт, определяющий его аналитическую рамку
- Получает одинаковый набор данных (EventTrajectory[] + CrossImpactMatrix)
- Работает на **отдельной LLM-модели** (критически важно, см. 1.3)
- Не имеет доступа к выводам других агентов до синтеза медиатора

### 1.3 Почему модельное разнообразие обязательно

Исследование **AIA Forecaster** (Schoenegger et al., 2024) показало: если все агенты в ансамбле используют одну модель, их ошибки сильно коррелируют. Коррелированные ошибки не компенсируются при агрегации -- ансамбль из 5 копий одной модели лишь незначительно лучше одного вызова.

Наша стратегия: **каждый агент работает на модели от другого провайдера или семейства**. Это максимизирует разнообразие ошибок и делает агрегацию эффективной.

### 1.4 Почему медиатор критичен

Исследование **DeLLMphi** (Zhao et al., 2024) воспроизвело Дельфи с LLM и показало: если агентам во втором раунде дать только медианные оценки группы (как в классическом Дельфи), улучшения минимальны. LLM просто сдвигается к медиане без содержательной ревизии.

Решение: вместо голой статистики, **медиатор формулирует содержательные вопросы** -- где именно эксперты не согласны и какой фактический вопрос стоит за каждым расхождением. Это заставляет LLM-агентов пересматривать свои аргументы, а не просто двигать числа.

---

## 2. Экспертные персоны (`personas.py`)

### 2.0 Общая архитектура персон

Каждая персона -- инстанс `ExpertPersona`, который определяет:
- Системный промпт (идентичность + аналитическая рамка)
- Назначенную LLM-модель
- Когнитивное смещение (осознанное и управляемое)
- Начальный вес для агрегации (до накопления Brier-статистики)

```python
# src/agents/forecasters/personas.py

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from src.schemas.agent import PersonaAssessment


class PersonaID(str, Enum):
    """Идентификаторы экспертных персон."""
    REALIST = "realist"
    GEOSTRATEG = "geostrateg"
    ECONOMIST = "economist"
    MEDIA_EXPERT = "media_expert"
    DEVILS_ADVOCATE = "devils_advocate"


@dataclass(frozen=True)
class CognitiveBias:
    """Описание осознанного когнитивного смещения персоны."""
    over_predicts: str      # что персона систематически переоценивает
    under_predicts: str     # что персона систематически недооценивает
    anchor_type: str        # к чему привязывается при неопределённости


@dataclass
class ExpertPersona:
    """Конфигурация экспертной персоны для Дельфи-симуляции."""
    id: PersonaID
    name_ru: str
    model_id: str               # e.g. "anthropic/claude-sonnet-4"
    model_rationale: str        # почему эта модель для этой персоны
    cognitive_bias: CognitiveBias
    initial_weight: float       # начальный вес до калибровки (0.0-1.0)
    prompt_doc_path: str        # путь к docs/prompts/{name}.md
    system_prompt: str          # загружается из prompt_doc_path

    # Рабочие параметры LLM
    temperature: float = 0.7
    max_tokens: int = 4096

    async def assess(
        self,
        trajectories: list["EventTrajectory"],
        cross_impact: "CrossImpactMatrix",
        mediator_feedback: "MediatorSynthesis | None" = None,
        calibration_history: "CalibrationRecord | None" = None,
    ) -> PersonaAssessment:
        """
        Запускает LLM-вызов для получения оценки от персоны.

        В раунде 1: mediator_feedback=None.
        В раунде 2: mediator_feedback содержит синтез расхождений.
        calibration_history: история калибровки из предыдущих прогнозов.
        """
        ...
```

### 2.1 Реалист-аналитик

**Идентичность**: Опытный аналитик политических рисков с 20-летним стажем работы в консалтинге (условный профиль -- Eurasia Group, Oxford Analytica). Мыслит категориями базовых ставок (base rates), исторических аналогий и институциональной инерции. Скептически относится к заявлениям о «беспрецедентности» событий. Первый вопрос к любому прогнозу: «Как часто подобное происходило раньше, и каков был исход?»

Аналитическая рамка построена на принципе Филипа Тетлока (Superforecasting): начинать с внешнего вида (outside view), потом корректировать на основе специфики кейса. Реалист-аналитик -- якорь группы, препятствующий дрейфу в сенсационность.

**Когнитивное смещение** (управляемое):
- **Переоценивает**: инерцию статус-кво, предсказуемость бюрократических процессов, силу институтов
- **Недооценивает**: черных лебедей, скорость эскалации, роль личных решений лидеров
- **Якорь при неопределённости**: исторические прецеденты, даже если контекст существенно изменился

**Модель**: `anthropic/claude-opus-4.6` (через OpenRouter)
**Обоснование выбора модели**: Claude Opus 4.6 обеспечивает высочайшее качество рассуждений при разумной стоимости ($5/$25 за 1M токенов). Diversity ансамбля обеспечивается промптами, когнитивными смещениями и аналитическими рамками каждой персоны, а не различием моделей.

**Начальный вес**: 0.22 (чуть выше среднего -- base rate reasoning исторически хорошо калиброван)

**Промпт**: `docs/prompts/realist.md`

---

### 2.2 Геополитический стратег

**Идентичность**: Специалист по международным отношениям с опытом работы в аналитических центрах (условный профиль -- IISS, Chatham House, ИМЭМО РАН). Видит мир через призму силовых балансов, альянсов, стратегических интересов государств. Ключевой вопрос: «Cui bono?» -- кто выигрывает, кто проигрывает, и какова цепочка последствий второго и третьего порядка.

Аналитическая рамка сочетает неореализм (структура международной системы определяет поведение) с конструктивизмом (нарративы и идентичности формируют восприятие угроз). Особое внимание к тому, как внутриполитические факторы проецируются на международную арену, и наоборот. Мыслит «деревьями решений» -- если X произойдёт, то Y отреагирует так, что Z будет вынужден...

**Когнитивное смещение** (управляемое):
- **Переоценивает**: рациональность государственных акторов, значимость геополитических факторов по сравнению с экономическими/социальными, скорость реакции международных институтов
- **Недооценивает**: внутриполитические случайности, роль технологий, экономическую мотивацию негосударственных акторов
- **Якорь при неопределённости**: модель великодержавного соперничества

**Модель**: `anthropic/claude-opus-4.6` (через OpenRouter)
**Обоснование выбора модели**: Claude Opus 4.6 обеспечивает высочайшее качество рассуждений при разумной стоимости ($5/$25 за 1M токенов). Diversity ансамбля обеспечивается промптами, когнитивными смещениями и аналитическими рамками каждой персоны, а не различием моделей.

**Начальный вес**: 0.20

**Промпт**: `docs/prompts/geostrateg.md`

---

### 2.3 Экономический аналитик

**Идентичность**: Макроэкономист и рыночный аналитик с опытом в инвестиционных банках и экономических изданиях (условный профиль -- Goldman Sachs Research, The Economist Intelligence Unit). Следит за деньгами: потоки капитала, фискальная политика, корпоративные интересы, санкционные режимы, цены на сырьё. Любое политическое решение анализирует через призму экономических стимулов и ограничений.

Аналитическая рамка основана на институциональной экономике и теории общественного выбора. Правительства и корпорации -- рациональные агенты с бюджетными ограничениями. «Следуй за деньгами» -- базовый принцип. Особое внимание к датам экономических релизов, заседаниям центральных банков, корпоративной отчётности -- они создают предсказуемые новостные поводы.

**Когнитивное смещение** (управляемое):
- **Переоценивает**: экономическую рациональность акторов, предсказательную силу рыночных индикаторов, значимость экономических данных для медиа-повестки
- **Недооценивает**: идеологические и эмоциональные факторы, роль случайности (теракты, катастрофы), культурные войны
- **Якорь при неопределённости**: экономический календарь и рыночный консенсус

**Модель**: `anthropic/claude-opus-4.6` (через OpenRouter)
**Обоснование выбора модели**: Claude Opus 4.6 обеспечивает высочайшее качество рассуждений при разумной стоимости ($5/$25 за 1M токенов). Diversity ансамбля обеспечивается промптами, когнитивными смещениями и аналитическими рамками каждой персоны, а не различием моделей.

**Начальный вес**: 0.20

**Промпт**: `docs/prompts/economist.md`

---

### 2.4 Медиа-эксперт

**Идентичность**: Бывший редактор крупного новостного агентства, ныне медиа-аналитик и преподаватель журналистики (условный профиль -- Reuters/ТАСС + факультет журналистики). Думает категориями «что попадёт в выпуск»: новостная ценность, эмоциональный заряд, визуальность, конфликтность, наличие говорящей головы. Понимает внутреннюю кухню редакции -- дедлайны, источники, редакционную политику.

Аналитическая рамка построена на теории гейткипинга и фрейминга. Любое событие может быть подано десятком способов -- выбор фрейма определяется не «объективной значимостью», а редакционной логикой: что даст трафик, что соответствует линии издания, что сейчас «в цикле». Особое внимание к медиа-насыщенности (saturation): если тема уже 2 недели в топе, издание будет искать свежий угол или переключится.

**Когнитивное смещение** (управляемое):
- **Переоценивает**: значимость медиа-циклов и информационных трендов, предсказуемость редакционных решений, роль «человеческого интереса» в новостях
- **Недооценивает**: технические и процедурные события (регуляторные решения, стандарты), медленно развивающиеся кризисы, новости без яркого визуального ряда
- **Якорь при неопределённости**: текущий новостной цикл и тематический баланс издания

**Модель**: `anthropic/claude-opus-4.6` (через OpenRouter)
**Обоснование выбора модели**: Claude Opus 4.6 обеспечивает высочайшее качество рассуждений при разумной стоимости ($5/$25 за 1M токенов). Diversity ансамбля обеспечивается промптами, когнитивными смещениями и аналитическими рамками каждой персоны, а не различием моделей. Русскоязычная стилистика обеспечивается промптом персоны.

**Начальный вес**: 0.18 (медиа-экспертиза важна для формулировки, меньше для оценки вероятностей)

**Промпт**: `docs/prompts/media-expert.md`

---

### 2.5 Адвокат дьявола

**Идентичность**: Систематический контрариан и специалист по анализу рисков (условный профиль -- red team аналитик в разведывательном сообществе + Nassim Taleb школа). Его задача -- не согласиться, а **найти то, что остальные пропустили**. Применяет технику pre-mortem: «Допустим, наш прогноз провалился -- что именно пошло не так?» Ищет чёрных лебедей, слепые зоны группы, некорректные предпосылки.

Аналитическая рамка основана на антихрупкости и теории нормальных аварий (Perrow). Сложные системы порождают непредсказуемые отказы. Если «все согласны» -- это красный флаг, а не повод для уверенности. Адвокат дьявола обязан предложить минимум одну альтернативу к каждому консенсусному прогнозу, даже если считает консенсус правильным.

**Когнитивное смещение** (управляемое, и в данном случае -- *желаемое*):
- **Переоценивает**: вероятность чёрных лебедей, хрупкость существующих систем, неочевидные каузальные связи
- **Недооценивает**: устойчивость статус-кво, вероятность «скучных» исходов, стабильность институтов
- **Якорь при неопределённости**: маловероятные, но высокоимпактные сценарии

**Модель**: `anthropic/claude-opus-4.6` (через OpenRouter)
**Обоснование выбора модели**: Claude Opus 4.6 обеспечивает высочайшее качество рассуждений при разумной стоимости ($5/$25 за 1M токенов). Diversity ансамбля обеспечивается промптами, когнитивными смещениями и аналитическими рамками каждой персоны, а не различием моделей. Контринтуитивные сценарии обеспечиваются промптом и повышенной temperature=0.9.

**Начальный вес**: 0.20 (парадоксально высокий -- контрарианские прогнозы добавляют ценность ансамблю при агрегации, даже когда не верны в большинстве случаев)

**Промпт**: `docs/prompts/devils-advocate.md`

---

### 2.6 Схема выхода персоны: `PersonaAssessment`

```python
# src/schemas/agent.py (фрагмент)

from pydantic import BaseModel, Field
from enum import Enum


class ScenarioType(StrEnum):
    """Тип сценария развития / оценки (единый enum, определён в events.py)."""
    BASELINE = "baseline"       # наиболее вероятный
    OPTIMISTIC = "optimistic"   # оптимистичный / эскалация
    PESSIMISTIC = "pessimistic" # пессимистичный / деэскалация
    BLACK_SWAN = "black_swan"   # маловероятный высокоимпактный
    WILDCARD = "wildcard"       # неожиданный поворот


class PredictionItem(BaseModel):
    """Единичный прогноз внутри оценки персоны."""
    event_thread_id: str = Field(
        description="ID EventThread, к которому относится прогноз"
    )
    prediction: str = Field(
        description="Что именно произойдёт (конкретное утверждение, не общие слова)"
    )
    probability: float = Field(
        ge=0.0, le=1.0,
        description="Оценка вероятности (0.0-1.0)"
    )
    newsworthiness: float = Field(
        ge=0.0, le=1.0,
        description="Насколько это станет новостью (0.0-1.0)"
    )
    scenario_type: ScenarioType = Field(
        description="Тип сценария"
    )
    reasoning: str = Field(
        description="Цепочка рассуждений, приведшая к оценке (3-7 предложений)"
    )
    key_assumptions: list[str] = Field(
        description="Ключевые предпосылки, на которых основан прогноз (2-4 штуки)"
    )
    evidence: list[str] = Field(
        description="Ссылки на конкретные факты из входных данных"
    )
    conditional_on: list[str] = Field(
        default_factory=list,
        description="ID других PredictionItem, от которых зависит этот прогноз"
    )


class PersonaAssessment(BaseModel):
    """Полная оценка от одной экспертной персоны за один раунд Дельфи."""
    persona_id: str = Field(description="ID персоны (PersonaID)")
    round_number: int = Field(ge=1, le=2, description="Номер раунда Дельфи")
    predictions: list[PredictionItem] = Field(
        min_length=5, max_length=15,
        description="Список прогнозов (5-15 штук)"
    )
    cross_impacts_noted: list[str] = Field(
        default_factory=list,
        description="Замеченные перекрёстные влияния ('если A, то B вероятнее')"
    )
    blind_spots: list[str] = Field(
        default_factory=list,
        description="Что, по мнению персоны, группа может пропустить"
    )
    confidence_self_assessment: float = Field(
        ge=0.0, le=1.0,
        description="Самооценка общей уверенности в своём анализе (мета-калибровка)"
    )

    # Только для раунда 2
    revisions_made: list[str] = Field(
        default_factory=list,
        description="Что было пересмотрено после обратной связи медиатора"
    )
    revision_rationale: str = Field(
        default="",
        description="Почему эти ревизии были сделаны (или почему позиция не изменилась)"
    )
```

---

## 3. Delphi Orchestrator (`delphi.py`)

Оркестратор управляет двухраундовой Дельфи-симуляцией. Ответственен за параллельный запуск агентов, передачу данных медиатору и обратно, обработку отказов.

### 3.1 Архитектура

```
        ┌──────────────────────────────────────────┐
        │            DelphiOrchestrator             │
        │                                           │
        │  run(trajectories, cross_impact, ctx)     │
        │          │                                │
        │          ├── round_1()                    │
        │          │   └── 5 personas in parallel   │
        │          │                                │
        │          ├── mediate()                    │
        │          │   └── Mediator.synthesize()    │
        │          │                                │
        │          ├── round_2()                    │
        │          │   └── 5 personas in parallel   │
        │          │       (with mediator feedback) │
        │          │                                │
        │          ├── supervisor_search()          │
        │          │   (optional, if spread > 0.25) │
        │          │                                │
        │          └── judge()                      │
        │              └── Judge.evaluate()         │
        └──────────────────────────────────────────┘
```

### 3.2 Полная реализация

```python
# src/agents/forecasters/delphi.py

import asyncio
import logging
from dataclasses import dataclass, field

from src.agents.base import BaseAgent, AgentResult
from src.agents.forecasters.personas import (
    ExpertPersona,
    PersonaID,
    PERSONAS,  # dict[PersonaID, ExpertPersona] -- реестр всех 5 персон
)
from src.agents.forecasters.mediator import Mediator, MediatorSynthesis
from src.agents.forecasters.judge import Judge
from src.schemas.agent import PersonaAssessment
from src.schemas.events import EventTrajectory, CrossImpactMatrix
from src.schemas.pipeline import PipelineContext, StageResult
from src.schemas.headline import RankedPrediction

logger = logging.getLogger(__name__)

MIN_AGENTS_FOR_VALID_DELPHI = 3
SPREAD_THRESHOLD_FOR_SEARCH = 0.25


@dataclass
class DelphiRoundResult:
    """Результат одного раунда Дельфи."""
    round_number: int
    assessments: dict[PersonaID, PersonaAssessment]
    failed_agents: list[PersonaID] = field(default_factory=list)
    duration_ms: int = 0


class DelphiOrchestrator(BaseAgent):
    """
    Оркестратор двухраундовой Дельфи-симуляции.

    Управляет жизненным циклом:
    1. Раунд 1: параллельный запуск 5 персон
    2. Медиация: синтез расхождений
    3. Раунд 2: параллельная ревизия с обратной связью
    4. (опционально) Supervisor search
    5. Передача результатов Judge для агрегации
    """

    name = "delphi_orchestrator"
    description = "Двухраундовая Дельфи-симуляция с 5 экспертными персонами"

    def __init__(
        self,
        personas: dict[PersonaID, ExpertPersona] | None = None,
        mediator: Mediator | None = None,
        judge: Judge | None = None,
    ):
        self.personas = personas or PERSONAS
        self.mediator = mediator or Mediator()
        self.judge = judge or Judge()

    async def run(
        self,
        trajectories: list[EventTrajectory],
        cross_impact: CrossImpactMatrix,
        ctx: PipelineContext,
    ) -> list[RankedPrediction]:
        """
        Полный цикл Дельфи-симуляции.

        Args:
            trajectories: Список траекторий событий из Stage 3.
            cross_impact: Матрица перекрёстных влияний.
            ctx: Контекст пайплайна (для SSE-обновлений, логирования).

        Returns:
            Ранжированный список прогнозов, готовых для Stage 7 (Framing).

        Raises:
            DelphiQuorumError: Если менее 3 агентов дали результат.
        """
        # --- Раунд 1 ---
        await ctx.emit_progress("delphi_round_1_start", detail="Запуск 5 экспертов...")
        round1 = await self._run_round(
            round_number=1,
            trajectories=trajectories,
            cross_impact=cross_impact,
            mediator_feedback=None,
            ctx=ctx,
        )
        self._validate_quorum(round1)

        # --- Медиация ---
        await ctx.emit_progress("mediation_start", detail="Синтез расхождений...")
        synthesis = await self.mediator.synthesize(
            assessments=list(round1.assessments.values()),
            trajectories=trajectories,
        )

        # --- Раунд 2 ---
        await ctx.emit_progress("delphi_round_2_start", detail="Ревизия прогнозов...")
        round2 = await self._run_round(
            round_number=2,
            trajectories=trajectories,
            cross_impact=cross_impact,
            mediator_feedback=synthesis,
            ctx=ctx,
        )
        self._validate_quorum(round2)

        # --- Supervisor Search (если нужен) ---
        max_spread = self._compute_max_spread(round2)
        if max_spread > SPREAD_THRESHOLD_FOR_SEARCH:
            await ctx.emit_progress(
                "supervisor_search",
                detail=f"Разброс {max_spread:.2f} > {SPREAD_THRESHOLD_FOR_SEARCH}, поиск фактов..."
            )
            supplementary_facts = await self._supervisor_search(
                synthesis=synthesis,
                round2=round2,
                ctx=ctx,
            )
            synthesis.supplementary_facts = supplementary_facts

        # --- Judge ---
        await ctx.emit_progress("judge_start", detail="Агрегация и ранжирование...")
        ranked = await self.judge.evaluate(
            round1=round1,
            round2=round2,
            synthesis=synthesis,
            outlet_profile=ctx.outlet_profile,
        )

        return ranked

    async def _run_round(
        self,
        round_number: int,
        trajectories: list[EventTrajectory],
        cross_impact: CrossImpactMatrix,
        mediator_feedback: MediatorSynthesis | None,
        ctx: PipelineContext,
    ) -> DelphiRoundResult:
        """
        Запускает один раунд Дельфи: все персоны параллельно.

        Обрабатывает отказы отдельных агентов gracefully:
        агент, упавший с ошибкой, помечается в failed_agents,
        но раунд продолжается с оставшимися.
        """
        tasks: dict[PersonaID, asyncio.Task] = {}

        async with asyncio.TaskGroup() as tg:
            for pid, persona in self.personas.items():
                task = tg.create_task(
                    self._run_single_persona(
                        persona=persona,
                        round_number=round_number,
                        trajectories=trajectories,
                        cross_impact=cross_impact,
                        mediator_feedback=mediator_feedback,
                        ctx=ctx,
                    ),
                    name=f"delphi_r{round_number}_{pid.value}",
                )
                tasks[pid] = task

        # Собираем результаты, обрабатываем ошибки
        assessments: dict[PersonaID, PersonaAssessment] = {}
        failed: list[PersonaID] = []

        for pid, task in tasks.items():
            try:
                result = task.result()
                if result is not None:
                    assessments[pid] = result
                else:
                    failed.append(pid)
            except Exception as e:
                logger.error(f"Persona {pid.value} failed in round {round_number}: {e}")
                failed.append(pid)
                await ctx.emit_progress(
                    f"agent_failed",
                    detail=f"{pid.value}: {type(e).__name__}"
                )

        return DelphiRoundResult(
            round_number=round_number,
            assessments=assessments,
            failed_agents=failed,
        )

    async def _run_single_persona(
        self,
        persona: ExpertPersona,
        round_number: int,
        trajectories: list[EventTrajectory],
        cross_impact: CrossImpactMatrix,
        mediator_feedback: MediatorSynthesis | None,
        ctx: PipelineContext,
    ) -> PersonaAssessment | None:
        """
        Запускает одну персону с retry и fallback.

        Retry policy:
        - 1 retry на ту же модель при API ошибке
        - 1 fallback на альтернативную модель при повторной ошибке
        - None при полном отказе (агент исключается из раунда)
        """
        calibration_history = await ctx.get_calibration_history(persona.id)

        try:
            return await persona.assess(
                trajectories=trajectories,
                cross_impact=cross_impact,
                mediator_feedback=mediator_feedback,
                calibration_history=calibration_history,
            )
        except Exception as e:
            logger.warning(f"First attempt failed for {persona.id.value}: {e}")

        # Retry: та же модель
        try:
            return await persona.assess(
                trajectories=trajectories,
                cross_impact=cross_impact,
                mediator_feedback=mediator_feedback,
                calibration_history=calibration_history,
            )
        except Exception as e:
            logger.warning(f"Retry failed for {persona.id.value}: {e}")

        # Fallback: альтернативная модель
        fallback_model = self._get_fallback_model(persona.model_id)
        if fallback_model:
            try:
                original_model = persona.model_id
                persona.model_id = fallback_model
                result = await persona.assess(
                    trajectories=trajectories,
                    cross_impact=cross_impact,
                    mediator_feedback=mediator_feedback,
                    calibration_history=calibration_history,
                )
                persona.model_id = original_model  # восстановить
                return result
            except Exception as e:
                logger.error(f"Fallback also failed for {persona.id.value}: {e}")
                persona.model_id = original_model

        return None

    def _validate_quorum(self, round_result: DelphiRoundResult) -> None:
        """
        Проверяет, что достаточно агентов завершили раунд.

        Raises:
            DelphiQuorumError: Если менее MIN_AGENTS_FOR_VALID_DELPHI.
        """
        active = len(round_result.assessments)
        if active < MIN_AGENTS_FOR_VALID_DELPHI:
            raise DelphiQuorumError(
                f"Только {active} агентов завершили раунд "
                f"{round_result.round_number}, "
                f"минимум {MIN_AGENTS_FOR_VALID_DELPHI} для валидной Дельфи. "
                f"Упавшие: {round_result.failed_agents}"
            )

    def _compute_max_spread(self, round_result: DelphiRoundResult) -> float:
        """
        Вычисляет максимальный разброс вероятностей по всем прогнозам.

        Для каждого event_thread_id: spread = max(prob) - min(prob)
        среди всех агентов, давших прогноз по этому событию.

        Returns:
            Максимальный spread среди всех событий.
        """
        from collections import defaultdict
        event_probs: dict[str, list[float]] = defaultdict(list)

        for assessment in round_result.assessments.values():
            for pred in assessment.predictions:
                event_probs[pred.event_thread_id].append(pred.probability)

        if not event_probs:
            return 0.0

        spreads = [
            max(probs) - min(probs)
            for probs in event_probs.values()
            if len(probs) >= 2
        ]
        return max(spreads) if spreads else 0.0

    async def _supervisor_search(
        self,
        synthesis: MediatorSynthesis,
        round2: DelphiRoundResult,
        ctx: PipelineContext,
    ) -> list[str]:
        """
        Дополнительный веб-поиск для разрешения оставшихся расхождений.

        Берёт key_questions из MediatorSynthesis, по которым
        spread остался > 0.25, и ищет свежие факты.

        Returns:
            Список найденных фактов (текстовые сниппеты).
        """
        unresolved = [
            dispute.key_question
            for dispute in synthesis.disputes
            if dispute.spread >= SPREAD_THRESHOLD_FOR_SEARCH
        ]

        if not unresolved:
            return []

        # Используем web search из data_sources
        from src.data_sources.web_search import search_facts
        facts = []
        for question in unresolved[:3]:  # максимум 3 поиска
            results = await search_facts(question)
            facts.extend(results)

        return facts

    @staticmethod
    def _get_fallback_model(primary_model: str) -> str | None:
        """
        Возвращает fallback-модель для данной primary.

        Цепочки fallback:
        - claude-sonnet-4 → gpt-4o
        - gpt-4o → claude-sonnet-4
        - gemini-2.5-pro → gpt-4o
        - yandexgpt → claude-sonnet-4
        - llama-3.3-70b → gemini-2.5-pro
        """
        fallback_chain: dict[str, str] = {
            "anthropic/claude-sonnet-4": "openai/gpt-4o",
            "openai/gpt-4o": "anthropic/claude-sonnet-4",
            "google/gemini-2.5-pro": "openai/gpt-4o",
            "yandexgpt": "anthropic/claude-sonnet-4",
            "meta-llama/llama-3.3-70b-instruct": "google/gemini-2.5-pro",
        }
        return fallback_chain.get(primary_model)


class DelphiQuorumError(Exception):
    """Недостаточно агентов для валидной Дельфи-симуляции."""
    pass
```

### 3.3 Гарантии анонимности

В классическом Дельфи анонимность -- ключевое свойство. В нашей реализации:

| Раунд | Что получает агент | Чего НЕ получает |
|---|---|---|
| R1 | EventTrajectory[], CrossImpactMatrix, CalibrationHistory | Ничего от других агентов |
| R2 | Свой R1 + MediatorSynthesis | Чужие PersonaAssessment, чужие persona_id |

Медиатор в `MediatorSynthesis` ссылается на позиции как "Эксперт A, Эксперт B" (анонимизированные метки), никогда не раскрывая PersonaID. Это предотвращает ситуацию, когда агент "подстраивается" под конкретную роль (например, всегда соглашаясь с Реалистом).

---

## 4. Медиатор (`mediator.py`)

Медиатор -- критическая связка между раундами Дельфи. Его задача не агрегировать (это делает Judge), а **выявить и структурировать разногласия** для продуктивной ревизии.

### 4.1 Логика работы

```
5 x PersonaAssessment (R1)
        │
        ▼
┌───────────────────────────────┐
│         Mediator              │
│                               │
│  1. Cluster predictions by    │
│     event_thread_id           │
│                               │
│  2. For each event:           │
│     ├─ Compute spread         │
│     ├─ Identify consensus     │
│     │  (spread < 0.15)        │
│     ├─ Identify disputes      │
│     │  (spread >= 0.15)       │
│     └─ Flag gaps (events      │
│        predicted by < 3)      │
│                               │
│  3. For each dispute:         │
│     └─ LLM: formulate the    │
│        key factual question   │
│        that would resolve it  │
│                               │
│  4. Cross-impact check:       │
│     └─ Where prediction A     │
│        depends on prediction  │
│        B but agents disagree  │
│        on B                   │
│                               │
│  5. Generate anonymized       │
│     feedback brief            │
└───────────────────────────────┘
        │
        ▼
   MediatorSynthesis
```

### 4.2 Реализация

```python
# src/agents/forecasters/mediator.py

import logging
from collections import defaultdict
from statistics import median

from src.agents.base import BaseAgent
from src.schemas.agent import PersonaAssessment, PredictionItem
from src.schemas.events import EventTrajectory
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class Mediator(BaseAgent):
    """
    Синтезирует результаты раунда Дельфи.

    НЕ агрегирует вероятности (это делает Judge).
    Вместо этого:
    - Выявляет области консенсуса и расхождений
    - Формулирует ключевые вопросы для разрешения споров
    - Проверяет перекрёстные зависимости
    - Готовит анонимизированную обратную связь для раунда 2
    """

    name = "mediator"
    description = "Синтез расхождений между экспертами Дельфи"

    CONSENSUS_THRESHOLD = 0.15   # spread < 0.15 = консенсус
    DISPUTE_THRESHOLD = 0.15     # spread >= 0.15 = расхождение
    GAP_MIN_AGENTS = 3           # если < 3 агентов упомянули событие = пробел

    def __init__(self, llm_router: LLMRouter | None = None):
        self.llm = llm_router or LLMRouter()

    async def synthesize(
        self,
        assessments: list[PersonaAssessment],
        trajectories: list[EventTrajectory],
    ) -> "MediatorSynthesis":
        """
        Основной метод: принимает оценки R1, возвращает структурированный синтез.

        Args:
            assessments: Список PersonaAssessment от всех активных персон.
            trajectories: Исходные EventTrajectory (для контекста).

        Returns:
            MediatorSynthesis с консенсусами, расхождениями, пробелами
            и рекомендациями для R2.
        """
        # 1. Группировка по event_thread_id
        event_groups = self._group_by_event(assessments)

        # 2. Классификация: консенсус / расхождение / пробел
        consensus_items: list[ConsensusArea] = []
        disputes: list[DisputeArea] = []
        gaps: list[GapArea] = []

        for event_id, predictions_by_agent in event_groups.items():
            probs = [p.probability for p in predictions_by_agent.values()]
            spread = max(probs) - min(probs) if len(probs) >= 2 else 0.0
            median_prob = median(probs)
            num_agents = len(predictions_by_agent)

            if num_agents < self.GAP_MIN_AGENTS:
                gaps.append(GapArea(
                    event_thread_id=event_id,
                    mentioned_by=list(predictions_by_agent.keys()),
                    note=f"Только {num_agents} из {len(assessments)} экспертов упомянули это событие",
                ))
            elif spread < self.CONSENSUS_THRESHOLD:
                consensus_items.append(ConsensusArea(
                    event_thread_id=event_id,
                    median_probability=median_prob,
                    spread=spread,
                    num_agents=num_agents,
                ))
            else:
                disputes.append(DisputeArea(
                    event_thread_id=event_id,
                    median_probability=median_prob,
                    spread=spread,
                    positions=self._anonymize_positions(predictions_by_agent),
                    key_question="",  # заполняется ниже через LLM
                ))

        # 3. LLM: формулировка ключевых вопросов для каждого расхождения
        if disputes:
            disputes = await self._formulate_key_questions(
                disputes=disputes,
                trajectories=trajectories,
            )

        # 4. Проверка перекрёстных зависимостей
        cross_impact_flags = self._check_cross_impacts(
            assessments=assessments,
            disputes=disputes,
        )

        # 5. Сборка итогового синтеза
        return MediatorSynthesis(
            consensus_areas=consensus_items,
            disputes=disputes,
            gaps=gaps,
            cross_impact_flags=cross_impact_flags,
            overall_summary=await self._generate_summary(
                consensus_items, disputes, gaps
            ),
            supplementary_facts=[],  # заполняется supervisor_search если нужен
        )

    def _group_by_event(
        self,
        assessments: list[PersonaAssessment],
    ) -> dict[str, dict[str, PredictionItem]]:
        """
        Группирует прогнозы всех агентов по event_thread_id.

        Returns:
            {event_thread_id: {anonymized_label: PredictionItem}}
        """
        result: dict[str, dict[str, PredictionItem]] = defaultdict(dict)
        labels = iter("ABCDEFGHIJ")  # анонимизированные метки
        persona_to_label: dict[str, str] = {}

        for assessment in assessments:
            if assessment.persona_id not in persona_to_label:
                persona_to_label[assessment.persona_id] = f"Эксперт {next(labels)}"

            label = persona_to_label[assessment.persona_id]
            for pred in assessment.predictions:
                result[pred.event_thread_id][label] = pred

        return dict(result)

    def _anonymize_positions(
        self,
        predictions_by_agent: dict[str, PredictionItem],
    ) -> list["AnonymizedPosition"]:
        """
        Готовит анонимизированный список позиций для передачи агентам в R2.
        """
        return [
            AnonymizedPosition(
                agent_label=label,
                probability=pred.probability,
                reasoning_summary=pred.reasoning[:200],  # усечённое
                key_assumptions=pred.key_assumptions,
            )
            for label, pred in predictions_by_agent.items()
        ]

    async def _formulate_key_questions(
        self,
        disputes: list["DisputeArea"],
        trajectories: list[EventTrajectory],
    ) -> list["DisputeArea"]:
        """
        Для каждого расхождения формулирует ключевой фактический вопрос,
        ответ на который разрешил бы спор.

        Использует LLM (Claude Opus) для формулировки вопросов.
        """
        # Подготовка промпта для LLM
        for dispute in disputes:
            prompt = self._build_key_question_prompt(dispute, trajectories)

            response = await self.llm.call(
                model_tier="strong",  # Claude Opus
                system_prompt="Ты -- модератор экспертной дискуссии. "
                    "Твоя задача -- сформулировать один конкретный фактический вопрос, "
                    "ответ на который разрешит расхождение между экспертами.",
                user_prompt=prompt,
                max_tokens=256,
                temperature=0.3,
            )
            dispute.key_question = response.content

        return disputes

    def _build_key_question_prompt(
        self,
        dispute: "DisputeArea",
        trajectories: list[EventTrajectory],
    ) -> str:
        """Строит промпт для формулировки ключевого вопроса."""
        positions_text = "\n".join(
            f"- {pos.agent_label}: вероятность {pos.probability:.0%}, "
            f"обоснование: {pos.reasoning_summary}"
            for pos in dispute.positions
        )

        return (
            f"Событие: {dispute.event_thread_id}\n"
            f"Разброс оценок: {dispute.spread:.0%}\n"
            f"Позиции экспертов:\n{positions_text}\n\n"
            f"Сформулируй один конкретный фактический вопрос, "
            f"ответ на который сблизит оценки."
        )

    def _check_cross_impacts(
        self,
        assessments: list[PersonaAssessment],
        disputes: list["DisputeArea"],
    ) -> list["CrossImpactFlag"]:
        """
        Проверяет: если прогноз A зависит от прогноза B (conditional_on),
        а по B есть расхождение -- это нужно подсветить.
        """
        disputed_events = {d.event_thread_id for d in disputes}
        flags: list[CrossImpactFlag] = []

        for assessment in assessments:
            for pred in assessment.predictions:
                for dep_id in pred.conditional_on:
                    if dep_id in disputed_events:
                        flags.append(CrossImpactFlag(
                            prediction_event_id=pred.event_thread_id,
                            depends_on_event_id=dep_id,
                            note=(
                                f"Прогноз по '{pred.event_thread_id}' зависит от "
                                f"'{dep_id}', по которому есть расхождение"
                            ),
                        ))

        return flags

    async def _generate_summary(
        self,
        consensus: list["ConsensusArea"],
        disputes: list["DisputeArea"],
        gaps: list["GapArea"],
    ) -> str:
        """
        Генерирует текстовое резюме для включения в MediatorSynthesis.
        Используется агентами в раунде 2 как высокоуровневый контекст.
        """
        summary_parts = []

        if consensus:
            summary_parts.append(
                f"Консенсус по {len(consensus)} событиям "
                f"(разброс < {self.CONSENSUS_THRESHOLD:.0%})."
            )
        if disputes:
            summary_parts.append(
                f"Расхождения по {len(disputes)} событиям. "
                f"Максимальный разброс: {max(d.spread for d in disputes):.0%}."
            )
        if gaps:
            summary_parts.append(
                f"Пробелы: {len(gaps)} событий упомянуты менее чем 3 экспертами."
            )

        return " ".join(summary_parts)
```

### 4.3 Схемы данных медиатора

```python
# src/schemas/agent.py (дополнение)

from pydantic import BaseModel, Field


class AnonymizedPosition(BaseModel):
    """Анонимизированная позиция одного эксперта по одному событию."""
    agent_label: str = Field(description="Анонимная метка: 'Эксперт A', 'Эксперт B'...")
    probability: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str = Field(description="Усечённое обоснование (до 200 символов)")
    key_assumptions: list[str] = Field(description="Ключевые предпосылки эксперта")


class ConsensusArea(BaseModel):
    """Область консенсуса: все эксперты примерно согласны."""
    event_thread_id: str
    median_probability: float = Field(ge=0.0, le=1.0)
    spread: float = Field(ge=0.0, lt=0.15, description="Разброс < 0.15")
    num_agents: int = Field(ge=3)


class DisputeArea(BaseModel):
    """Область расхождения: значительный разброс между экспертами."""
    event_thread_id: str
    median_probability: float = Field(ge=0.0, le=1.0)
    spread: float = Field(ge=0.15, le=1.0, description="Разброс >= 0.15")
    positions: list[AnonymizedPosition] = Field(
        description="Анонимизированные позиции экспертов"
    )
    key_question: str = Field(
        default="",
        description="Ключевой фактический вопрос для разрешения спора (LLM-generated)"
    )


class GapArea(BaseModel):
    """Пробел: событие упомянуто слишком малым числом экспертов."""
    event_thread_id: str
    mentioned_by: list[str] = Field(description="Анонимные метки экспертов, упомянувших событие")
    note: str


class CrossImpactFlag(BaseModel):
    """Флаг перекрёстного влияния: прогноз зависит от спорного события."""
    prediction_event_id: str
    depends_on_event_id: str
    note: str


class MediatorSynthesis(BaseModel):
    """
    Полный синтез медиатора между раундами Дельфи.

    Передаётся каждому агенту в раунде 2 (но без раскрытия persona_id).
    """
    consensus_areas: list[ConsensusArea] = Field(
        description="События с консенсусом (spread < 0.15)"
    )
    disputes: list[DisputeArea] = Field(
        description="События с расхождениями (spread >= 0.15)"
    )
    gaps: list[GapArea] = Field(
        description="События, упомянутые < 3 экспертами"
    )
    cross_impact_flags: list[CrossImpactFlag] = Field(
        description="Прогнозы, зависящие от спорных событий"
    )
    overall_summary: str = Field(
        description="Текстовое резюме для контекста раунда 2"
    )
    supplementary_facts: list[str] = Field(
        default_factory=list,
        description="Дополнительные факты из supervisor search (заполняется позже)"
    )
```

---

## 5. Судья (`judge.py`)

Judge -- финальная стадия Дельфи. Принимает результаты обоих раундов и производит калиброванный, ранжированный список прогнозов для передачи генераторам.

> **v0.7.0**: Judge разделён на два детерминистических шага (без LLM-вызова):
> - **Step 6a** `_aggregate_timeline()` → `PredictedTimeline` (event-level aggregation с predicted_date, uncertainty_days, causal_dependencies)
> - **Step 6b** `_select_headlines(timeline)` → `RankedPrediction[]` (headline scoring с temporal proximity factor)
>
> `PredictedTimeline` сохраняется в `PipelineContext.predicted_timeline` для eval pipeline.
> `RankedPrediction` output contract сохранён — Stages 7-9 не затронуты.
>
> **Horizon-aware**: Judge применяет `HORIZON_WEIGHT_ADJUSTMENTS` — persona weights адаптируются по горизонту (immediate: Media Expert↑, medium: Realist↑).

### 5.1 Алгоритм агрегации

**Шаг 1: Взвешенная медиана**

Для каждого события вычисляется взвешенная медиана вероятностей. Веса определяются на основе исторической точности агентов (Brier score):

```
weight_i = 1 / brier_score_i     (если есть история)
weight_i = initial_weight_i      (cold start)
```

Взвешенная медиана: сортируем (probability, weight) пары, находим точку, где кумулятивный вес достигает 50%.

**Шаг 2: Калибровка (Platt scaling + extremization)**

Агрегированные вероятности проходят через калибровочное преобразование:

```
calibrated_p = sigmoid(a * logit(raw_p) + b)
```

Параметры по умолчанию:
- `a = 1.5` (extremization: сдвигает вероятности от 0.5 к краям, что компенсирует typical LLM underconfidence)
- `b = 0.0` (без смещения)

Обоснование `a = 1.5`: исследования показывают, что ансамбли прогнозистов систематически недостаточно экстремальны -- средняя оценка 0.7 у группы обычно означает, что реальная вероятность ближе к 0.85 (Baron et al., 2014, "Two Reasons to Make Aggregated Probability Forecasts More Extreme").

**Шаг 3: headline_score**

```
headline_score = calibrated_prob * newsworthiness * (1 - saturation) * outlet_relevance
```

Где:
- `calibrated_prob`: калиброванная вероятность (0-1)
- `newsworthiness`: средняя оценка новостной ценности от всех агентов (0-1)
- `saturation`: насколько тема уже насыщена в текущем цикле (0-1, из OutletProfile)
- `outlet_relevance`: насколько тема соответствует профилю издания (0-1, из OutletProfile)

### 5.2 Протокол разрешения разногласий (тиерованный)

| Паттерн | Интерпретация | Действие |
|---|---|---|
| 4-5 агентов согласны (spread < 0.15) | **Консенсус** | Использовать взвешенную медиану, label = "consensus" |
| 3 vs 2 агента (spread 0.15-0.30) | **Мажоритарная позиция с инакомыслием** | Взвешенная медиана + поле `dissenting_views` заполняется позициями меньшинства |
| 2 vs 2 vs 1 или другое (spread > 0.30) | **Нет консенсуса** | Консервативная оценка: медиана * 0.8 (штраф за неопределённость), label = "contested" |

### 5.3 Выбор финального списка

- **Top-7**: события с наивысшим headline_score
- **Wild cards**: 1-2 прогноза от Адвоката дьявола, которые не попали в top-7, но имеют newsworthiness > 0.7 (чёрные лебеди заслуживают внимания)
- **Дедупликация**: если два прогноза по сути об одном -- берём тот, у которого headline_score выше, второй помечаем как альтернативный фрейм

### 5.4 Реализация

```python
# src/agents/forecasters/judge.py

import math
import logging
from statistics import median
from collections import defaultdict

from src.agents.base import BaseAgent
from src.agents.forecasters.delphi import DelphiRoundResult
from src.agents.forecasters.personas import PersonaID
from src.schemas.agent import (
    PersonaAssessment,
    PredictionItem,
    MediatorSynthesis,
)
from src.schemas.headline import (
    RankedPrediction,
    ConfidenceLabel,
    AgreementLevel,
    DissentingView,
)

logger = logging.getLogger(__name__)

# Калибровочные параметры по умолчанию
DEFAULT_EXTREMIZATION_A = 1.5
DEFAULT_BIAS_B = 0.0

# Пороги
CONSENSUS_SPREAD = 0.15
CONTESTED_SPREAD = 0.30
UNCERTAINTY_PENALTY = 0.8

# Выбор
TOP_N_HEADLINES = 7
WILD_CARD_NEWSWORTHINESS_MIN = 0.7
MAX_WILD_CARDS = 2


class Judge(BaseAgent):
    """
    Агрегация, калибровка и ранжирование прогнозов Дельфи.

    Принимает результаты обоих раундов + синтез медиатора.
    Выдаёт калиброванный ранжированный список для генераторов.
    """

    name = "judge"
    description = "Агрегация вероятностей и ранжирование прогнозов"

    def __init__(
        self,
        extremization_a: float = DEFAULT_EXTREMIZATION_A,
        bias_b: float = DEFAULT_BIAS_B,
        brier_scores: dict[str, float] | None = None,
    ):
        """
        Args:
            extremization_a: Параметр extremization для Platt scaling.
            bias_b: Параметр смещения для Platt scaling.
            brier_scores: Исторические Brier scores по persona_id.
                          None = cold start, используются initial_weight.
        """
        self.a = extremization_a
        self.b = bias_b
        self.brier_scores = brier_scores or {}

    async def evaluate(
        self,
        round1: DelphiRoundResult,
        round2: DelphiRoundResult,
        synthesis: MediatorSynthesis,
        outlet_profile: "OutletProfile",
    ) -> list[RankedPrediction]:
        """
        Полный цикл оценки: агрегация → калибровка → скоринг → отбор.

        Использует результаты R2 как основу (R1 -- для контекста
        и понимания того, кто пересмотрел позицию).

        Args:
            round1: Результаты первого раунда.
            round2: Результаты второго раунда (основные для агрегации).
            synthesis: Синтез медиатора.
            outlet_profile: Профиль целевого издания.

        Returns:
            Ранжированный список прогнозов (top-7 + wild cards).
        """
        # 1. Группировка R2 по событиям
        event_data = self._aggregate_by_event(round2)

        # 2. Для каждого события: взвешенная медиана + калибровка + скоринг
        scored_predictions: list[RankedPrediction] = []

        for event_id, agent_predictions in event_data.items():
            # Взвешенная медиана
            raw_prob = self._weighted_median(agent_predictions)

            # Определение уровня согласия
            agreement, spread = self._assess_agreement(agent_predictions)

            # Штраф за неопределённость
            if agreement == AgreementLevel.CONTESTED:
                raw_prob *= UNCERTAINTY_PENALTY

            # Калибровка
            calibrated_prob = self._calibrate(raw_prob)

            # Средняя новостная ценность
            newsworthiness = self._mean_newsworthiness(agent_predictions)

            # Насыщенность и релевантность из OutletProfile
            saturation = outlet_profile.get_topic_saturation(event_id)
            relevance = outlet_profile.get_topic_relevance(event_id)

            # headline_score
            headline_score = (
                calibrated_prob
                * newsworthiness
                * (1.0 - saturation)
                * relevance
            )

            # Сбор reasoning и dissent
            reasoning = self._build_reasoning_chain(agent_predictions, synthesis)
            dissenting = self._collect_dissent(agent_predictions, agreement)
            evidence = self._collect_evidence(agent_predictions)

            scored_predictions.append(RankedPrediction(
                event_thread_id=event_id,
                prediction=self._select_best_prediction_text(agent_predictions),
                calibrated_probability=calibrated_prob,
                raw_probability=raw_prob,
                headline_score=headline_score,
                newsworthiness=newsworthiness,
                confidence_label=self._prob_to_label(calibrated_prob),
                agreement_level=agreement,
                spread=spread,
                reasoning=reasoning,
                evidence_chain=evidence,
                dissenting_views=dissenting,
                is_wild_card=False,
                rank=0,  # заполняется при финальной сортировке
            ))

        # 3. Сортировка и отбор
        scored_predictions.sort(key=lambda p: p.headline_score, reverse=True)
        top_predictions = scored_predictions[:TOP_N_HEADLINES]

        # 4. Wild cards от Адвоката дьявола
        wild_cards = self._select_wild_cards(
            all_predictions=scored_predictions,
            top_predictions=top_predictions,
            round2=round2,
        )

        # 5. Финальный ранжированный список
        final = top_predictions + wild_cards
        for i, pred in enumerate(final, 1):
            pred.rank = i

        return final

    def _weighted_median(
        self,
        agent_predictions: dict[str, PredictionItem],
    ) -> float:
        """
        Вычисляет взвешенную медиану вероятностей.

        Веса: 1/brier_score (если есть история) или initial_weight.
        """
        from src.agents.forecasters.personas import PERSONAS, PersonaID

        weighted_pairs: list[tuple[float, float]] = []  # (prob, weight)

        for persona_id_str, pred in agent_predictions.items():
            if persona_id_str in self.brier_scores:
                brier = self.brier_scores[persona_id_str]
                weight = 1.0 / max(brier, 0.01)  # защита от деления на 0
            else:
                # Cold start: используем initial_weight из конфигурации персоны
                try:
                    pid = PersonaID(persona_id_str)
                    weight = PERSONAS[pid].initial_weight
                except (ValueError, KeyError):
                    weight = 0.20  # дефолт

            weighted_pairs.append((pred.probability, weight))

        # Сортируем по вероятности
        weighted_pairs.sort(key=lambda x: x[0])

        # Находим взвешенную медиану
        total_weight = sum(w for _, w in weighted_pairs)
        cumulative = 0.0
        for prob, weight in weighted_pairs:
            cumulative += weight
            if cumulative >= total_weight / 2:
                return prob

        # Fallback: обычная медиана
        return median([p for p, _ in weighted_pairs])

    def _calibrate(self, raw_prob: float) -> float:
        """
        Platt scaling с extremization.

        calibrated = sigmoid(a * logit(raw) + b)

        Где logit(p) = log(p / (1-p)), sigmoid(x) = 1 / (1 + exp(-x))
        """
        # Clamp для числовой стабильности
        p = max(0.01, min(0.99, raw_prob))

        logit_p = math.log(p / (1.0 - p))
        transformed = self.a * logit_p + self.b
        calibrated = 1.0 / (1.0 + math.exp(-transformed))

        return round(calibrated, 3)

    def _assess_agreement(
        self,
        agent_predictions: dict[str, PredictionItem],
    ) -> tuple["AgreementLevel", float]:
        """
        Определяет уровень согласия между агентами.

        Returns:
            (AgreementLevel, spread)
        """
        probs = [p.probability for p in agent_predictions.values()]
        if len(probs) < 2:
            return AgreementLevel.CONSENSUS, 0.0

        spread = max(probs) - min(probs)

        if spread < CONSENSUS_SPREAD:
            return AgreementLevel.CONSENSUS, spread
        elif spread < CONTESTED_SPREAD:
            return AgreementLevel.MAJORITY_WITH_DISSENT, spread
        else:
            return AgreementLevel.CONTESTED, spread

    def _mean_newsworthiness(
        self, agent_predictions: dict[str, PredictionItem]
    ) -> float:
        """Средняя оценка новостной ценности по всем агентам."""
        values = [p.newsworthiness for p in agent_predictions.values()]
        return sum(values) / len(values) if values else 0.5

    def _select_best_prediction_text(
        self, agent_predictions: dict[str, PredictionItem]
    ) -> str:
        """
        Выбирает текст прогноза от агента, чей probability
        ближе всего к взвешенной медиане (наиболее репрезентативный).
        """
        target = self._weighted_median(agent_predictions)
        return min(
            agent_predictions.values(),
            key=lambda p: abs(p.probability - target),
        ).prediction

    def _build_reasoning_chain(
        self,
        agent_predictions: dict[str, PredictionItem],
        synthesis: MediatorSynthesis,
    ) -> str:
        """Собирает цепочку рассуждений из всех агентов в единый нарратив."""
        parts = []
        for persona_id, pred in agent_predictions.items():
            parts.append(pred.reasoning)
        return " | ".join(parts)

    def _collect_dissent(
        self,
        agent_predictions: dict[str, PredictionItem],
        agreement: "AgreementLevel",
    ) -> list["DissentingView"]:
        """Собирает несогласные позиции, если уровень согласия < consensus."""
        if agreement == AgreementLevel.CONSENSUS:
            return []

        target = self._weighted_median(agent_predictions)
        dissenting = []
        for persona_id, pred in agent_predictions.items():
            if abs(pred.probability - target) > 0.15:
                dissenting.append(DissentingView(
                    agent_label=persona_id,
                    probability=pred.probability,
                    reasoning=pred.reasoning[:300],
                ))
        return dissenting

    def _collect_evidence(
        self,
        agent_predictions: dict[str, PredictionItem],
    ) -> list[dict[str, str]]:
        """Собирает все evidence из всех агентов, дедуплицируя."""
        seen: set[str] = set()
        evidence = []
        for pred in agent_predictions.values():
            for ev in pred.evidence:
                if ev not in seen:
                    seen.add(ev)
                    evidence.append({"source": "agent", "summary": ev})
        return evidence

    def _select_wild_cards(
        self,
        all_predictions: list[RankedPrediction],
        top_predictions: list[RankedPrediction],
        round2: DelphiRoundResult,
    ) -> list[RankedPrediction]:
        """
        Отбирает wild cards от Адвоката дьявола.

        Критерии:
        - Не в top-7
        - Предложен Адвокатом дьявола
        - newsworthiness > 0.7
        - Максимум 2 штуки
        """
        top_ids = {p.event_thread_id for p in top_predictions}

        # Прогнозы Адвоката дьявола
        devils_events: set[str] = set()
        if PersonaID.DEVILS_ADVOCATE in round2.assessments:
            devils = round2.assessments[PersonaID.DEVILS_ADVOCATE]
            for pred in devils.predictions:
                if pred.scenario_type.value == "black_swan":
                    devils_events.add(pred.event_thread_id)

        wild_cards = []
        for pred in all_predictions:
            if (
                pred.event_thread_id not in top_ids
                and pred.event_thread_id in devils_events
                and pred.newsworthiness >= WILD_CARD_NEWSWORTHINESS_MIN
            ):
                pred.is_wild_card = True
                wild_cards.append(pred)
                if len(wild_cards) >= MAX_WILD_CARDS:
                    break

        return wild_cards

    @staticmethod
    def _prob_to_label(prob: float) -> "ConfidenceLabel":
        """
        Преобразует калиброванную вероятность в пользовательскую метку.

        Диапазоны:
        - >= 0.85: очень высокая
        - >= 0.70: высокая
        - >= 0.50: умеренная
        - >= 0.30: низкая
        - < 0.30:  спекулятивная
        """
        if prob >= 0.85:
            return ConfidenceLabel.VERY_HIGH
        elif prob >= 0.70:
            return ConfidenceLabel.HIGH
        elif prob >= 0.50:
            return ConfidenceLabel.MODERATE
        elif prob >= 0.30:
            return ConfidenceLabel.LOW
        else:
            return ConfidenceLabel.SPECULATIVE

    def _aggregate_by_event(
        self,
        round_result: DelphiRoundResult,
    ) -> dict[str, dict[str, PredictionItem]]:
        """
        Группирует прогнозы R2 по event_thread_id.

        Returns:
            {event_thread_id: {persona_id: PredictionItem}}
        """
        result: dict[str, dict[str, PredictionItem]] = defaultdict(dict)
        for persona_id, assessment in round_result.assessments.items():
            for pred in assessment.predictions:
                result[pred.event_thread_id][persona_id.value] = pred
        return dict(result)
```

### 5.5 Схемы данных Judge

```python
# src/schemas/headline.py (фрагмент)

from pydantic import BaseModel, Field
from enum import Enum


class ConfidenceLabel(str, Enum):
    """Пользовательские метки уверенности."""
    VERY_HIGH = "очень высокая"      # >= 0.85
    HIGH = "высокая"                  # >= 0.70
    MODERATE = "умеренная"            # >= 0.50
    LOW = "низкая"                    # >= 0.30
    SPECULATIVE = "спекулятивная"     # < 0.30


class AgreementLevel(str, Enum):
    """Уровень согласия между агентами."""
    CONSENSUS = "consensus"                       # 4-5 согласны, spread < 0.15
    MAJORITY_WITH_DISSENT = "majority_dissent"    # 3 vs 2, spread 0.15-0.30
    CONTESTED = "contested"                        # 2-2-1 или хуже, spread > 0.30


class DissentingView(BaseModel):
    """Несогласная позиция одного агента."""
    agent_label: str = Field(description="Анонимная метка или роль агента")
    probability: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(description="Краткое обоснование несогласия")


class RankedPrediction(BaseModel):
    """
    Единичный ранжированный прогноз -- выход Judge, вход для генераторов.
    """
    event_thread_id: str
    prediction: str = Field(
        description="Текст прогноза (что произойдёт)"
    )
    calibrated_probability: float = Field(
        ge=0.0, le=1.0,
        description="Калиброванная вероятность после Platt scaling"
    )
    raw_probability: float = Field(
        ge=0.0, le=1.0,
        description="Исходная взвешенная медиана до калибровки"
    )
    headline_score: float = Field(
        ge=0.0,
        description="Итоговый скоринговый балл (prob * newsworthiness * (1-saturation) * relevance)"
    )
    newsworthiness: float = Field(
        ge=0.0, le=1.0,
        description="Средняя оценка новостной ценности"
    )
    confidence_label: ConfidenceLabel = Field(
        description="Пользовательская метка уверенности"
    )
    agreement_level: AgreementLevel = Field(
        description="Уровень согласия между агентами"
    )
    spread: float = Field(
        ge=0.0, le=1.0,
        description="Разброс вероятностей между агентами"
    )
    reasoning: str = Field(
        description="Объединённая цепочка рассуждений"
    )
    evidence_chain: list[dict[str, str]] = Field(
        description="Цепочка доказательств [{source, summary}]"
    )
    dissenting_views: list[DissentingView] = Field(
        default_factory=list,
        description="Несогласные позиции (пустой при консенсусе)"
    )
    is_wild_card: bool = Field(
        default=False,
        description="True если прогноз добавлен как wild card от Адвоката дьявола"
    )
    rank: int = Field(
        default=0,
        description="Позиция в итоговом ранжировании (1-based)"
    )
```

---

## 6. Система калибровки уверенности

### 6.1 Cold start (первые прогнозы)

До накопления истории верификаций система использует фиксированные значения:

| Параметр | Значение | Обоснование |
|---|---|---|
| initial_weight (Реалист) | 0.22 | Base rate reasoning исторически хорошо калиброван |
| initial_weight (Геостратег) | 0.20 | Среднее |
| initial_weight (Экономист) | 0.20 | Среднее |
| initial_weight (Медиа) | 0.18 | Ценен для формулировки, менее для вероятностей |
| initial_weight (Адвокат) | 0.20 | Контрарианство добавляет ценность ансамблю |
| extremization_a | 1.5 | LLM-ансамбли underconfident (Baron et al., 2014) |
| bias_b | 0.0 | Нет априорного смещения |

### 6.2 Brier score tracking

После каждого верифицированного прогноза (пользователь отмечает, сбылся ли) обновляется Brier score каждого агента:

```
Brier_i = mean( (forecast_i - outcome)^2 )
```

Где `outcome` = 1.0 (событие произошло) или 0.0 (не произошло).

```python
# src/agents/forecasters/calibration.py

from dataclasses import dataclass, field


@dataclass
class CalibrationRecord:
    """История калибровки одного агента."""
    persona_id: str
    total_predictions: int = 0
    brier_score: float = 0.25       # начальное значение (random baseline)
    brier_history: list[float] = field(default_factory=list)  # скользящее окно

    # Калибровочная кривая: бакеты [0.0-0.1, 0.1-0.2, ..., 0.9-1.0]
    calibration_buckets: dict[str, "CalibrationBucket"] = field(
        default_factory=dict
    )

    def update(self, forecast: float, outcome: float) -> None:
        """
        Обновляет Brier score после верификации.

        Args:
            forecast: Прогнозированная вероятность (0-1).
            outcome: Фактический исход (0.0 или 1.0).
        """
        squared_error = (forecast - outcome) ** 2
        self.brier_history.append(squared_error)

        # Скользящее среднее (последние 100 прогнозов)
        window = self.brier_history[-100:]
        self.brier_score = sum(window) / len(window)
        self.total_predictions += 1

        # Обновление калибровочного бакета
        bucket_key = f"{int(forecast * 10) / 10:.1f}"
        if bucket_key not in self.calibration_buckets:
            self.calibration_buckets[bucket_key] = CalibrationBucket()
        self.calibration_buckets[bucket_key].add(forecast, outcome)


@dataclass
class CalibrationBucket:
    """Один бакет калибровочной кривой."""
    count: int = 0
    mean_forecast: float = 0.0
    mean_outcome: float = 0.0

    def add(self, forecast: float, outcome: float) -> None:
        self.count += 1
        # Инкрементальное среднее
        self.mean_forecast += (forecast - self.mean_forecast) / self.count
        self.mean_outcome += (outcome - self.mean_outcome) / self.count
```

### 6.3 Калибровочная кривая

Калибровочная кривая строится из бакетов: для каждого диапазона предсказанных вероятностей (0.0-0.1, 0.1-0.2, ...) сравнивается средняя предсказанная вероятность с фактической частотой наступления. Идеальная калибровка -- диагональ.

Используется для:
1. Корректировки параметров Platt scaling (a, b) при накоплении > 50 верификаций
2. Инъекции в промпт персоны: «В прошлом, когда ты оценивал вероятность в 0.7-0.8, событие происходило в 55% случаев. Скорректируй свои оценки.»

### 6.4 Инъекция калибровочной истории в промпт

```python
def build_calibration_prompt_section(record: CalibrationRecord) -> str:
    """
    Генерирует секцию промпта с историей калибровки.

    Включается в системный промпт персоны при наличии >= 10 верификаций.
    """
    if record.total_predictions < 10:
        return ""

    lines = [
        "\n## Твоя история калибровки",
        f"Общий Brier score: {record.brier_score:.3f} "
        f"(идеал 0.0, случайный 0.25)",
    ]

    miscalibrated = []
    for bucket_key, bucket in sorted(record.calibration_buckets.items()):
        if bucket.count >= 3:  # достаточно данных
            diff = abs(bucket.mean_forecast - bucket.mean_outcome)
            if diff > 0.10:  # существенная расхождение
                direction = "переоцениваешь" if bucket.mean_forecast > bucket.mean_outcome else "недооцениваешь"
                miscalibrated.append(
                    f"- Диапазон {bucket_key}: ты {direction} "
                    f"(среднее предсказание {bucket.mean_forecast:.0%}, "
                    f"фактическая частота {bucket.mean_outcome:.0%}, "
                    f"n={bucket.count})"
                )

    if miscalibrated:
        lines.append("\nОбласти некалиброванности:")
        lines.extend(miscalibrated)
        lines.append("\nУчитывай эту историю при оценке вероятностей.")

    return "\n".join(lines)
```

### 6.5 Пользовательские метки уверенности

Метки отображаются в UI для нетехнических пользователей:

| Метка | Диапазон | Описание для пользователя |
|---|---|---|
| **Очень высокая** | >= 0.85 | Событие почти наверняка произойдёт. Согласие большинства экспертов. |
| **Высокая** | 0.70 - 0.84 | Событие скорее всего произойдёт. Есть сильные основания. |
| **Умеренная** | 0.50 - 0.69 | Вероятность выше среднего, но исход не предопределён. |
| **Низкая** | 0.30 - 0.49 | Возможный, но маловероятный сценарий. |
| **Спекулятивная** | < 0.30 | Маловероятно, но потенциально важно. Часто -- wild card. |

---

## 7. Обработка ошибок

### 7.1 Отказ агента

| Ситуация | Реакция | Восстановление |
|---|---|---|
| 1 из 5 агентов упал | Продолжить с 4 | Результат валиден, пометить в метаданных |
| 2 из 5 агентов упали | Продолжить с 3 | Результат валиден, но снижается доверие к ансамблю |
| 3+ из 5 агентов упали | `DelphiQuorumError` | Abort pipeline, вернуть пользователю сообщение об ошибке |
| Адвокат дьявола упал | Особый случай | Wild cards недоступны, пометить отсутствие контрарианской проверки |

### 7.2 Дегенеративный консенсус

Если после R2 все агенты дают практически одинаковые оценки (max spread < 0.05 по всем событиям), это подозрительно -- возможно, LLM-агенты конвергировали к тривиальному ответу.

**Протокол**:
1. Проверить: не являются ли все предсказания «очевидными» (e.g., "войны не будет", "рынки продолжат работать")
2. Запустить Адвоката дьявола на второй проход с усиленным промптом: "Все 5 экспертов согласились. Найди, что они все пропустили."
3. Если второй проход Адвоката даёт существенно отличающиеся сценарии -- добавить их как wild cards с пометкой "forced contrarian"

```python
async def _handle_degenerate_consensus(
    self,
    round2: DelphiRoundResult,
    trajectories: list[EventTrajectory],
    cross_impact: CrossImpactMatrix,
    ctx: PipelineContext,
) -> list[PredictionItem]:
    """
    Обработка случая, когда все агенты подозрительно единодушны.

    Запускает Адвоката дьявола с усиленным контрарианским промптом.
    """
    devils_persona = self.personas[PersonaID.DEVILS_ADVOCATE]

    # Усиленный промпт для второго прохода
    forced_prompt = (
        "ВСЕ эксперты в группе согласились. Это красный флаг. "
        "Твоя задача: найди минимум 3 события или сценария, "
        "которые все остальные пропустили. "
        "Сосредоточься на: незапланированных событиях, скрытых рисках, "
        "событиях в смежных областях."
    )

    assessment = await devils_persona.assess(
        trajectories=trajectories,
        cross_impact=cross_impact,
        mediator_feedback=None,  # чистый старт
        calibration_history=None,
        additional_system_prompt=forced_prompt,
    )

    if assessment:
        return [
            p for p in assessment.predictions
            if p.newsworthiness >= 0.5
        ]
    return []
```

### 7.3 Отсутствие чёткого прогноза

Если после полного цикла ни одно событие не набрало headline_score > 0.3 (всё слишком неуверенно или мало новостной ценности):

1. Снизить порог до 0.2
2. Если и это не помогает -- сгенерировать "Прогноз низкой активности": "На указанную дату для данного издания прогнозируется период пониженной новостной активности. Наиболее вероятные темы: [перечисление top-3 с low confidence]"
3. Пометить результат label = "low_activity_forecast"

### 7.4 Отказ LLM API

Цепочки fallback для каждой модели:

| Основная модель | Fallback 1 | Fallback 2 (крайний случай) |
|---|---|---|
| `anthropic/claude-sonnet-4` | `openai/gpt-4o` | `google/gemini-2.5-pro` |
| `openai/gpt-4o` | `anthropic/claude-sonnet-4` | `google/gemini-2.5-pro` |
| `google/gemini-2.5-pro` | `openai/gpt-4o` | `anthropic/claude-sonnet-4` |
| `yandexgpt` | `anthropic/claude-sonnet-4` | `openai/gpt-4o` |
| `meta-llama/llama-3.3-70b-instruct` | `google/gemini-2.5-pro` | `openai/gpt-4o` |

Retry policy: 1 retry с той же моделью (exponential backoff 2s), потом переключение на fallback.

---

## 8. Резюме файлов модуля

| Файл | Назначение | Ключевые классы |
|---|---|---|
| `src/agents/forecasters/personas.py` | Конфигурация 5 экспертных персон | `ExpertPersona`, `PersonaID`, `CognitiveBias`, `PERSONAS` |
| `src/agents/forecasters/delphi.py` | Оркестрация двухраундовой Дельфи | `DelphiOrchestrator`, `DelphiRoundResult`, `DelphiQuorumError` |
| `src/agents/forecasters/mediator.py` | Синтез расхождений между раундами | `Mediator` |
| `src/agents/forecasters/judge.py` | Агрегация, калибровка, ранжирование | `Judge` |
| `src/agents/forecasters/calibration.py` | Трекинг Brier score и калибровки | `CalibrationRecord`, `CalibrationBucket` |
| `src/schemas/agent.py` | Схемы данных персон и медиатора | `PersonaAssessment`, `MediatorSynthesis`, `ConsensusArea`, `DisputeArea`, `GapArea`, `CrossImpactFlag` |
| `src/schemas/headline.py` | Схемы данных Judge | `RankedPrediction`, `ConfidenceLabel`, `AgreementLevel`, `DissentingView` |
| `docs/prompts/realist.md` | Полный промпт Реалиста | -- |
| `docs/prompts/geostrateg.md` | Полный промпт Геостратега | -- |
| `docs/prompts/economist.md` | Полный промпт Экономиста | -- |
| `docs/prompts/media-expert.md` | Полный промпт Медиа-эксперта | -- |
| `docs/prompts/devils-advocate.md` | Полный промпт Адвоката дьявола | -- |
| `docs/prompts/mediator.md` | Полный промпт Медиатора | -- |
| `docs/prompts/judge.md` | Полный промпт Судьи | -- |
