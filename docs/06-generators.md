# 06 -- Generators: генерация заголовков в стиле издания

> Реализует: `src/agents/generators/framing.py`, `style_replicator.py`, `quality_gate.py`
> Стадии пайплайна: 7 (Framing Analysis), 8 (Style-Conditioned Generation), 9 (Quality Gate)
> Зависимости: `src/schemas/headline.py`, `src/schemas/agent.py`, `src/llm/router.py`, `src/llm/prompts/framing.py`, `src/llm/prompts/generation.py`, `src/llm/prompts/quality.py`

---

## Общая задача

Генераторы -- финальный каскад пайплайна. На входе: калиброванные прогнозы от Judge (что произойдёт + с какой вероятностью). На выходе: заголовки и первые абзацы, которые **выглядят как настоящие публикации конкретного издания**.

Три модуля работают последовательно:

```
RankedPrediction[] + OutletProfile
        │
        ▼
┌─────────────────────┐
│  FramingAnalyzer     │  Stage 7: "Как издание подаст это?"
│  (framing.py)        │
└──────────┬──────────┘
           │ FramingBrief[]
           ▼
┌─────────────────────┐
│  StyleReplicator     │  Stage 8: "Напиши заголовок в стиле издания"
│  (style_replicator)  │
└──────────┬──────────┘
           │ GeneratedHeadline[]
           ▼
┌─────────────────────┐
│  QualityGate         │  Stage 9: "Проверь факты, стиль, дедуп"
│  (quality_gate.py)   │
└──────────┬──────────┘
           │
           ▼
     List[FinalPrediction]
```

Ключевой принцип: **разделение аналитической и генеративной задач**. FramingAnalyzer думает стратегически (какой угол?), StyleReplicator -- тактически (какие слова?). Это позволяет использовать сильные reasoning-модели для фрейминга и более быстрые/специализированные модели для генерации текста.

---

## 1. FramingAnalyzer (`framing.py`)

### 1.1 Назначение

FramingAnalyzer отвечает на вопрос: **«Как конкретное издание подаст это событие?»**

Это не просто пересказ прогноза -- это анализ редакционной логики. Одно и то же событие (например, "ЦБ повысит ставку до 23%") для разных изданий превращается в разные новости:
- **РБК**: "ЦБ повышает ставку: что будет с ипотекой и вкладами"
- **ТАСС**: "Набиуллина: ставка повышена для обеспечения ценовой стабильности"
- **Незыгарь**: "Источники в ЦБ: решение по ставке принято под давлением из АП"
- **BBC Russian**: "Россия повышает ставку на фоне растущей инфляции и военных расходов"

FramingAnalyzer моделирует эту редакционную логику на основе OutletProfile.

### 1.2 Входные данные

- `RankedPrediction` -- прогноз от Judge (что произойдёт, вероятность, обоснование)
- `OutletProfile` -- профиль издания, включающий:
  - Редакционную линию (editorial_stance)
  - Типичные темы и разделы (sections, topic_distribution)
  - 10-20 примеров недавних заголовков (sample_headlines)
  - Тональный профиль (tone_profile: нейтральный/сенсационный/аналитический/...)
  - Типичные источники (sourcing_patterns)
  - Средняя длина заголовка (avg_headline_length)

### 1.3 Реализация

```python
# src/agents/generators/framing.py

import logging
from typing import Literal

from src.agents.base import BaseAgent
from src.schemas.headline import RankedPrediction, FramingBrief, FramingStrategy
from src.schemas.pipeline import PipelineContext
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class FramingAnalyzer(BaseAgent):
    """
    Анализирует, как конкретное издание подаст прогнозируемое событие.

    Для каждого RankedPrediction генерирует FramingBrief:
    редакционный угол, стратегия фрейминга, тон, что издание
    подчеркнёт, а что опустит.

    Модель: Claude Sonnet (через OpenRouter) -- нужны reasoning
    способности для моделирования редакционной логики.
    """

    name = "framing_analyzer"
    description = "Анализ фрейминга событий для конкретного издания"

    # Основная модель для анализа фрейминга
    MODEL_TIER = "reasoning"  # Claude Sonnet

    def __init__(self, llm_router: LLMRouter | None = None):
        self.llm = llm_router or LLMRouter()

    async def analyze(
        self,
        prediction: RankedPrediction,
        outlet_profile: "OutletProfile",
        ctx: PipelineContext,
    ) -> FramingBrief:
        """
        Анализирует фрейминг одного прогноза для одного издания.

        Args:
            prediction: Ранжированный прогноз от Judge.
            outlet_profile: Профиль целевого издания.
            ctx: Контекст пайплайна.

        Returns:
            FramingBrief -- редакционный бриф для StyleReplicator.
        """
        prompt = self._build_prompt(prediction, outlet_profile)

        response = await self.llm.call_structured(
            model_tier=self.MODEL_TIER,
            system_prompt=self._system_prompt(outlet_profile),
            user_prompt=prompt,
            response_model=FramingBrief,
            max_tokens=1024,
            temperature=0.5,
        )

        return response

    async def analyze_batch(
        self,
        predictions: list[RankedPrediction],
        outlet_profile: "OutletProfile",
        ctx: PipelineContext,
    ) -> list[FramingBrief]:
        """
        Параллельный анализ фрейминга для списка прогнозов.

        Запускает analyze() параллельно для всех прогнозов.
        При ошибке отдельного прогноза -- пропускает его с логированием.
        """
        import asyncio

        tasks = [
            self.analyze(pred, outlet_profile, ctx)
            for pred in predictions
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        briefs: list[FramingBrief] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"Framing analysis failed for prediction "
                    f"'{predictions[i].event_thread_id}': {result}"
                )
                # Fallback: минимальный brief
                briefs.append(self._fallback_brief(predictions[i], outlet_profile))
            else:
                briefs.append(result)

        return briefs

    def _system_prompt(self, outlet_profile: "OutletProfile") -> str:
        """Системный промпт для анализа фрейминга."""
        return (
            "Ты -- опытный медиа-аналитик, специализирующийся на анализе "
            "редакционной политики СМИ. Твоя задача -- предсказать, "
            f"как издание «{outlet_profile.name}» подаст конкретное событие.\n\n"
            f"Профиль издания:\n"
            f"- Редакционная линия: {outlet_profile.editorial_stance}\n"
            f"- Тональность: {outlet_profile.tone_profile}\n"
            f"- Типичные источники: {', '.join(outlet_profile.sourcing_patterns[:5])}\n"
            f"- Целевая аудитория: {outlet_profile.target_audience}\n\n"
            f"Примеры недавних заголовков:\n"
            + "\n".join(f"- {h}" for h in outlet_profile.sample_headlines[:10])
        )

    def _build_prompt(
        self,
        prediction: RankedPrediction,
        outlet_profile: "OutletProfile",
    ) -> str:
        """Промпт для анализа фрейминга конкретного события."""
        return (
            f"Событие: {prediction.prediction}\n"
            f"Вероятность: {prediction.calibrated_probability:.0%}\n"
            f"Обоснование: {prediction.reasoning}\n"
            f"Уровень согласия экспертов: {prediction.agreement_level.value}\n\n"
            f"Как издание «{outlet_profile.name}» подаст это событие?\n\n"
            f"Проанализируй:\n"
            f"1. Какую стратегию фрейминга выберет редакция? "
            f"(угроза / возможность / кризис / рутина / сенсация / аналитика)\n"
            f"2. Какой конкретный угол (angle) -- что будет в фокусе?\n"
            f"3. Что издание подчеркнёт, а что опустит или приглушит?\n"
            f"4. Какой тон заголовка? (тревожный / нейтральный / оптимистичный / ироничный / ...)\n"
            f"5. На какие источники сошлётся?\n"
            f"6. В какой раздел попадёт публикация?\n"
            f"7. Есть ли привязка к текущему новостному циклу или серии публикаций?"
        )

    def _fallback_brief(
        self,
        prediction: RankedPrediction,
        outlet_profile: "OutletProfile",
    ) -> FramingBrief:
        """Минимальный brief при ошибке LLM -- нейтральный фрейминг."""
        return FramingBrief(
            event_thread_id=prediction.event_thread_id,
            outlet_name=outlet_profile.name,
            framing_strategy=FramingStrategy.NEUTRAL_REPORT,
            angle=prediction.prediction,
            emphasis_points=[prediction.reasoning[:200]],
            omission_points=[],
            headline_tone="нейтральный",
            likely_sources=outlet_profile.sourcing_patterns[:3],
            section=outlet_profile.sections[0] if outlet_profile.sections else "новости",
            news_cycle_hook="",
            editorial_alignment_score=0.5,
        )
```

