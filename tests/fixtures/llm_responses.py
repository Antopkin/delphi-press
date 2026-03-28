"""JSON fixture factories for every LLM task in the Delphi pipeline.

Each factory returns a JSON string that an agent can parse into its
expected Pydantic output schema.  Two shared thread IDs are used
across all fixtures for data coherence.

Spec references (for field-name verification):
    - ``src/schemas/llm.py`` -- LLMResponse
    - ``src/schemas/agent.py`` -- PersonaAssessment, MediatorSynthesis
    - ``src/schemas/headline.py`` -- FramingBrief, GeneratedHeadline, CheckResult, RankedPrediction
    - ``src/schemas/events.py`` -- HeadlineStyle, WritingStyle, EditorialPosition
    - ``src/llm/prompts/collectors/classify.py`` -- ClassificationBatch
    - ``src/llm/prompts/collectors/events.py`` -- ExtractedEventsBatch, AssessedEventsBatch
    - ``src/llm/prompts/analysts/clustering.py`` -- ClusterLabelBatch
    - ``src/llm/prompts/analysts/trajectory.py`` -- TrajectoryBatch
    - ``src/llm/prompts/analysts/cross_impact.py`` -- CrossImpactOutput
    - ``src/llm/prompts/analysts/geopolitical.py`` -- GeopoliticalBatch
    - ``src/llm/prompts/analysts/economic.py`` -- EconomicBatch
    - ``src/llm/prompts/analysts/media.py`` -- MediaBatch
    - ``src/llm/prompts/forecasters/judge.py`` -- JudgeResult
    - ``src/llm/prompts/generators/style.py`` -- GeneratedHeadlineSet
"""

from __future__ import annotations

import json
from typing import Any

# =====================================================================
# Shared thread IDs -- used across all fixtures for coherence
# =====================================================================

THREAD_ID_1 = "thread_abc12345"
THREAD_ID_2 = "thread_def67890"
THREAD_IDS = [THREAD_ID_1, THREAD_ID_2]

# =====================================================================
# 1. news_scout_search -- ClassificationBatch
# =====================================================================


def news_scout_search() -> str:
    """Return ClassificationBatch with 10 classified signals."""
    items = [
        {
            "index": i,
            "categories": [
                [
                    "politics",
                    "diplomacy",
                    "economy",
                    "military",
                    "technology",
                    "politics",
                    "economy",
                    "diplomacy",
                    "politics",
                    "economy",
                ][i]
            ],
            "entities": [
                ["Russia", "Ukraine"],
                ["EU", "European Commission"],
                ["China", "USA"],
                ["NATO", "Turkey"],
                ["OpenAI", "Google"],
                ["Macron", "France"],
                ["ECB", "Lagarde"],
                ["India", "Modi"],
                ["UN", "Guterres"],
                ["Saudi Arabia", "OPEC"],
            ][i],
        }
        for i in range(10)
    ]
    return json.dumps({"items": items})


# =====================================================================
# 2. event_calendar -- ExtractedEventsBatch
# =====================================================================


def event_calendar() -> str:
    """Return ExtractedEventsBatch with 4 scheduled events."""
    events = [
        {
            "title": "Заседание Совета Безопасности ООН по Украине",
            "description": "Экстренное заседание по вопросу перемирия.",
            "event_date": "2026-03-29",
            "event_type": "political",
            "certainty": "confirmed",
            "location": "New York",
            "participants": ["UN Security Council", "Russia", "Ukraine"],
            "source_url": "",
        },
        {
            "title": "Заседание ЕЦБ по ключевой ставке",
            "description": "Плановое заседание по монетарной политике.",
            "event_date": "2026-03-29",
            "event_type": "economic",
            "certainty": "confirmed",
            "location": "Frankfurt",
            "participants": ["ECB", "Lagarde"],
            "source_url": "",
        },
        {
            "title": "Саммит G7 по энергобезопасности",
            "description": "Обсуждение энергетической независимости Европы.",
            "event_date": "2026-03-29",
            "event_type": "diplomatic",
            "certainty": "likely",
            "location": "Berlin",
            "participants": ["G7 leaders", "Germany", "France", "USA"],
            "source_url": "",
        },
        {
            "title": "Публикация данных по инфляции в России",
            "description": "Росстат публикует месячные данные по инфляции.",
            "event_date": "2026-03-29",
            "event_type": "economic",
            "certainty": "confirmed",
            "location": "Moscow",
            "participants": ["Rosstat"],
            "source_url": "",
        },
    ]
    return json.dumps({"events": events})


