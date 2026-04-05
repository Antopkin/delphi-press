"""Tests for horizon-aware prompt sections in persona and mediator prompts."""

from __future__ import annotations

from src.llm.prompts.forecasters.mediator import MediatorPrompt
from src.llm.prompts.forecasters.persona import PersonaPrompt
from src.schemas.events import EventTrajectory, Scenario


def _make_trajectory() -> EventTrajectory:
    return EventTrajectory(
        thread_id="thread_0001",
        current_state="Situation developing",
        momentum="stable",
        momentum_explanation="No change",
        scenarios=[
            Scenario(
                scenario_type="baseline",
                description="Status quo",
                probability=0.6,
                key_indicators=["indicator1"],
                headline_potential="Quiet",
            ),
            Scenario(
                scenario_type="optimistic",
                description="Improvement",
                probability=0.4,
                key_indicators=["indicator2"],
                headline_potential="Good news",
            ),
        ],
        key_drivers=["driver1"],
        uncertainties=["uncertainty1"],
    )


def _render_persona(horizon_band: str, horizon_days: int, persona_id: str = "realist") -> str:
    prompt = PersonaPrompt(
        persona_id=persona_id,
        system_prompt_text="You are an expert.",
    )
    return prompt.render_user(
        persona_id=persona_id,
        outlet_name="TASS",
        target_date="2026-04-01",
        event_trajectories=[_make_trajectory()],
        cross_impact_matrix=None,
        round_number=1,
        mediator_feedback=None,
        horizon_days=horizon_days,
        horizon_band=horizon_band,
        high_saturation_threads=[],
        schema_instruction="JSON schema here",
    )


def _render_mediator(horizon_band: str, horizon_days: int) -> str:
    prompt = MediatorPrompt()
    return prompt.render_user(
        outlet_name="TASS",
        target_date="2026-04-01",
        anonymized_assessments={},
        event_trajectories=[_make_trajectory()],
        horizon_days=horizon_days,
        horizon_band=horizon_band,
        schema_instruction="JSON schema here",
    )


# ── Persona: Analytical mode ──────────────────────────────────────


class TestPersonaHorizonMode:
    def test_immediate_operational_mode(self):
        text = _render_persona("immediate", 1)
        assert "OPERATIONAL" in text
        assert "breaking signals from last 24h" in text

    def test_near_mixed_mode(self):
        text = _render_persona("near", 3)
        assert "MIXED" in text
        assert "maximum uncertainty zone" in text

    def test_medium_structural_mode(self):
        text = _render_persona("medium", 6)
        assert "STRUCTURAL" in text
        assert "HEDGE toward 0.5" in text


# ── Persona: Calibration constraints ──────────────────────────────


class TestPersonaCalibration:
    def test_immediate_overestimation_warning(self):
        text = _render_persona("immediate", 1)
        assert "OVERESTIMATION" in text
        assert "[0.05, 0.95]" in text

    def test_near_scope_check(self):
        text = _render_persona("near", 3)
        assert "Scope check" in text
        assert "6 days instead of 3" in text  # horizon_days * 2

    def test_medium_hedge_warning(self):
        text = _render_persona("medium", 7)
        assert "HEDGE TO 0.5" in text
        assert "[0.07, 0.93]" in text

    def test_medium_scope_check(self):
        text = _render_persona("medium", 5)
        assert "10 days instead of 5" in text


# ── Persona: Evidence priority ────────────────────────────────────


class TestPersonaEvidencePriority:
    def test_immediate_breaking_signals_first(self):
        text = _render_persona("immediate", 2)
        assert "breaking signals (last 24h)" in text

    def test_medium_structural_factors_first(self):
        text = _render_persona("medium", 6)
        # Evidence section should prioritize scheduled events and structural
        assert "scheduled events in 5-7 day window" in text

    def test_near_balanced_evidence(self):
        text = _render_persona("near", 4)
        assert "scheduled events in 3-4 day window" in text


# ── Persona: Devil's Advocate circuit breaker ────────────────────


class TestDevilsAdvocateCircuitBreaker:
    def test_near_horizon_has_circuit_breaker(self):
        text = _render_persona("near", 3, persona_id="devils_advocate")
        assert "CIRCUIT BREAKER HUNT" in text
        assert "maximum groupthink risk" in text

    def test_immediate_no_circuit_breaker(self):
        text = _render_persona("immediate", 1, persona_id="devils_advocate")
        assert "CIRCUIT BREAKER" not in text

    def test_non_devils_no_circuit_breaker(self):
        text = _render_persona("near", 3, persona_id="realist")
        assert "CIRCUIT BREAKER" not in text


# ── Persona: Temporal output format ──────────────────────────────


class TestPersonaTemporalFormat:
    def test_predicted_date_required(self):
        text = _render_persona("immediate", 1)
        assert "predicted_date" in text
        assert "uncertainty_days" in text

    def test_confidence_interval_for_non_immediate(self):
        text = _render_persona("near", 3)
        assert "confidence_interval_95" in text

    def test_no_confidence_interval_for_immediate(self):
        text = _render_persona("immediate", 1)
        assert "confidence_interval_95" not in text


# ── Mediator: Horizon synthesis ──────────────────────────────────


# ── Persona: Media saturation warning ────────────────────────────


class TestPersonaSaturationWarning:
    def test_high_saturation_shows_warning(self):
        prompt = PersonaPrompt(persona_id="realist", system_prompt_text="Expert.")
        text = prompt.render_user(
            persona_id="realist",
            outlet_name="TASS",
            target_date="2026-04-01",
            event_trajectories=[_make_trajectory()],
            cross_impact_matrix=None,
            round_number=1,
            mediator_feedback=None,
            horizon_days=2,
            horizon_band="immediate",
            high_saturation_threads=[
                {"title": "Ukraine conflict", "saturation": 0.85, "coverage_days": 14},
            ],
            schema_instruction="JSON",
        )
        assert "MEDIA SATURATION WARNING" in text
        assert "Ukraine conflict" in text
        assert "14 days" in text

    def test_no_saturation_no_warning(self):
        text = _render_persona("immediate", 1)
        assert "MEDIA SATURATION WARNING" not in text


class TestMediatorHorizon:
    def test_immediate_scheduled_events_check(self):
        text = _render_mediator("immediate", 2)
        assert "SCHEDULED EVENTS CHECK" in text
        assert "Media Expert and Economist carry extra weight" in text

    def test_near_equal_weight(self):
        text = _render_mediator("near", 3)
        assert "equal weight" in text
        assert "maximum uncertainty zone" in text

    def test_medium_news_decay_check(self):
        text = _render_mediator("medium", 6)
        assert "NEWS DECAY CHECK" in text
        assert "Realist and Geopolitical Strategist carry extra weight" in text