### 1.4 Схема FramingBrief

```python
# src/schemas/headline.py (дополнение)

from pydantic import BaseModel, Field
from enum import Enum


class FramingStrategy(str, Enum):
    """Стратегия фрейминга, выбранная редакцией."""
    THREAT = "threat"                   # Угроза: "это опасно для..."
    OPPORTUNITY = "opportunity"         # Возможность: "это открывает..."
    CRISIS = "crisis"                   # Кризис: "ситуация обостряется"
    ROUTINE = "routine"                 # Рутина: "регулярное событие"
    SENSATION = "sensation"             # Сенсация: "шокирующие подробности"
    ANALYTICAL = "analytical"           # Аналитика: "что это значит"
    HUMAN_INTEREST = "human_interest"   # Человеческая история
    NEUTRAL_REPORT = "neutral_report"   # Нейтральный отчёт
    CONFLICT = "conflict"               # Конфликт сторон


class FramingBrief(BaseModel):
    """
    Редакционный бриф: как конкретное издание подаст событие.

    Генерируется FramingAnalyzer, используется StyleReplicator.
    """
    event_thread_id: str = Field(
        description="ID события из RankedPrediction"
    )
    outlet_name: str = Field(
        description="Название издания"
    )
    framing_strategy: FramingStrategy = Field(
        description="Основная стратегия фрейминга"
    )
    angle: str = Field(
        description="Конкретный угол подачи: что в фокусе заголовка "
        "(1-2 предложения). Например: 'Фокус на последствиях для "
        "малого бизнеса, а не на макроэкономических показателях'"
    )
    emphasis_points: list[str] = Field(
        min_length=1, max_length=5,
        description="Что издание подчеркнёт (2-5 пунктов). "
        "Например: ['масштаб последствий', 'реакция оппозиции', "
        "'цитата пострадавших']"
    )
    omission_points: list[str] = Field(
        default_factory=list, max_length=5,
        description="Что издание приглушит или опустит (0-5 пунктов). "
        "Например: ['контекст предыдущих решений', 'альтернативные мнения']"
    )
    headline_tone: str = Field(
        description="Тон заголовка: тревожный / нейтральный / "
        "оптимистичный / ироничный / острый / дипломатичный / сенсационный"
    )
    likely_sources: list[str] = Field(
        min_length=1, max_length=5,
        description="На какие источники сошлётся издание. "
        "Например: ['пресс-служба Кремля', 'анонимные источники в МИД', "
        "'Reuters']"
    )
    section: str = Field(
        description="Раздел издания, в который попадёт публикация. "
        "Например: 'Политика', 'Экономика', 'Главное'"
    )
    news_cycle_hook: str = Field(
        default="",
        description="Привязка к текущему новостному циклу или серии. "
        "Пустая строка если привязки нет. "
        "Например: 'Серия публикаций о реформе ЖКХ (3-я неделя)'"
    )
    editorial_alignment_score: float = Field(
        ge=0.0, le=1.0,
        description="Насколько событие соответствует редакционной линии "
        "издания (0 = совсем не в профиле, 1 = идеально в профиле)"
    )
```

---

## 2. StyleReplicator (`style_replicator.py`)

### 2.1 Назначение

StyleReplicator -- генеративное ядро. Принимает **что** нужно написать (prediction + framing brief) и **как** (outlet profile с примерами) и генерирует заголовок + первый абзац, стилистически неотличимые от настоящих публикаций издания.

### 2.2 Мультиязычная стратегия

Ключевое решение: выбор модели зависит от языка целевого издания.

| Язык издания | Основная модель | Обоснование |
|---|---|---|
| Русский | YandexGPT (напрямую) | Обучен на русскоязычных медиа, лучше понимает стилистические нюансы |
| Английский | Claude Sonnet (OpenRouter) | Превосходное качество английской генерации |
| Другие языки | Claude Sonnet (OpenRouter) | Надёжная мультиязычная генерация |

### 2.3 Инъекция стилевых примеров

StyleReplicator получает конкретные примеры из OutletProfile. Формат инъекции:

```
## Стилевые примеры: {outlet_name}

### Параметры стиля
- Средняя длина заголовка: {avg_headline_length} символов
- Регистр: {headline_case} (нижний / верхний / как предложение / title case)
- Тон: {tone_profile}
- Использование кавычек: {quotes_usage}
- Использование двоеточия: {colon_usage}

### Последние заголовки этого издания (образцы для имитации):
1. {headline_1}
2. {headline_2}
...
10. {headline_10}

### Примеры первых абзацев:
1. {lede_1}
2. {lede_2}
3. {lede_3}
```

Система передаёт 10-20 заголовков и 3-5 первых абзацев как few-shot примеры. Это критически важно для захвата неявных стилистических паттернов: длина, ритм, типичные конструкции, лексика.

### 2.4 Реализация