# =====================================================================
# 3. event_assessment -- AssessedEventsBatch
# =====================================================================


def event_assessment() -> str:
    """Return AssessedEventsBatch with 4 assessed events."""
    assessments = [
        {
            "title": "Заседание Совета Безопасности ООН по Украине",
            "newsworthiness": 0.9,
            "potential_impact": "Может привести к резолюции о перемирии.",
        },
        {
            "title": "Заседание ЕЦБ по ключевой ставке",
            "newsworthiness": 0.7,
            "potential_impact": "Влияние на курс евро и рынки.",
        },
        {
            "title": "Саммит G7 по энергобезопасности",
            "newsworthiness": 0.8,
            "potential_impact": "Новые санкции или энергетические соглашения.",
        },
        {
            "title": "Публикация данных по инфляции в России",
            "newsworthiness": 0.5,
            "potential_impact": "Сигнал для решений ЦБ РФ по ставке.",
        },
    ]
    return json.dumps({"assessments": assessments})


# =====================================================================
# 4. outlet_historian -- HeadlineStyle, WritingStyle, EditorialPosition
#    Called 3 times; use list rotation.
# =====================================================================


def outlet_historian() -> list[str]:
    """Return list of 3 JSON strings rotated by call count.

    Call 0: HeadlineStyle
    Call 1: WritingStyle
    Call 2: EditorialPosition
    """
    headline_style = json.dumps(
        {
            "avg_length_chars": 65,
            "avg_length_words": 8,
            "uses_colons": False,
            "uses_quotes": True,
            "uses_questions": False,
            "uses_numbers": True,
            "capitalization": "sentence_case",
            "vocabulary_register": "formal",
            "emotional_tone": "neutral",
            "common_patterns": [
                "Кто-то заявил о...",
                "В ... произошло...",
            ],
        }
    )

    writing_style = json.dumps(
        {
            "first_paragraph_style": "inverted_pyramid",
            "avg_first_paragraph_sentences": 2,
            "avg_first_paragraph_words": 35,
            "attribution_style": "source_first",
            "uses_dateline": True,
            "paragraph_length": "short",
        }
    )

    editorial_position = json.dumps(
        {
            "tone": "official",
            "focus_topics": ["politics", "economy", "diplomacy"],
            "avoided_topics": [],
            "framing_tendencies": [
                "neutral reporting",
                "official sources first",
            ],
            "source_preferences": [
                "government officials",
                "TASS correspondents",
            ],
            "stance_on_current_topics": {},
            "omissions": [],
        }
    )

    return [headline_style, writing_style, editorial_position]


# =====================================================================
# 5. event_clustering -- ClusterLabelBatch
# =====================================================================


def event_clustering() -> str:
    """Return ClusterLabelBatch with 2 clusters."""
    return json.dumps(
        {
            "clusters": [
                {
                    "title": "Российско-украинские переговоры",
                    "summary": (
                        "Дипломатические усилия по урегулированию конфликта "
                        "активизировались после заявлений обеих сторон "
                        "о готовности к диалогу."
                    ),
                    "category": "diplomacy",
                    "importance": 0.9,
                    "entity_prominence": 0.85,
                },
                {
                    "title": "Экономические санкции ЕС",
                    "summary": (
                        "Новый пакет санкций против российского энергетического "
                        "сектора обсуждается на уровне Еврокомиссии. "
                        "Ожидается решение в ближайшие дни."
                    ),
                    "category": "economy",
                    "importance": 0.8,
                    "entity_prominence": 0.7,
                },
            ]
        }
    )


# =====================================================================
# 6. trajectory_analysis -- TrajectoryBatch
# =====================================================================


