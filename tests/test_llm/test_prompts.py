"""Tests for src.llm.prompts.base."""

import pytest
from pydantic import BaseModel, Field

from src.llm.prompts.base import BasePrompt, PromptParseError
from src.schemas.llm import MessageRole


class SampleOutput(BaseModel):
    name: str
    score: float = Field(ge=0.0, le=1.0)


class SamplePrompt(BasePrompt):
    system_template = "You are a {{ role }}. Analyze {{ topic }}."
    user_template = "Data: {{ data }}"
    output_schema = SampleOutput


class NoSchemaPrompt(BasePrompt):
    system_template = "You are helpful."
    user_template = "Hello {{ name }}."


class TestRender:
    def test_render_system(self):
        p = SamplePrompt()
        result = p.render_system(role="analyst", topic="events")
        assert "analyst" in result
        assert "events" in result

    def test_render_user(self):
        p = SamplePrompt()
        result = p.render_user(data="some data")
        assert "some data" in result

    def test_render_missing_variable_raises(self):
        p = SamplePrompt()
        with pytest.raises(Exception):  # Jinja2 UndefinedError
            p.render_system(role="analyst")  # missing topic

    def test_to_messages(self):
        p = SamplePrompt()
        msgs = p.to_messages(role="analyst", topic="events", data="test")
        assert len(msgs) == 2
        assert msgs[0].role == MessageRole.SYSTEM
        assert msgs[1].role == MessageRole.USER

    def test_to_messages_empty_system(self):
        class EmptySystemPrompt(BasePrompt):
            system_template = ""
            user_template = "Hello {{ name }}."

        p = EmptySystemPrompt()
        msgs = p.to_messages(name="World")
        assert len(msgs) == 1
        assert msgs[0].role == MessageRole.USER


class TestOutputSchema:
    def test_schema_instruction_present(self):
        p = SamplePrompt()
        instruction = p.render_output_schema_instruction()
        assert "Respond ONLY with valid JSON" in instruction
        assert "name" in instruction
        assert "score" in instruction

    def test_schema_instruction_none_when_no_schema(self):
        p = NoSchemaPrompt()
        assert p.render_output_schema_instruction() == ""


class TestParseResponse:
    def test_parse_valid_json(self):
        p = SamplePrompt()
        result = p.parse_response('{"name": "test", "score": 0.5}')
        assert isinstance(result, SampleOutput)
        assert result.name == "test"
        assert result.score == 0.5

    def test_parse_markdown_json_block(self):
        p = SamplePrompt()
        content = '```json\n{"name": "test", "score": 0.8}\n```'
        result = p.parse_response(content)
        assert isinstance(result, SampleOutput)
        assert result.score == 0.8

    def test_parse_invalid_json_raises(self):
        p = SamplePrompt()
        with pytest.raises(PromptParseError):
            p.parse_response("not json at all")

    def test_parse_invalid_schema_raises(self):
        p = SamplePrompt()
        with pytest.raises(PromptParseError):
            p.parse_response('{"name": "test", "score": 5.0}')  # score > 1.0

    def test_parse_no_schema_returns_none(self):
        p = NoSchemaPrompt()
        result = p.parse_response("anything")
        assert result is None

    def test_parse_error_has_raw_content(self):
        p = SamplePrompt()
        with pytest.raises(PromptParseError) as exc_info:
            p.parse_response("broken json {{{")
        assert exc_info.value.raw_content == "broken json {{{"