```python
# src/agents/generators/style_replicator.py

import asyncio
import logging

from src.agents.base import BaseAgent
from src.schemas.headline import (
    RankedPrediction,
    FramingBrief,
    GeneratedHeadline,
)
from src.schemas.pipeline import PipelineContext
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)

# Сколько вариантов генерировать на один прогноз
VARIANTS_PER_PREDICTION = 3

# Ограничения на ревизию
MAX_REVISION_ATTEMPTS = 1


class StyleReplicator(BaseAgent):
    """
    Генерирует заголовки и первые абзацы в стиле целевого издания.

    Для каждого прогноза + framing brief создаёт 2-3 варианта заголовка
    с первым абзацем. Стиль определяется OutletProfile (примеры + метрики).

    Выбор модели: YandexGPT для русскоязычных изданий,
    Claude Sonnet для остальных.
    """

    name = "style_replicator"
    description = "Генерация заголовков в стиле издания"

    def __init__(self, llm_router: LLMRouter | None = None):
        self.llm = llm_router or LLMRouter()

    async def generate(
        self,
        prediction: RankedPrediction,
        framing: FramingBrief,
        outlet_profile: "OutletProfile",
        ctx: PipelineContext,
        revision_feedback: str | None = None,
    ) -> list[GeneratedHeadline]:
        """
        Генерирует варианты заголовков для одного прогноза.

        Args:
            prediction: Ранжированный прогноз.
            framing: Фрейминг-бриф от FramingAnalyzer.
            outlet_profile: Профиль издания с примерами.
            ctx: Контекст пайплайна.
            revision_feedback: Обратная связь от QualityGate при ревизии.
                              None при первой генерации.

        Returns:
            Список из 2-3 GeneratedHeadline.
        """
        model_tier = self._select_model_tier(outlet_profile.language)

        system_prompt = self._build_system_prompt(outlet_profile)
        user_prompt = self._build_user_prompt(
            prediction, framing, outlet_profile, revision_feedback
        )

        # Генерация: один вызов LLM, в ответе -- несколько вариантов
        response = await self.llm.call_structured(
            model_tier=model_tier,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=GeneratedHeadlineSet,
            max_tokens=2048,
            temperature=0.8,  # чуть выше для творческого разнообразия
        )

        # Валидация длины заголовков
        validated = self._validate_length(
            headlines=response.headlines,
            target_length=outlet_profile.avg_headline_length,
        )

        return validated

    async def generate_batch(
        self,
        predictions_with_framing: list[tuple[RankedPrediction, FramingBrief]],
        outlet_profile: "OutletProfile",
        ctx: PipelineContext,
    ) -> list[GeneratedHeadline]:
        """
        Параллельная генерация для всех прогнозов.

        Returns:
            Плоский список GeneratedHeadline (2-3 варианта на каждый прогноз).
        """
        tasks = [
            self.generate(pred, framing, outlet_profile, ctx)
            for pred, framing in predictions_with_framing
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_headlines: list[GeneratedHeadline] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"Generation failed for prediction "
                    f"'{predictions_with_framing[i][0].event_thread_id}': {result}"
                )
                # При ошибке генерации -- пропускаем прогноз
                continue
            all_headlines.extend(result)

        return all_headlines

    async def revise(
        self,
        headline: GeneratedHeadline,
        feedback: str,
        outlet_profile: "OutletProfile",
        original_prediction: RankedPrediction,
        original_framing: FramingBrief,
        ctx: PipelineContext,
    ) -> GeneratedHeadline | None:
        """
        Ревизия одного заголовка на основе обратной связи QualityGate.

        Вызывается когда style_score < 3. Максимум 1 попытка ревизии.

        Args:
            headline: Исходный заголовок, не прошедший проверку.
            feedback: Текстовая обратная связь от QualityGate.
            outlet_profile: Профиль издания.
            original_prediction: Исходный прогноз.
            original_framing: Исходный фрейминг-бриф.
            ctx: Контекст пайплайна.

        Returns:
            Исправленный GeneratedHeadline или None при повторной ошибке.
        """
        revision_feedback = (
            f"Предыдущий вариант не прошёл стилистическую проверку.\n"
            f"Исходный заголовок: {headline.headline}\n"
            f"Обратная связь: {feedback}\n"
            f"Исправь стилистические проблемы, сохранив смысл и фрейминг."
        )

        try:
            results = await self.generate(
                prediction=original_prediction,
                framing=original_framing,
                outlet_profile=outlet_profile,
                ctx=ctx,
                revision_feedback=revision_feedback,
            )
            if results:
                revised = results[0]  # берём первый вариант ревизии
                revised.is_revision = True
                revised.revision_of_id = headline.id
                return revised
        except Exception as e:
            logger.error(f"Revision failed: {e}")

        return None

    def _select_model_tier(self, language: str) -> str:
        """
        Выбирает tier модели на основе языка издания.

        Returns:
            "russian" для русского, "reasoning" для остальных.
        """
        if language.lower() in ("ru", "russian", "русский"):
            return "russian"  # YandexGPT
        return "reasoning"  # Claude Sonnet

    def _build_system_prompt(self, outlet_profile: "OutletProfile") -> str:
        """
        Строит системный промпт с полным стилевым контекстом.

        Включает: идентичность, стилевые параметры, примеры заголовков.
        """
        headlines_block = "\n".join(
            f"{i+1}. {h}" for i, h in enumerate(outlet_profile.sample_headlines[:15])
        )

        ledes_block = ""
        if outlet_profile.sample_ledes:
            ledes_block = "\n\n### Примеры первых абзацев:\n" + "\n".join(
                f"{i+1}. {l}" for i, l in enumerate(outlet_profile.sample_ledes[:5])
            )

        return (
            f"Ты -- автор заголовков и первых абзацев для издания «{outlet_profile.name}».\n"
            f"Твоя задача: написать заголовок и первый абзац, стилистически "
            f"неотличимые от настоящих публикаций этого издания.\n\n"
            f"## Параметры стиля\n"
            f"- Язык: {outlet_profile.language}\n"
            f"- Средняя длина заголовка: {outlet_profile.avg_headline_length} символов\n"
            f"- Регистр заголовков: {outlet_profile.headline_case}\n"
            f"- Тональность: {outlet_profile.tone_profile}\n"
            f"- Использование кавычек в заголовках: {outlet_profile.quotes_usage}\n"
            f"- Двоеточие в заголовках: {outlet_profile.colon_usage}\n"
            f"- Длина первого абзаца: {outlet_profile.avg_lede_length} слов\n\n"
            f"## Последние заголовки «{outlet_profile.name}» (образцы для имитации):\n"
            f"{headlines_block}"
            f"{ledes_block}\n\n"
            f"## Правила\n"
            f"1. Заголовок должен быть по длине близок к среднему ({outlet_profile.avg_headline_length} символов, допуск +/- 20%)\n"
            f"2. Тон должен соответствовать профилю издания\n"
            f"3. Лексика и конструкции -- как в примерах выше\n"
            f"4. Первый абзац: {outlet_profile.avg_lede_length} слов, содержит кто/что/где/когда\n"
            f"5. НЕ изобретай факты, которых нет в прогнозе\n"
            f"6. НЕ используй клише, которых нет в примерах\n"
            f"7. Заголовок должен быть на языке издания ({outlet_profile.language})"
        )

    def _build_user_prompt(
        self,
        prediction: RankedPrediction,
        framing: FramingBrief,
        outlet_profile: "OutletProfile",
        revision_feedback: str | None = None,
    ) -> str:
        """Промпт с конкретным прогнозом и фреймингом."""
        base = (
            f"## Событие для заголовка\n"
            f"Прогноз: {prediction.prediction}\n"
            f"Вероятность: {prediction.calibrated_probability:.0%}\n"
            f"Новостная ценность: {prediction.newsworthiness:.0%}\n\n"
            f"## Фрейминг\n"
            f"Стратегия: {framing.framing_strategy.value}\n"
            f"Угол: {framing.angle}\n"
            f"Подчеркнуть: {', '.join(framing.emphasis_points)}\n"
            f"Опустить: {', '.join(framing.omission_points) or 'ничего'}\n"
            f"Тон: {framing.headline_tone}\n"
            f"Источники: {', '.join(framing.likely_sources)}\n"
            f"Раздел: {framing.section}\n"
        )

        if framing.news_cycle_hook:
            base += f"Привязка к циклу: {framing.news_cycle_hook}\n"

        base += (
            f"\nСгенерируй {VARIANTS_PER_PREDICTION} варианта заголовка + первый абзац для каждого.\n"
            f"Варианты должны отличаться углом подачи или акцентом, но соответствовать одному фреймингу."
        )

        if revision_feedback:
            base += f"\n\n## Ревизия\n{revision_feedback}"

        return base

    def _validate_length(
        self,
        headlines: list[GeneratedHeadline],
        target_length: int,
    ) -> list[GeneratedHeadline]:
        """
        Проверяет длину заголовков. Отмечает отклонения.

        Не отклоняет заголовки по длине -- это делает QualityGate.
        Только добавляет метку length_deviation для дальнейшей проверки.
        """
        tolerance = 0.20  # +/- 20%
        min_len = int(target_length * (1 - tolerance))
        max_len = int(target_length * (1 + tolerance))

        for headline in headlines:
            actual_len = len(headline.headline)
            if actual_len < min_len or actual_len > max_len:
                headline.length_deviation = (actual_len - target_length) / target_length
            else:
                headline.length_deviation = 0.0

        return headlines


# --- Вспомогательная модель для парсинга LLM-ответа ---

from pydantic import BaseModel, Field


class GeneratedHeadlineSet(BaseModel):
    """Множество вариантов заголовков от одного LLM-вызова."""
    headlines: list["GeneratedHeadline"] = Field(
        min_length=2, max_length=4,
        description="2-3 варианта заголовка + первый абзац"
    )
```