def trajectory_analysis() -> str:
    """Return TrajectoryBatch with 2 trajectories."""
    trajectories = []
    for tid, state, mom in [
        (
            THREAD_ID_1,
            "Active diplomacy phase with multiple parallel tracks.",
            "escalating",
        ),
        (
            THREAD_ID_2,
            "Sanctions debate intensifying within EU institutions.",
            "stable",
        ),
    ]:
        trajectories.append(
            {
                "current_state": state,
                "momentum": mom,
                "momentum_explanation": f"Momentum assessment for {tid}.",
                "scenarios": [
                    {
                        "scenario_type": "baseline",
                        "description": "Current trajectory continues without major disruption.",
                        "probability": 0.5,
                        "key_indicators": [
                            "Regular diplomatic meetings continue",
                            "No ceasefire violations",
                        ],
                        "headline_potential": "Переговоры продолжаются в штатном режиме",
                    },
                    {
                        "scenario_type": "optimistic",
                        "description": "Breakthrough agreement reached on key issues.",
                        "probability": 0.25,
                        "key_indicators": [
                            "Joint statement issued",
                            "Ceasefire agreement signed",
                        ],
                        "headline_potential": "Прорыв на переговорах в Женеве",
                    },
                    {
                        "scenario_type": "pessimistic",
                        "description": "Talks collapse due to irreconcilable demands.",
                        "probability": 0.25,
                        "key_indicators": [
                            "Delegation walks out",
                            "Military escalation on the ground",
                        ],
                        "headline_potential": "Переговоры зашли в тупик",
                    },
                ],
                "key_drivers": [
                    "US diplomatic pressure",
                    "European energy concerns",
                    "Internal political dynamics",
                ],
                "uncertainties": [
                    "Willingness of parties to compromise",
                    "Impact of domestic politics on negotiating positions",
                ],
            }
        )
    return json.dumps({"trajectories": trajectories})


# =====================================================================
# 7. cross_impact_analysis -- CrossImpactOutput
# =====================================================================


def cross_impact_analysis() -> str:
    """Return CrossImpactOutput with one significant pair."""
    return json.dumps(
        {
            "pairs": [
                {
                    "source": 1,
                    "target": 2,
                    "impact": 0.4,
                    "explanation": ("Diplomatic progress affects sanctions policy"),
                }
            ]
        }
    )


# =====================================================================
# 8. geopolitical_analysis -- GeopoliticalBatch
# =====================================================================


def geopolitical_analysis() -> str:
    """Return GeopoliticalBatch with 2 assessments."""
    assessments = [
        {
            "thread_id": THREAD_ID_1,
            "strategic_actors": [
                {
                    "name": "Russia",
                    "role": "initiator",
                    "interests": [
                        "Security guarantees",
                        "Sanctions relief",
                    ],
                    "likely_actions": [
                        "Propose ceasefire framework",
                        "Leverage energy supplies",
                    ],
                    "leverage": "Energy exports and military position",
                },
                {
                    "name": "Ukraine",
                    "role": "target",
                    "interests": [
                        "Territorial integrity",
                        "EU integration",
                    ],
                    "likely_actions": [
                        "Seek security guarantees from NATO",
                    ],
                    "leverage": "Western diplomatic support",
                },
            ],
            "power_dynamics": (
                "Russia holds military advantage but faces economic pressure. "
                "Ukraine leverages Western support."
            ),
            "alliance_shifts": [],
            "escalation_probability": 0.3,
            "second_order_effects": [
                "Energy price volatility in Europe",
                "Shift in NATO resource allocation",
            ],
            "sanctions_risk": "medium",
            "military_implications": "",
            "headline_angles": [
                "Diplomatic breakthrough angle",
                "Balance of power shift",
            ],
        },
        {
            "thread_id": THREAD_ID_2,
            "strategic_actors": [
                {
                    "name": "EU",
                    "role": "initiator",
                    "interests": [
                        "Energy independence",
                        "Economic stability",
                    ],
                    "likely_actions": [
                        "Adopt new sanctions package",
                    ],
                    "leverage": "Market access and financial systems",
                },
            ],
            "power_dynamics": (
                "EU acts collectively but internal divisions persist "
                "between energy-dependent and independent members."
            ),
            "alliance_shifts": ["Hungary may block consensus"],
            "escalation_probability": 0.2,
            "second_order_effects": [
                "Supply chain restructuring",
                "Rise in energy costs",
            ],
            "sanctions_risk": "high",
            "military_implications": "",
            "headline_angles": [
                "EU unity test",
                "Economic warfare escalation",
            ],
        },
    ]
    return json.dumps({"assessments": assessments})


# =====================================================================
# 9. economic_analysis -- EconomicBatch
# =====================================================================


