"""Tests for Delphi persona configuration and agents (Stages 4-5)."""

from __future__ import annotations

import json

import pytest

from .conftest import make_llm_response, make_trajectory


class TestPersonaID:
    """Test PersonaID enumeration."""

    def test_has_five_members(self):
        from src.agents.forecasters.personas import PersonaID

        assert len(PersonaID) == 5

    def test_values_are_strings(self):
        from src.agents.forecasters.personas import PersonaID

        for pid in PersonaID:
            assert isinstance(pid.value, str)

    def test_expected_members(self):
        from src.agents.forecasters.personas import PersonaID

        expected = {"realist", "geostrateg", "economist", "media_expert", "devils_advocate"}
        actual = {pid.value for pid in PersonaID}
        assert actual == expected


class TestCognitiveBias:
    """Test CognitiveBias is frozen dataclass."""

    def test_is_frozen(self):
        from src.agents.forecasters.personas import CognitiveBias

        bias = CognitiveBias(
            over_predicts="status quo",
            under_predicts="black swans",
            anchor_type="historical precedent",
        )
        import pytest

        with pytest.raises(AttributeError):
            bias.over_predicts = "changed"  # type: ignore[misc]


class TestPERSONAS:
    """Test PERSONAS registry."""

    def test_has_five_entries(self):
        from src.agents.forecasters.personas import PERSONAS, PersonaID

        assert len(PERSONAS) == 5
        for pid in PersonaID:
            assert pid in PERSONAS

    def test_agent_names_match_orchestrator(self):
        from src.agents.forecasters.personas import PERSONAS

        expected_names = {
            "delphi_realist",
            "delphi_geostrategist",
            "delphi_economist",
            "delphi_media_expert",
            "delphi_devils_advocate",
        }
        actual_names = {p.agent_name for p in PERSONAS.values()}
        assert actual_names == expected_names

    def test_initial_weights_sum_to_one(self):
        from src.agents.forecasters.personas import PERSONAS

        total = sum(p.initial_weight for p in PERSONAS.values())
        assert abs(total - 1.0) < 0.01

    def test_each_persona_has_task_prefix(self):
        from src.agents.forecasters.personas import PERSONAS

        for persona in PERSONAS.values():
            assert persona.task_prefix, f"{persona.id} missing task_prefix"

    def test_each_persona_has_system_prompt(self):
        from src.agents.forecasters.personas import PERSONAS

        for persona in PERSONAS.values():
            assert len(persona.system_prompt) > 100, f"{persona.id} system_prompt too short"