### 2.5 Схема GeneratedHeadline

```python
# src/schemas/headline.py (дополнение)

import uuid

from pydantic import BaseModel, Field


class GeneratedHeadline(BaseModel):
    """
    Один вариант заголовка + первый абзац.

    Генерируется StyleReplicator, проверяется QualityGate.
    """
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Уникальный ID варианта"
    )
    event_thread_id: str = Field(
        description="ID события из RankedPrediction"
    )
    variant_number: int = Field(
        ge=1, le=4,
        description="Номер варианта (1-3)"
    )
    headline: str = Field(
        description="Текст заголовка на языке издания"
    )
    first_paragraph: str = Field(
        description="Первый абзац (лид) на языке издания"
    )
    headline_language: str = Field(
        description="Язык заголовка (ru / en / ...)"
    )
    length_deviation: float = Field(
        default=0.0,
        description="Отклонение длины от среднего издания "
        "(0.0 = в норме, >0 = длиннее, <0 = короче)"
    )

    # Метаданные ревизии
    is_revision: bool = Field(
        default=False,
        description="True если заголовок был исправлен после QualityGate"
    )
    revision_of_id: str | None = Field(
        default=None,
        description="ID исходного заголовка, если это ревизия"
    )
```

---

## 3. QualityGate (`quality_gate.py`)

### 3.1 Назначение

QualityGate -- финальный фильтр. Три независимые проверки для каждого GeneratedHeadline, затем решение: PASS / REJECT / REVISE / DEPRIORITIZE.

### 3.2 Три проверки

#### 3.2.1 Проверка фактической правдоподобности (Factual Plausibility)

**Модель**: Claude Sonnet (через OpenRouter)
**Задача**: Найти противоречия с известными фактами, логические несоответствия, анахронизмы.

Проверяет:
- Противоречит ли прогноз общеизвестным фактам? (e.g., "Путин встретится с Зеленским в Москве" -- если нет дипломатических отношений)
- Есть ли логические несоответствия в первом абзаце?
- Корректны ли упомянутые даты, должности, названия?
- Не является ли событие физически / логически невозможным?
- Не устарела ли предпосылка? (e.g., "Министр X заявил" -- если X уже не министр)

**Не** проверяет: произойдёт ли событие (это задача Judge). Проверяет только внутреннюю непротиворечивость и соответствие известным фактам.

**Оценка**: 1-5
- 5: Полностью правдоподобно, фактов-противоречий не найдено
- 4: Мелкие неточности, не влияющие на смысл
- 3: Есть спорные утверждения, но принципиально не ошибочные
- 2: Содержит фактическую ошибку или серьёзное логическое противоречие
- 1: Явно абсурдный или невозможный сценарий

#### 3.2.2 Проверка стилистической аутентичности (Style Authenticity)

**Модель**: YandexGPT (для русскоязычных изданий), Claude Sonnet (для остальных)
**Задача**: Оценить, насколько заголовок и первый абзац стилистически соответствуют целевому изданию.

Проверяет:
- Лексика: типичны ли используемые слова для этого издания?
- Конструкции: типичны ли синтаксические конструкции?
- Длина: соответствует ли длина заголовка средней длине издания?
- Тон: соответствует ли тон профилю издания?
- «Smell test»: похоже ли это на реальную публикацию этого издания?

YandexGPT выбран для русскоязычных изданий, потому что он обучен на большом объёме русскоязычных медиа и лучше чувствует стилистические нюансы (канцелярит, публицистические штампы, разговорный стиль Telegram-каналов и т.д.).

**Оценка**: 1-5
- 5: Неотличимо от настоящей публикации
- 4: Стиль в целом верный, мелкие шероховатости
- 3: Узнаваемый стиль, но с заметными отклонениями
- 2: Стиль не соответствует изданию (слишком формальный / неформальный / чуждая лексика)
- 1: Совершенно не похоже на это издание