def economic_analysis() -> str:
    """Return EconomicBatch with 2 assessments."""
    assessments = [
        {
            "thread_id": THREAD_ID_1,
            "affected_indicators": [
                {
                    "name": "EUR/USD",
                    "direction": "volatile",
                    "magnitude": "medium",
                    "confidence": 0.6,
                    "timeframe": "days",
                },
                {
                    "name": "Brent Crude",
                    "direction": "down",
                    "magnitude": "low",
                    "confidence": 0.5,
                    "timeframe": "days",
                },
            ],
            "market_impact": "neutral",
            "affected_sectors": ["energy", "defense"],
            "supply_chain_impact": "Minimal direct impact at current stage.",
            "fiscal_calendar_events": [],
            "central_bank_signals": [],
            "trade_flow_impact": "",
            "commodity_prices": ["Brent Crude -1%"],
            "employment_impact": "",
            "headline_angles": [
                "Energy price reaction",
                "Market uncertainty",
            ],
        },
        {
            "thread_id": THREAD_ID_2,
            "affected_indicators": [
                {
                    "name": "European natural gas",
                    "direction": "up",
                    "magnitude": "high",
                    "confidence": 0.7,
                    "timeframe": "weeks",
                },
            ],
            "market_impact": "negative",
            "affected_sectors": ["energy", "manufacturing", "utilities"],
            "supply_chain_impact": "European industry faces higher input costs.",
            "fiscal_calendar_events": ["ECB rate decision"],
            "central_bank_signals": ["Hawkish ECB rhetoric on inflation"],
            "trade_flow_impact": "Rerouting of LNG supplies.",
            "commodity_prices": ["TTF +5-8%", "LNG spot +3%"],
            "employment_impact": "",
            "headline_angles": [
                "Sanctions hit European wallets",
                "Energy crisis deepens",
            ],
        },
    ]
    return json.dumps({"assessments": assessments})


# =====================================================================
# 10. media_analysis -- MediaBatch
# =====================================================================


def media_analysis() -> str:
    """Return MediaBatch with 2 assessments including newsworthiness sub-object."""
    assessments = [
        {
            "thread_id": THREAD_ID_1,
            "newsworthiness": {
                "timeliness": 0.9,
                "impact": 0.85,
                "prominence": 0.8,
                "proximity": 0.7,
                "conflict": 0.6,
                "novelty": 0.5,
            },
            "editorial_fit": 0.9,
            "editorial_fit_explanation": (
                "Directly aligns with outlet's focus on politics and diplomacy."
            ),
            "news_cycle_position": "developing",
            "saturation": 0.3,
            "coverage_probability": 0.95,
            "predicted_prominence": "top_headline",
            "likely_framing": "Diplomatic progress framing.",
            "competing_stories": ["ECB rate decision"],
            "headline_angles": [
                "Прорыв на переговорах",
                "Дипломатический поворот",
            ],
        },
        {
            "thread_id": THREAD_ID_2,
            "newsworthiness": {
                "timeliness": 0.7,
                "impact": 0.75,
                "prominence": 0.65,
                "proximity": 0.6,
                "conflict": 0.7,
                "novelty": 0.4,
            },
            "editorial_fit": 0.7,
            "editorial_fit_explanation": (
                "Economic sanctions topic fits outlet's economy coverage."
            ),
            "news_cycle_position": "emerging",
            "saturation": 0.5,
            "coverage_probability": 0.8,
            "predicted_prominence": "major",
            "likely_framing": "Economic impact framing.",
            "competing_stories": ["Diplomatic negotiations"],
            "headline_angles": [
                "Новый пакет санкций",
                "Экономическое давление усиливается",
            ],
        },
    ]
    return json.dumps({"assessments": assessments})


# =====================================================================
# 11-15 / 17-21. Delphi persona factories (R1 + R2)
# =====================================================================

# Base probabilities per thread; each persona gets a +-offset.
_BASE_PROB = {THREAD_ID_1: 0.65, THREAD_ID_2: 0.45}
_BASE_NEWS = {THREAD_ID_1: 0.8, THREAD_ID_2: 0.6}

_PERSONA_OFFSETS: dict[str, float] = {
    "realist": 0.00,
    "geostrateg": 0.05,
    "economist": -0.05,
    "media": 0.03,
    "devils": -0.10,
}