class TestDelphiPersonaAgent:
    """Test DelphiPersonaAgent (BaseAgent subclass)."""

    def test_agent_has_correct_name(self, mock_router):
        from src.agents.forecasters.personas import PERSONAS, DelphiPersonaAgent, PersonaID

        persona = PERSONAS[PersonaID.REALIST]
        agent = DelphiPersonaAgent(llm_client=mock_router, persona=persona)
        assert agent.name == "delphi_realist"

    def test_validate_context_no_trajectories(self, mock_router, make_context):
        from src.agents.forecasters.personas import PERSONAS, DelphiPersonaAgent, PersonaID

        agent = DelphiPersonaAgent(llm_client=mock_router, persona=PERSONAS[PersonaID.REALIST])
        ctx = make_context()
        assert agent.validate_context(ctx) is not None

    def test_validate_context_with_trajectories(self, mock_router, make_context):
        from src.agents.forecasters.personas import PERSONAS, DelphiPersonaAgent, PersonaID

        agent = DelphiPersonaAgent(llm_client=mock_router, persona=PERSONAS[PersonaID.REALIST])
        ctx = make_context()
        ctx.trajectories = [make_trajectory("thread_0000")]
        assert agent.validate_context(ctx) is None

    @pytest.mark.asyncio
    async def test_execute_r1_returns_assessment(self, mock_router, make_context):
        from src.agents.forecasters.personas import PERSONAS, DelphiPersonaAgent, PersonaID

        persona = PERSONAS[PersonaID.REALIST]
        agent = DelphiPersonaAgent(llm_client=mock_router, persona=persona)
        ctx = make_context()
        ctx.trajectories = [make_trajectory("thread_0000")]

        assessment_data = {
            "persona_id": "realist",
            "round_number": 1,
            "predictions": [
                {
                    "event_thread_id": "thread_0000",
                    "prediction": "Specific event will happen with measurable impact on policy.",
                    "probability": 0.55,
                    "newsworthiness": 0.7,
                    "scenario_type": "baseline",
                    "reasoning": "Base rate analysis shows 40% historical frequency, adjusted up for current momentum and specific triggers identified.",
                    "key_assumptions": ["Status quo holds", "No external shock"],
                    "evidence": ["Treaty deadline approaching"],
                    "conditional_on": [],
                }
                for _ in range(5)
            ],
            "cross_impacts_noted": [],
            "blind_spots": [],
            "confidence_self_assessment": 0.7,
            "revisions_made": [],
            "revision_rationale": "",
        }
        mock_router.complete.return_value = make_llm_response(json.dumps(assessment_data))

        result = await agent.execute(ctx)

        assert "assessment" in result
        mock_router.complete.assert_called_once()
        call_kwargs = mock_router.complete.call_args.kwargs
        assert call_kwargs["task"] == "delphi_r1_realist"
        assert call_kwargs["json_mode"] is True

    @pytest.mark.asyncio
    async def test_execute_r2_returns_revised_assessment(self, mock_router, make_context):
        from src.agents.forecasters.personas import PERSONAS, DelphiPersonaAgent, PersonaID

        from .conftest import make_mediator_synthesis

        persona = PERSONAS[PersonaID.REALIST]
        agent = DelphiPersonaAgent(llm_client=mock_router, persona=persona)
        ctx = make_context()
        ctx.trajectories = [make_trajectory("thread_0000")]
        ctx.mediator_synthesis = make_mediator_synthesis()

        assessment_data = {
            "persona_id": "realist",
            "round_number": 2,
            "predictions": [
                {
                    "event_thread_id": "thread_0000",
                    "prediction": "Revised: event will happen with measurable impact on policy after review.",
                    "probability": 0.58,
                    "newsworthiness": 0.75,
                    "scenario_type": "baseline",
                    "reasoning": "After mediator feedback, base rate reasoning confirmed. Adjusted slightly upward based on new facts from dispute resolution.",
                    "key_assumptions": ["Status quo holds", "No external shock"],
                    "evidence": ["Treaty deadline approaching"],
                    "conditional_on": [],
                }
                for _ in range(5)
            ],
            "cross_impacts_noted": [],
            "blind_spots": [],
            "confidence_self_assessment": 0.75,
            "revisions_made": ["Adjusted probability for thread_0000"],
            "revision_rationale": "Mediator highlighted new evidence.",
        }
        mock_router.complete.return_value = make_llm_response(json.dumps(assessment_data))

        result = await agent.execute(ctx)

        assert "revised_assessment" in result
        call_kwargs = mock_router.complete.call_args.kwargs
        assert call_kwargs["task"] == "delphi_r2_realist"

    @pytest.mark.asyncio
    async def test_tracks_llm_usage(self, mock_router, make_context):
        from src.agents.forecasters.personas import PERSONAS, DelphiPersonaAgent, PersonaID

        persona = PERSONAS[PersonaID.REALIST]
        agent = DelphiPersonaAgent(llm_client=mock_router, persona=persona)
        ctx = make_context()
        ctx.trajectories = [make_trajectory("thread_0000")]

        assessment_data = {
            "persona_id": "realist",
            "round_number": 1,
            "predictions": [
                {
                    "event_thread_id": "thread_0000",
                    "prediction": "Specific event will happen with measurable impact on policy.",
                    "probability": 0.55,
                    "newsworthiness": 0.7,
                    "scenario_type": "baseline",
                    "reasoning": "Base rate analysis shows 40% historical frequency, adjusted up for current momentum and specific triggers.",
                    "key_assumptions": ["Status quo holds", "No external shock"],
                    "evidence": ["Treaty deadline approaching"],
                    "conditional_on": [],
                }
                for _ in range(5)
            ],
            "cross_impacts_noted": [],
            "blind_spots": [],
            "confidence_self_assessment": 0.7,
            "revisions_made": [],
            "revision_rationale": "",
        }
        mock_router.complete.return_value = make_llm_response(json.dumps(assessment_data))

        await agent.execute(ctx)

        assert agent._cost_usd > 0
        assert agent._tokens_in > 0

    @pytest.mark.asyncio
    async def test_parse_error_returns_fallback_assessment_r1(self, mock_router, make_context):
        """When LLM returns unparseable JSON in R1, execute returns empty assessment."""
        from src.agents.forecasters.personas import PERSONAS, DelphiPersonaAgent, PersonaID

        persona = PERSONAS[PersonaID.REALIST]
        agent = DelphiPersonaAgent(llm_client=mock_router, persona=persona)
        ctx = make_context()
        ctx.trajectories = [make_trajectory("thread_0000")]

        mock_router.complete.return_value = make_llm_response(
            "INVALID JSON — triggers PromptParseError"
        )

        result = await agent.execute(ctx)

        assert "assessment" in result
        assert result["assessment"] == {}

    @pytest.mark.asyncio
    async def test_parse_error_returns_fallback_assessment_r2(self, mock_router, make_context):
        """When LLM returns unparseable JSON in R2, execute returns empty revised_assessment."""
        from src.agents.forecasters.personas import PERSONAS, DelphiPersonaAgent, PersonaID

        from .conftest import make_mediator_synthesis

        persona = PERSONAS[PersonaID.ECONOMIST]
        agent = DelphiPersonaAgent(llm_client=mock_router, persona=persona)
        ctx = make_context()
        ctx.trajectories = [make_trajectory("thread_0000")]
        ctx.mediator_synthesis = make_mediator_synthesis()

        mock_router.complete.return_value = make_llm_response(
            'TRUNCATED JSON {"persona_id": "economist"'
        )

        result = await agent.execute(ctx)

        assert "revised_assessment" in result
        assert result["revised_assessment"] == {}

    def test_all_five_agents_have_distinct_names(self, mock_router):
        from src.agents.forecasters.personas import PERSONAS, DelphiPersonaAgent

        agents = [DelphiPersonaAgent(llm_client=mock_router, persona=p) for p in PERSONAS.values()]
        names = [a.name for a in agents]
        assert len(set(names)) == 5