#### 3.2.3 Дедупликация (Deduplication)

**Модель**: Не требуется (эмбеддинги + cosine similarity)
**Задача**: Проверить, что прогноз не дублирует:
- Другой прогноз в текущем списке (внутренняя дедупликация)
- Реальный заголовок, уже опубликованный изданием (внешняя дедупликация)

**Метод**:
1. Вычислить эмбеддинги всех заголовков (OpenAI text-embedding-3-small через OpenRouter)
2. Cosine similarity > 0.85 с другим прогнозом = внутренний дубликат
3. Cosine similarity > 0.80 с реальным заголовком из OutletProfile.recent_headlines = внешний дубликат

### 3.3 Логика гейта

```
                    ┌────────────────┐
                    │ GeneratedHead- │
                    │ line           │
                    └───────┬────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ Factual  │  │  Style   │  │  Dedup   │
        │ Check    │  │  Check   │  │  Check   │
        │ (Sonnet) │  │ (Yandex) │  │ (embed)  │
        └────┬─────┘  └────┬─────┘  └────┬─────┘
             │             │             │
             ▼             ▼             ▼
        score: 1-5    score: 1-5    is_dup: bool
              └─────────────┼─────────────┘
                            ▼
                    ┌───────────────┐
                    │ Gate Decision │
                    └───────┬───────┘
                            │
          ┌─────────┬───────┼───────┬──────────┐
          ▼         ▼       ▼       ▼          ▼
        PASS     REVISE   REJECT  DEPRIO-   MERGE
                                  RITIZE
```

**Правила решения**:

| factual_score | style_score | is_duplicate | Решение |
|---|---|---|---|
| >= 3 | >= 3 | false | **PASS** -- заголовок принят |
| < 3 | любой | любой | **REJECT** -- прогноз фактически некорректен, не исправлять (проблема в прогнозе, а не в генерации) |
| >= 3 | < 3 | false | **REVISE** -- отправить обратно в StyleReplicator с обратной связью (1 попытка) |
| >= 3 | >= 3 | true (внутренний) | **MERGE** -- объединить с более сильным вариантом |
| >= 3 | >= 3 | true (внешний) | **DEPRIORITIZE** -- понизить приоритет (событие уже освещено) |

Важная деталь: при `factual_score < 3` заголовок **отклоняется без ревизии**. Стилистику можно исправить, но если прогноз содержит фактическую ошибку -- проблема на уровне прогнозирования, а не генерации, и исправление заголовка не поможет.

### 3.4 Реализация