def _make_persona_assessment(
    persona_id: str,
    round_number: int,
) -> str:
    """Build a PersonaAssessment JSON for *persona_id* and *round_number*.

    Each persona returns 5 predictions (min_length=5 per schema) -- 2 per
    thread plus 1 additional base for thread 1 -- so we generate 3 for
    thread_1 and 2 for thread_2.

    Round 2 assessments include populated ``revisions_made``.
    """
    offset = _PERSONA_OFFSETS.get(persona_id, 0.0)
    predictions = []

    for i, tid in enumerate(THREAD_IDS):
        base_p = _BASE_PROB[tid] + offset
        base_n = _BASE_NEWS[tid]
        # Clamp to [0.01, 0.99]
        prob = max(0.01, min(0.99, base_p))
        predictions.append(
            {
                "event_thread_id": tid,
                "prediction": (
                    f"Prediction for {tid} by {persona_id} "
                    f"(round {round_number}): significant development expected."
                ),
                "probability": round(prob, 2),
                "newsworthiness": base_n,
                "scenario_type": "baseline",
                "reasoning": (
                    f"Based on analysis of current dynamics, {persona_id} "
                    f"assesses a {'higher' if offset > 0 else 'baseline'} "
                    "probability of this outcome materializing. "
                    "Multiple indicators support this assessment. "
                    "The trend direction is consistent with recent developments."
                ),
                "key_assumptions": [
                    "Current diplomatic framework remains intact",
                    "No major external shocks occur",
                ],
                "evidence": [f"Signal data for {tid}"],
                "conditional_on": [],
            }
        )

    # Add 3 more predictions (min_length=5) with slight variations
    for extra_idx in range(3):
        tid = THREAD_IDS[extra_idx % len(THREAD_IDS)]
        base_p = _BASE_PROB[tid] + offset + (0.05 * (extra_idx + 1))
        prob = max(0.01, min(0.99, base_p))
        predictions.append(
            {
                "event_thread_id": tid,
                "prediction": (
                    f"Secondary prediction #{extra_idx + 1} for {tid} "
                    f"by {persona_id}: alternative scenario considered."
                ),
                "probability": round(prob, 2),
                "newsworthiness": round(_BASE_NEWS[tid] - 0.1, 2),
                "scenario_type": "baseline",
                "reasoning": (
                    f"Alternative angle from {persona_id} perspective. "
                    "Supporting evidence is weaker but scenario is plausible. "
                    "Risk factors warrant monitoring."
                ),
                "key_assumptions": [
                    "Alternative pathway remains open",
                    "Key actors maintain stated positions",
                ],
                "evidence": [f"Secondary signal data for {tid}"],
                "conditional_on": [],
            }
        )

    revisions: list[str] = []
    rationale = ""
    if round_number == 2:
        revisions = [f"Adjusted probability for {THREAD_ID_1} based on mediator feedback"]
        rationale = (
            "Mediator synthesis highlighted consensus on thread 1 "
            "and dispute on thread 2; adjusted accordingly."
        )

    return json.dumps(
        {
            "persona_id": persona_id,
            "round_number": round_number,
            "predictions": predictions,
            "cross_impacts_noted": [
                f"If {THREAD_ID_1} resolves positively, {THREAD_ID_2} probability drops"
            ],
            "blind_spots": [f"{persona_id} may underweight domestic political factors"],
            "confidence_self_assessment": round(0.7 + offset, 2),
            "revisions_made": revisions,
            "revision_rationale": rationale,
        }
    )


def _delphi_dispatcher(
    round_number: int,
    persona_id: str,
) -> str:
    """Return static JSON for a Delphi persona task."""
    return _make_persona_assessment(persona_id, round_number)


def delphi_r1_realist() -> str:
    return _delphi_dispatcher(1, "realist")


def delphi_r1_geostrateg() -> str:
    return _delphi_dispatcher(1, "geostrateg")


def delphi_r1_economist() -> str:
    return _delphi_dispatcher(1, "economist")


def delphi_r1_media() -> str:
    return _delphi_dispatcher(1, "media")


def delphi_r1_devils() -> str:
    return _delphi_dispatcher(1, "devils")


def delphi_r2_realist() -> str:
    return _delphi_dispatcher(2, "realist")


def delphi_r2_geostrateg() -> str:
    return _delphi_dispatcher(2, "geostrateg")


def delphi_r2_economist() -> str:
    return _delphi_dispatcher(2, "economist")


def delphi_r2_media() -> str:
    return _delphi_dispatcher(2, "media")


def delphi_r2_devils() -> str:
    return _delphi_dispatcher(2, "devils")


