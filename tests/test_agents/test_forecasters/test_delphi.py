"""Tests for Delphi utility classes."""

from __future__ import annotations

import pytest


class TestDelphiRoundResult:
    """Test DelphiRoundResult dataclass."""

    def test_create_with_defaults(self):
        from src.agents.forecasters.delphi import DelphiRoundResult

        result = DelphiRoundResult(round_number=1, assessments={"realist": {}})
        assert result.round_number == 1
        assert result.failed_agents == []
        assert result.duration_ms == 0

    def test_create_with_failed_agents(self):
        from src.agents.forecasters.delphi import DelphiRoundResult

        result = DelphiRoundResult(
            round_number=2,
            assessments={"realist": {}, "economist": {}},
            failed_agents=["media_expert"],
            duration_ms=5000,
        )
        assert len(result.assessments) == 2
        assert "media_expert" in result.failed_agents


class TestDelphiQuorumError:
    """Test DelphiQuorumError exception."""

    def test_stores_counts(self):
        from src.agents.forecasters.delphi import DelphiQuorumError

        err = DelphiQuorumError(required=3, actual=2)
        assert err.required == 3
        assert err.actual == 2

    def test_message_includes_counts(self):
        from src.agents.forecasters.delphi import DelphiQuorumError

        err = DelphiQuorumError(required=4, actual=1)
        assert "4" in str(err)
        assert "1" in str(err)

    def test_is_exception(self):
        from src.agents.forecasters.delphi import DelphiQuorumError

        with pytest.raises(DelphiQuorumError):
            raise DelphiQuorumError(required=3, actual=2)