```python
# src/agents/generators/quality_gate.py

import asyncio
import logging
from enum import Enum

from src.agents.base import BaseAgent
from src.agents.generators.style_replicator import StyleReplicator
from src.schemas.headline import (
    RankedPrediction,
    FramingBrief,
    GeneratedHeadline,
    FinalPrediction,
    QualityScore,
    GateDecision,
)
from src.schemas.pipeline import PipelineContext
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)

# Пороги
FACTUAL_MIN_SCORE = 3
STYLE_MIN_SCORE = 3
INTERNAL_DEDUP_THRESHOLD = 0.85  # cosine similarity
EXTERNAL_DEDUP_THRESHOLD = 0.80


class QualityGate(BaseAgent):
    """
    Финальный фильтр качества: фактическая проверка, стилистическая
    проверка, дедупликация.

    Для каждого GeneratedHeadline выносит решение:
    PASS / REJECT / REVISE / DEPRIORITIZE / MERGE.

    При REVISE -- запускает StyleReplicator повторно (максимум 1 раз).
    """

    name = "quality_gate"
    description = "Проверка фактов, стиля и дедупликация"

    def __init__(
        self,
        llm_router: LLMRouter | None = None,
        style_replicator: StyleReplicator | None = None,
    ):
        self.llm = llm_router or LLMRouter()
        self.style_replicator = style_replicator or StyleReplicator(llm_router)

    async def evaluate(
        self,
        headlines: list[GeneratedHeadline],
        predictions: list[RankedPrediction],
        framings: list[FramingBrief],
        outlet_profile: "OutletProfile",
        ctx: PipelineContext,
    ) -> list[FinalPrediction]:
        """
        Полная проверка качества всех заголовков.

        Args:
            headlines: Все GeneratedHeadline от StyleReplicator.
            predictions: Исходные RankedPrediction (для контекста).
            framings: FramingBrief (для ревизии при необходимости).
            outlet_profile: Профиль издания.
            ctx: Контекст пайплайна.

        Returns:
            Отфильтрованный и ранжированный список FinalPrediction.
        """
        # Построить индексы для быстрого доступа
        pred_index = {p.event_thread_id: p for p in predictions}
        framing_index = {f.event_thread_id: f for f in framings}

        # 1. Параллельные проверки для всех заголовков
        scored_headlines = await self._score_all(
            headlines=headlines,
            predictions=predictions,
            outlet_profile=outlet_profile,
        )

        # 2. Дедупликация (требует все заголовки одновременно)
        scored_headlines = await self._deduplicate(
            scored_headlines=scored_headlines,
            outlet_profile=outlet_profile,
        )

        # 3. Применение решений
        passed: list[GeneratedHeadline] = []
        to_revise: list[tuple[GeneratedHeadline, QualityScore]] = []
        rejected: list[str] = []
        deprioritized: list[GeneratedHeadline] = []

        for headline, score in scored_headlines:
            decision = self._make_decision(score)

            if decision == GateDecision.PASS:
                passed.append(headline)
            elif decision == GateDecision.REVISE:
                to_revise.append((headline, score))
            elif decision == GateDecision.REJECT:
                rejected.append(headline.event_thread_id)
                logger.info(
                    f"REJECTED '{headline.headline[:50]}...': "
                    f"factual={score.factual_score}"
                )
            elif decision == GateDecision.DEPRIORITIZE:
                deprioritized.append(headline)
            elif decision == GateDecision.MERGE:
                # При merge -- не добавляем дубликат, уже есть более сильный
                logger.info(f"MERGED: '{headline.headline[:50]}...'")

        # 4. Ревизия (1 попытка для каждого)
        if to_revise:
            await ctx.emit_progress(
                "quality_revision",
                detail=f"Ревизия {len(to_revise)} заголовков..."
            )
            revised = await self._revise_batch(
                to_revise=to_revise,
                pred_index=pred_index,
                framing_index=framing_index,
                outlet_profile=outlet_profile,
                ctx=ctx,
            )
            passed.extend(revised)

        # 5. Добавляем deprioritized в конец
        passed.extend(deprioritized)

        # 6. Формируем FinalPrediction
        return self._build_final_predictions(
            passed_headlines=passed,
            pred_index=pred_index,
            framing_index=framing_index,
        )

    async def _score_all(
        self,
        headlines: list[GeneratedHeadline],
        predictions: list[RankedPrediction],
        outlet_profile: "OutletProfile",
    ) -> list[tuple[GeneratedHeadline, QualityScore]]:
        """
        Параллельная оценка всех заголовков: factual + style.
        """
        pred_index = {p.event_thread_id: p for p in predictions}

        async def score_one(headline: GeneratedHeadline) -> tuple[GeneratedHeadline, QualityScore]:
            prediction = pred_index.get(headline.event_thread_id)

            # Параллельно: factual + style
            factual_task = self._check_factual(headline, prediction)
            style_task = self._check_style(headline, outlet_profile)
            factual_result, style_result = await asyncio.gather(
                factual_task, style_task
            )

            score = QualityScore(
                headline_id=headline.id,
                factual_score=factual_result.score,
                factual_feedback=factual_result.feedback,
                style_score=style_result.score,
                style_feedback=style_result.feedback,
                is_internal_duplicate=False,  # заполняется в _deduplicate
                is_external_duplicate=False,
                duplicate_of_id=None,
            )
            return headline, score

        tasks = [score_one(h) for h in headlines]
        return await asyncio.gather(*tasks)

    async def _check_factual(
        self,
        headline: GeneratedHeadline,
        prediction: RankedPrediction | None,
    ) -> "CheckResult":
        """
        Проверка фактической правдоподобности (Claude Sonnet).

        Returns:
            CheckResult с score (1-5) и текстовой обратной связью.
        """
        context = ""
        if prediction:
            context = (
                f"Прогноз основан на: {prediction.reasoning}\n"
                f"Уровень уверенности: {prediction.calibrated_probability:.0%}\n"
                f"Согласие экспертов: {prediction.agreement_level.value}\n"
            )

        prompt = (
            f"Оцени фактическую правдоподобность этого заголовка и первого абзаца.\n\n"
            f"Заголовок: {headline.headline}\n"
            f"Первый абзац: {headline.first_paragraph}\n\n"
            f"Контекст прогноза:\n{context}\n\n"
            f"Проверь:\n"
            f"1. Нет ли противоречий с общеизвестными фактами?\n"
            f"2. Корректны ли должности, названия, даты?\n"
            f"3. Логически непротиворечив ли сценарий?\n"
            f"4. Не является ли событие физически невозможным?\n\n"
            f"Оценка (1-5, где 5 = полностью правдоподобно):"
        )

        response = await self.llm.call_structured(
            model_tier="reasoning",  # Claude Sonnet
            system_prompt=(
                "Ты -- факт-чекер. Оцени фактическую правдоподобность "
                "прогнозного заголовка. НЕ оценивай, произойдёт ли событие -- "
                "только внутреннюю непротиворечивость и соответствие известным фактам."
            ),
            user_prompt=prompt,
            response_model=CheckResult,
            max_tokens=512,
            temperature=0.2,
        )

        return response

    async def _check_style(
        self,
        headline: GeneratedHeadline,
        outlet_profile: "OutletProfile",
    ) -> "CheckResult":
        """
        Проверка стилистической аутентичности.

        Модель: YandexGPT для русскоязычных изданий, Claude Sonnet для остальных.
        """
        model_tier = (
            "russian" if headline.headline_language in ("ru", "russian")
            else "reasoning"
        )

        examples = "\n".join(
            f"- {h}" for h in outlet_profile.sample_headlines[:10]
        )

        prompt = (
            f"Оцени стилистическое соответствие заголовка изданию «{outlet_profile.name}».\n\n"
            f"Проверяемый заголовок: {headline.headline}\n"
            f"Проверяемый первый абзац: {headline.first_paragraph}\n\n"
            f"Примеры настоящих заголовков «{outlet_profile.name}»:\n{examples}\n\n"
            f"Параметры стиля издания:\n"
            f"- Средняя длина заголовка: {outlet_profile.avg_headline_length} символов\n"
            f"- Тон: {outlet_profile.tone_profile}\n"
            f"- Регистр: {outlet_profile.headline_case}\n\n"
            f"Проверь:\n"
            f"1. Типична ли лексика для этого издания?\n"
            f"2. Соответствуют ли синтаксические конструкции?\n"
            f"3. Подходит ли длина?\n"
            f"4. Верный ли тон?\n"
            f"5. Похоже ли это на реальную публикацию этого издания (smell test)?\n\n"
            f"Оценка (1-5, где 5 = неотличимо от настоящей публикации):"
        )

        response = await self.llm.call_structured(
            model_tier=model_tier,
            system_prompt=(
                "Ты -- редактор с 15-летним стажем. "
                "Оцени, насколько заголовок и первый абзац соответствуют "
                "стилю конкретного издания."
            ),
            user_prompt=prompt,
            response_model=CheckResult,
            max_tokens=512,
            temperature=0.2,
        )

        return response

    async def _deduplicate(
        self,
        scored_headlines: list[tuple[GeneratedHeadline, QualityScore]],
        outlet_profile: "OutletProfile",
    ) -> list[tuple[GeneratedHeadline, QualityScore]]:
        """
        Дедупликация: внутренняя (между прогнозами) и внешняя
        (против реальных заголовков).

        Использует эмбеддинги + cosine similarity.
        """
        if not scored_headlines:
            return scored_headlines

        # Собираем тексты для эмбеддингов
        texts = [h.headline for h, _ in scored_headlines]
        reference_texts = outlet_profile.recent_headlines or []

        # Получаем эмбеддинги
        all_texts = texts + reference_texts
        embeddings = await self._get_embeddings(all_texts)

        headline_embeddings = embeddings[:len(texts)]
        reference_embeddings = embeddings[len(texts):]

        # Внутренняя дедупликация
        for i in range(len(scored_headlines)):
            for j in range(i + 1, len(scored_headlines)):
                sim = self._cosine_similarity(
                    headline_embeddings[i], headline_embeddings[j]
                )
                if sim > INTERNAL_DEDUP_THRESHOLD:
                    # Помечаем более слабый как дубликат
                    h_i, s_i = scored_headlines[i]
                    h_j, s_j = scored_headlines[j]

                    # Слабее = ниже средний score
                    avg_i = (s_i.factual_score + s_i.style_score) / 2
                    avg_j = (s_j.factual_score + s_j.style_score) / 2

                    if avg_i <= avg_j:
                        s_i.is_internal_duplicate = True
                        s_i.duplicate_of_id = h_j.id
                    else:
                        s_j.is_internal_duplicate = True
                        s_j.duplicate_of_id = h_i.id

        # Внешняя дедупликация
        if reference_embeddings:
            for i in range(len(scored_headlines)):
                for ref_emb in reference_embeddings:
                    sim = self._cosine_similarity(
                        headline_embeddings[i], ref_emb
                    )
                    if sim > EXTERNAL_DEDUP_THRESHOLD:
                        scored_headlines[i][1].is_external_duplicate = True
                        break

        return scored_headlines

    async def _get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Получает эмбеддинги текстов через LLM router.

        Модель: text-embedding-3-small (через OpenRouter).
        """
        return await self.llm.get_embeddings(
            texts=texts,
            model="openai/text-embedding-3-small",
        )

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Cosine similarity между двумя векторами."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _make_decision(self, score: QualityScore) -> GateDecision:
        """
        Принимает решение по заголовку на основе оценок.

        Приоритет проверок:
        1. Factual < 3 → REJECT (не исправляется)
        2. Duplicate → MERGE (внутренний) или DEPRIORITIZE (внешний)
        3. Style < 3 → REVISE (1 попытка)
        4. Все проверки пройдены → PASS
        """
        # 1. Фактическая проверка (приоритет)
        if score.factual_score < FACTUAL_MIN_SCORE:
            return GateDecision.REJECT

        # 2. Дедупликация
        if score.is_internal_duplicate:
            return GateDecision.MERGE
        if score.is_external_duplicate:
            return GateDecision.DEPRIORITIZE

        # 3. Стилистическая проверка
        if score.style_score < STYLE_MIN_SCORE:
            return GateDecision.REVISE

        # 4. Всё в порядке
        return GateDecision.PASS

    async def _revise_batch(
        self,
        to_revise: list[tuple[GeneratedHeadline, QualityScore]],
        pred_index: dict[str, RankedPrediction],
        framing_index: dict[str, FramingBrief],
        outlet_profile: "OutletProfile",
        ctx: PipelineContext,
    ) -> list[GeneratedHeadline]:
        """
        Ревизия заголовков, не прошедших стилистическую проверку.

        Максимум 1 попытка ревизии на заголовок.
        """
        revised: list[GeneratedHeadline] = []

        for headline, score in to_revise:
            prediction = pred_index.get(headline.event_thread_id)
            framing = framing_index.get(headline.event_thread_id)

            if not prediction or not framing:
                logger.warning(
                    f"Cannot revise '{headline.headline[:50]}...': "
                    f"missing prediction or framing"
                )
                continue

            result = await self.style_replicator.revise(
                headline=headline,
                feedback=score.style_feedback,
                outlet_profile=outlet_profile,
                original_prediction=prediction,
                original_framing=framing,
                ctx=ctx,
            )

            if result:
                # Перепроверяем ревизию (только стиль, factual уже прошёл)
                style_check = await self._check_style(result, outlet_profile)
                if style_check.score >= STYLE_MIN_SCORE:
                    revised.append(result)
                else:
                    logger.info(
                        f"Revision still failed style check: "
                        f"'{result.headline[:50]}...' score={style_check.score}"
                    )

        return revised

    def _build_final_predictions(
        self,
        passed_headlines: list[GeneratedHeadline],
        pred_index: dict[str, RankedPrediction],
        framing_index: dict[str, FramingBrief],
    ) -> list[FinalPrediction]:
        """
        Собирает FinalPrediction из прошедших проверку заголовков.

        Группирует варианты по event_thread_id, выбирает лучший
        вариант как primary, остальные -- alternatives.
        """
        from collections import defaultdict

        # Группировка по событию
        by_event: dict[str, list[GeneratedHeadline]] = defaultdict(list)
        for h in passed_headlines:
            by_event[h.event_thread_id].append(h)

        final: list[FinalPrediction] = []

        for event_id, variants in by_event.items():
            prediction = pred_index.get(event_id)
            framing = framing_index.get(event_id)

            if not prediction:
                continue

            # Primary = первый вариант (самый высокий приоритет)
            primary = variants[0]
            alternatives = variants[1:3]  # максимум 2 альтернативы

            final.append(FinalPrediction(
                rank=prediction.rank,
                event_thread_id=event_id,
                headline=primary.headline,
                first_paragraph=primary.first_paragraph,
                alternative_headlines=[h.headline for h in alternatives],
                confidence=prediction.calibrated_probability,
                confidence_label=prediction.confidence_label,
                category=framing.section if framing else "новости",
                reasoning=prediction.reasoning,
                evidence_chain=prediction.evidence_chain,
                agent_agreement=prediction.agreement_level,
                dissenting_views=prediction.dissenting_views,
                is_wild_card=prediction.is_wild_card,
                framing_strategy=(
                    framing.framing_strategy.value if framing else "neutral_report"
                ),
                headline_language=primary.headline_language,
            ))

        # Сортировка по rank
        final.sort(key=lambda p: p.rank)
        return final
```