# =====================================================================
# 16. mediator -- MediatorSynthesis
# =====================================================================


def mediator() -> str:
    """Return MediatorSynthesis JSON."""
    return json.dumps(
        {
            "consensus_areas": [
                {
                    "event_thread_id": THREAD_ID_1,
                    "median_probability": 0.65,
                    "spread": 0.1,
                    "num_agents": 5,
                }
            ],
            "disputes": [
                {
                    "event_thread_id": THREAD_ID_2,
                    "median_probability": 0.45,
                    "spread": 0.2,
                    "positions": [
                        {
                            "agent_label": "Expert A",
                            "probability": 0.55,
                            "reasoning_summary": (
                                "Sanctions package will be adopted in full "
                                "given current political momentum."
                            ),
                            "key_assumptions": [
                                "EU internal consensus holds",
                            ],
                        },
                        {
                            "agent_label": "Expert B",
                            "probability": 0.35,
                            "reasoning_summary": (
                                "Hungary and other skeptics will water down "
                                "the sanctions package significantly."
                            ),
                            "key_assumptions": [
                                "Veto risk remains high",
                            ],
                        },
                    ],
                    "key_question": (
                        "Will Hungary exercise its veto on the new sanctions package?"
                    ),
                }
            ],
            "gaps": [
                {
                    "event_thread_id": THREAD_ID_1,
                    "mentioned_by": ["Expert A", "Expert B"],
                    "note": ("Insufficient analysis of China's potential mediating role."),
                }
            ],
            "cross_impact_flags": [
                {
                    "prediction_event_id": THREAD_ID_1,
                    "depends_on_event_id": THREAD_ID_2,
                    "note": ("Sanctions outcome influences diplomatic leverage in negotiations."),
                }
            ],
            "overall_summary": (
                "Five experts assessed two main event threads. "
                "Consensus exists on the diplomatic track probability (~0.65). "
                "Significant dispute on sanctions adoption (~0.35-0.55). "
                "Key gap: China's role underexplored."
            ),
            "supplementary_facts": [
                "EU Foreign Affairs Council scheduled for March 30",
            ],
        }
    )


# =====================================================================
# 22. judge -- JudgeResult
# =====================================================================


def judge() -> str:
    """Return JudgeResult JSON with 2 ranked predictions."""
    return json.dumps(
        {
            "ranked_predictions": [
                {
                    "event_thread_id": THREAD_ID_1,
                    "prediction": (
                        "Россия и Украина достигли предварительных "
                        "договорённостей на переговорах в Женеве."
                    ),
                    "calibrated_probability": 0.62,
                    "raw_probability": 0.65,
                    "headline_score": 0.85,
                    "newsworthiness": 0.9,
                    "confidence_label": "высокая",
                    "agreement_level": "consensus",
                    "spread": 0.1,
                    "reasoning": (
                        "Five experts converge on ~0.65 probability. "
                        "Multiple diplomatic signals support this outcome. "
                        "Calibration adjustment: -0.03 for overconfidence bias."
                    ),
                    "evidence_chain": [
                        {"source": "TASS wire", "summary": "Official statement on talks progress"},
                        {"source": "Reuters", "summary": "Diplomatic sources confirm agenda"},
                    ],
                    "dissenting_views": [],
                    "is_wild_card": False,
                    "rank": 1,
                },
                {
                    "event_thread_id": THREAD_ID_2,
                    "prediction": (
                        "ЕС утвердит новый пакет санкций против энергетического сектора России."
                    ),
                    "calibrated_probability": 0.43,
                    "raw_probability": 0.45,
                    "headline_score": 0.65,
                    "newsworthiness": 0.75,
                    "confidence_label": "умеренная",
                    "agreement_level": "majority_dissent",
                    "spread": 0.2,
                    "reasoning": (
                        "Experts split 3-2 on adoption. "
                        "Hungary veto risk is the main uncertainty. "
                        "Calibration: -0.02 for spread penalty."
                    ),
                    "evidence_chain": [
                        {"source": "EU Council", "summary": "Draft sanctions package circulated"},
                    ],
                    "dissenting_views": [
                        {
                            "agent_label": "Economist",
                            "probability": 0.35,
                            "reasoning": (
                                "Economic costs for EU members make full adoption unlikely."
                            ),
                        }
                    ],
                    "is_wild_card": False,
                    "rank": 2,
                },
            ],
            "aggregation_notes": (
                "Two main predictions ranked by headline score. "
                "Thread 1 shows strong consensus; Thread 2 is contested."
            ),
        }
    )


# =====================================================================
# 23. framing -- FramingBrief (callable dispatcher, cycles thread IDs)
# =====================================================================

_FRAMING_FIXTURES: dict[str, dict[str, Any]] = {
    THREAD_ID_1: {
        "event_thread_id": THREAD_ID_1,
        "outlet_name": "ТАСС",
        "framing_strategy": "neutral_report",
        "angle": "Diplomatic breakthrough angle",
        "emphasis_points": [
            "Progress in negotiations",
            "Positions of both sides",
        ],
        "omission_points": [],
        "headline_tone": "neutral-informative",
        "likely_sources": [
            "МИД РФ",
            "ТАСС корреспонденты",
        ],
        "section": "Политика",
        "news_cycle_hook": "Breaking development",
        "editorial_alignment_score": 0.85,
    },
    THREAD_ID_2: {
        "event_thread_id": THREAD_ID_2,
        "outlet_name": "ТАСС",
        "framing_strategy": "analytical",
        "angle": "Economic implications of new sanctions for EU members",
        "emphasis_points": [
            "Impact on European economy",
            "Russia's response measures",
        ],
        "omission_points": [],
        "headline_tone": "neutral-informative",
        "likely_sources": [
            "Минэкономразвития",
            "Аналитики",
        ],
        "section": "Экономика",
        "news_cycle_hook": "Ongoing sanctions series",
        "editorial_alignment_score": 0.75,
    },
}


def framing_dispatcher(
    task: str,
    messages: list[Any],
    call_count: int,
) -> str:
    """Callable dispatcher for ``framing`` task -- cycles through thread IDs."""
    tid = THREAD_IDS[call_count % len(THREAD_IDS)]
    return json.dumps(_FRAMING_FIXTURES[tid])


# =====================================================================
# 24. style_generation_ru -- GeneratedHeadlineSet (callable dispatcher)
# =====================================================================

_STYLE_FIXTURES: dict[str, dict[str, Any]] = {
    THREAD_ID_1: {
        "headlines": [
            {
                "id": "gen_001",
                "event_thread_id": THREAD_ID_1,
                "variant_number": 1,
                "headline": ("Россия и Украина достигли прорыва на переговорах в Женеве"),
                "first_paragraph": (
                    "Представители России и Украины завершили "
                    "трёхдневный раунд переговоров в Женеве, "
                    "достигнув предварительных договорённостей по ряду "
                    "ключевых вопросов, сообщили источники, знакомые "
                    "с ходом переговоров."
                ),
                "headline_language": "ru",
                "length_deviation": 0.0,
                "is_revision": False,
                "revision_of_id": None,
            },
            {
                "id": "gen_002",
                "event_thread_id": THREAD_ID_1,
                "variant_number": 2,
                "headline": (
                    "Женевские переговоры завершились подписанием протокола о намерениях"
                ),
                "first_paragraph": (
                    "По итогам женевского раунда переговоров стороны "
                    "подписали протокол о намерениях, предусматривающий "
                    "поэтапное урегулирование конфликта, заявил глава "
                    "российской делегации."
                ),
                "headline_language": "ru",
                "length_deviation": 0.0,
                "is_revision": False,
                "revision_of_id": None,
            },
            {
                "id": "gen_003",
                "event_thread_id": THREAD_ID_1,
                "variant_number": 3,
                "headline": (
                    "МИД РФ: Женевские договорённости открывают путь к мирному урегулированию"
                ),
                "first_paragraph": (
                    "Министерство иностранных дел России назвало "
                    "достигнутые в Женеве договорённости "
                    '"значительным шагом вперёд" и призвало все '
                    "стороны к выполнению взятых обязательств."
                ),
                "headline_language": "ru",
                "length_deviation": 0.0,
                "is_revision": False,
                "revision_of_id": None,
            },
        ]
    },
    THREAD_ID_2: {
        "headlines": [
            {
                "id": "gen_004",
                "event_thread_id": THREAD_ID_2,
                "variant_number": 1,
                "headline": (
                    "Евросоюз согласовал новый пакет санкций против энергосектора России"
                ),
                "first_paragraph": (
                    "Совет ЕС утвердил очередной пакет ограничительных "
                    "мер, направленных против российского "
                    "энергетического сектора, сообщили в пресс-службе "
                    "Еврокомиссии."
                ),
                "headline_language": "ru",
                "length_deviation": 0.0,
                "is_revision": False,
                "revision_of_id": None,
            },
            {
                "id": "gen_005",
                "event_thread_id": THREAD_ID_2,
                "variant_number": 2,
                "headline": ("Новые санкции ЕС затронут поставки российского СПГ в Европу"),
                "first_paragraph": (
                    "Принятый Евросоюзом пакет санкций впервые "
                    "включает ограничения на импорт российского "
                    "сжиженного природного газа, что может существенно "
                    "повлиять на энергобаланс региона."
                ),
                "headline_language": "ru",
                "length_deviation": 0.0,
                "is_revision": False,
                "revision_of_id": None,
            },
            {
                "id": "gen_006",
                "event_thread_id": THREAD_ID_2,
                "variant_number": 3,
                "headline": ("Москва пообещала зеркальные меры в ответ на санкции ЕС"),
                "first_paragraph": (
                    "Россия предупредила о введении ответных мер "
                    "в случае принятия нового пакета санкций, "
                    "заявил официальный представитель МИД РФ "
                    "на брифинге в Москве."
                ),
                "headline_language": "ru",
                "length_deviation": 0.0,
                "is_revision": False,
                "revision_of_id": None,
            },
        ]
    },
}