### 3.5 Вспомогательные схемы

```python
# src/schemas/headline.py (дополнение)

from pydantic import BaseModel, Field
from enum import Enum


class GateDecision(str, Enum):
    """Решение QualityGate по заголовку."""
    PASS = "pass"                   # Принят
    REJECT = "reject"               # Отклонён (фактическая ошибка)
    REVISE = "revise"               # На ревизию (стилистические проблемы)
    DEPRIORITIZE = "deprioritize"   # Понижен приоритет (внешний дубликат)
    MERGE = "merge"                 # Объединён с другим (внутренний дубликат)


class CheckResult(BaseModel):
    """Результат одной проверки (factual или style)."""
    score: int = Field(
        ge=1, le=5,
        description="Оценка 1-5"
    )
    feedback: str = Field(
        description="Текстовая обратная связь: что не так и как исправить"
    )


class QualityScore(BaseModel):
    """Полная оценка качества одного заголовка."""
    headline_id: str = Field(description="ID GeneratedHeadline")

    # Фактическая проверка
    factual_score: int = Field(
        ge=1, le=5,
        description="Оценка фактической правдоподобности (1-5)"
    )
    factual_feedback: str = Field(
        description="Обратная связь от фактчекера"
    )

    # Стилистическая проверка
    style_score: int = Field(
        ge=1, le=5,
        description="Оценка стилистической аутентичности (1-5)"
    )
    style_feedback: str = Field(
        description="Обратная связь от стилистического ревьюера"
    )

    # Дедупликация
    is_internal_duplicate: bool = Field(
        default=False,
        description="Дубликат другого прогноза в этом же списке"
    )
    is_external_duplicate: bool = Field(
        default=False,
        description="Дубликат реального уже опубликованного заголовка"
    )
    duplicate_of_id: str | None = Field(
        default=None,
        description="ID заголовка-оригинала (при внутренней дедупликации)"
    )


class FinalPrediction(BaseModel):
    """
    Финальный прогноз -- то, что видит пользователь.

    Прошёл все проверки QualityGate. Содержит заголовок, абзац,
    уверенность, обоснование, несогласные мнения.
    """
    rank: int = Field(ge=1, description="Позиция в ранжировании")
    event_thread_id: str
    headline: str = Field(
        description="Основной заголовок на языке издания"
    )
    first_paragraph: str = Field(
        description="Первый абзац (лид) на языке издания"
    )
    alternative_headlines: list[str] = Field(
        default_factory=list, max_length=3,
        description="Альтернативные варианты заголовка (0-2 штуки)"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Калиброванная вероятность"
    )
    confidence_label: "ConfidenceLabel" = Field(
        description="Пользовательская метка уверенности"
    )
    category: str = Field(
        description="Раздел издания: 'Политика', 'Экономика', 'Общество'..."
    )
    reasoning: str = Field(
        description="Цепочка рассуждений (для блока 'Почему мы так считаем')"
    )
    evidence_chain: list[dict[str, str]] = Field(
        description="Цепочка доказательств [{source, summary}]"
    )
    agent_agreement: "AgreementLevel" = Field(
        description="Уровень согласия экспертов"
    )
    dissenting_views: list["DissentingView"] = Field(
        default_factory=list,
        description="Несогласные мнения (для блока 'Альтернативный взгляд')"
    )
    is_wild_card: bool = Field(
        default=False,
        description="True = прогноз от Адвоката дьявола (wild card)"
    )
    framing_strategy: str = Field(
        description="Стратегия фрейминга, использованная при генерации"
    )
    headline_language: str = Field(
        description="Язык заголовка"
    )
```