def style_generation_dispatcher(
    task: str,
    messages: list[Any],
    call_count: int,
) -> str:
    """Callable dispatcher for ``style_generation_ru`` -- cycles through thread IDs."""
    tid = THREAD_IDS[call_count % len(THREAD_IDS)]
    return json.dumps(_STYLE_FIXTURES[tid])


# =====================================================================
# 25-26. quality_factcheck / quality_style -- CheckResult (static)
# =====================================================================


def quality_factcheck() -> str:
    """Return CheckResult JSON for factual check."""
    return json.dumps(
        {
            "score": 4,
            "feedback": "Factual claims are consistent with available evidence.",
        }
    )


def quality_style() -> str:
    """Return CheckResult JSON for style check."""
    return json.dumps(
        {
            "score": 4,
            "feedback": "Style matches editorial guidelines.",
        }
    )


# =====================================================================
# Master dispatcher builder
# =====================================================================


def build_all_dispatchers() -> dict[str, Any]:
    """Return the complete task -> dispatcher map for MockLLMClient.

    Returns:
        A dict mapping every known task ID to a static JSON string,
        list of strings, or callable dispatcher.
    """
    return {
        # Stage 1: Collection
        "news_scout_search": news_scout_search(),
        "event_calendar": event_calendar(),
        "event_assessment": event_assessment(),
        "outlet_historian": outlet_historian(),  # list[str], rotated
        # Stage 2: Event identification
        "event_clustering": event_clustering(),
        # Stage 3: Trajectory & analysis
        "trajectory_analysis": trajectory_analysis(),
        "cross_impact_analysis": cross_impact_analysis(),
        "geopolitical_analysis": geopolitical_analysis(),
        "economic_analysis": economic_analysis(),
        "media_analysis": media_analysis(),
        # Stage 4: Delphi Round 1
        "delphi_r1_realist": delphi_r1_realist(),
        "delphi_r1_geostrateg": delphi_r1_geostrateg(),
        "delphi_r1_economist": delphi_r1_economist(),
        "delphi_r1_media": delphi_r1_media(),
        "delphi_r1_devils": delphi_r1_devils(),
        # Stage 4.5: Mediator
        "mediator": mediator(),
        # Stage 5: Delphi Round 2
        "delphi_r2_realist": delphi_r2_realist(),
        "delphi_r2_geostrateg": delphi_r2_geostrateg(),
        "delphi_r2_economist": delphi_r2_economist(),
        "delphi_r2_media": delphi_r2_media(),
        "delphi_r2_devils": delphi_r2_devils(),
        # Stage 6: Judge
        "judge": judge(),
        # Stage 7: Framing (callable -- cycles thread IDs)
        "framing": framing_dispatcher,
        # Stage 8: Style generation (callable -- cycles thread IDs)
        "style_generation": style_generation_dispatcher,
        "style_generation_ru": style_generation_dispatcher,
        # Stage 9: Quality gate
        "quality_factcheck": quality_factcheck(),
        "quality_style": quality_style(),
    }