---

## 4. Сводка всех Pydantic-схем модуля

| Схема | Файл | Назначение |
|---|---|---|
| `FramingStrategy` | `src/schemas/headline.py` | Enum стратегий фрейминга |
| `FramingBrief` | `src/schemas/headline.py` | Редакционный бриф от FramingAnalyzer |
| `GeneratedHeadline` | `src/schemas/headline.py` | Один вариант заголовка + лид |
| `GateDecision` | `src/schemas/headline.py` | Enum решений QualityGate |
| `CheckResult` | `src/schemas/headline.py` | Результат одной проверки (1-5 + feedback) |
| `QualityScore` | `src/schemas/headline.py` | Полная оценка качества заголовка |
| `FinalPrediction` | `src/schemas/headline.py` | Финальный прогноз для пользователя |

---

## 5. Имплементационные заметки

### 5.1 Мультиязычная генерация

**Проблема**: Одно и то же издание может быть на русском (ТАСС), английском (BBC), или другом языке. Заголовок должен быть на языке издания.

**Решение**:

1. `OutletProfile.language` определяет язык генерации
2. `StyleReplicator._select_model_tier()` выбирает модель:
   - `"russian"` -> YandexGPT (лучше для русского стиля)
   - `"reasoning"` -> Claude Sonnet (для английского и других)
3. Все промпты для StyleReplicator и style-проверки QualityGate содержат инструкцию: "Заголовок должен быть на языке издания ({language})"
4. Примеры заголовков в OutletProfile всегда на языке издания -- LLM копирует язык примеров

**Важно**: FramingAnalyzer всегда работает на Claude Sonnet (reasoning на любом языке), а StyleReplicator адаптируется к языку целевого издания.

### 5.2 Инъекция стилевых примеров

**Формат**: few-shot в системном промпте (см. `_build_system_prompt` в StyleReplicator).

**Количество**: 10-15 заголовков + 3-5 первых абзацев. Больше не нужно -- увеличивает стоимость без значимого улучшения качества.

**Отбор примеров**: OutletHistorian (Stage 1) собирает последние 30 дней публикаций. Из них выбираются:
- 5 типичных заголовков (медианная длина, типичный тон)
- 5 заголовков по тематике, близкой к текущему прогнозу (по эмбеддинг-сходству)
- 3-5 первых абзацев из тех же публикаций

### 5.3 Цикл ревизии

```
StyleReplicator.generate()
        │
        ▼
QualityGate._check_style()
        │
        ├── score >= 3 → PASS
        │
        └── score < 3 → StyleReplicator.revise()
                                │
                                ▼
                         QualityGate._check_style()
                                │
                                ├── score >= 3 → PASS
                                │
                                └── score < 3 → DROP
                                     (заголовок не выдается)
```

Максимум **1 ревизия**. Обоснование:
- Каждая ревизия -- дополнительный LLM-вызов (стоимость)
- Если после 1 ревизии стиль всё ещё не тот -- проблема глубже (плохой OutletProfile или неподходящий прогноз)
- Бесконечные ревизии могут привести к деградации контента (over-fitting к проверке)

При ревизии StyleReplicator получает:
- Исходный заголовок (что было)
- Обратную связь от QualityGate (что не так)
- Те же framing brief и outlet profile (контекст)

### 5.4 Обработка ошибок в генераторах

| Ситуация | Реакция |
|---|---|
| FramingAnalyzer LLM timeout | Fallback brief (нейтральный фрейм) |
| StyleReplicator LLM timeout | Пропуск прогноза (не генерируем для него) |
| QualityGate LLM timeout | Пропуск проверки, score = 3 (пограничный pass) |
| Embedding API недоступен | Дедупликация отключается, проходят все |
| Все заголовки REJECT | Вернуть предупреждение + top-3 по headline_score без заголовков (только predictions) |

### 5.5 Стоимость одного прогноза (Stage 7-9)

| Компонент | Вызовов | Модель | ~Стоимость |
|---|---|---|---|
| FramingAnalyzer | ~7 (top-7 + wild cards) | Claude Sonnet | $2.00 |
| StyleReplicator | ~27 (9 predictions * 3 variants) | YandexGPT / Sonnet | $1.50 |
| QualityGate: factual | ~27 | Claude Sonnet | $1.00 |
| QualityGate: style | ~27 | YandexGPT / Sonnet | $0.80 |
| QualityGate: embeddings | ~1 batch | text-embedding-3-small | $0.01 |
| Ревизии (если нужны) | ~3-5 | YandexGPT / Sonnet | $0.20 |
| **Итого Stage 7-9** | **~90** | | **~$5.50** |

---

## 6. Резюме файлов модуля

| Файл | Назначение | Ключевые классы |
|---|---|---|
| `src/agents/generators/framing.py` | Анализ фрейминга для издания | `FramingAnalyzer` |
| `src/agents/generators/style_replicator.py` | Генерация заголовков в стиле издания | `StyleReplicator`, `GeneratedHeadlineSet` |
| `src/agents/generators/quality_gate.py` | Тройная проверка качества | `QualityGate` |
| `src/schemas/headline.py` | Все Pydantic-схемы модуля | `FramingBrief`, `GeneratedHeadline`, `QualityScore`, `FinalPrediction`, `GateDecision`, `CheckResult`, `FramingStrategy`, `ConfidenceLabel`, `AgreementLevel`, `DissentingView` |
| `src/llm/prompts/framing.py` | Шаблоны промптов для FramingAnalyzer | -- |
| `src/llm/prompts/generation.py` | Шаблоны промптов для StyleReplicator | -- |
| `src/llm/prompts/quality.py` | Шаблоны промптов для QualityGate | -- |
