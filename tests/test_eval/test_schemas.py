"""Tests for src.eval.schemas — Pydantic v2 evaluation schemas."""

import pytest
from pydantic import ValidationError

from src.eval.schemas import (
    BrierComparison,
    CorrelationResult,
    PriceMovement,
    ResolvedMarket,
)


class TestResolvedMarket:
    def test_frozen(self) -> None:
        m = ResolvedMarket(
            market_id="m1",
            question="Will X?",
            resolved_yes=True,
            closed_time="2026-03-15T12:00:00Z",
            volume=100_000.0,
        )
        with pytest.raises(ValidationError):
            m.market_id = "m2"  # type: ignore[misc]

    def test_defaults(self) -> None:
        m = ResolvedMarket(
            market_id="m1",
            question="Q?",
            resolved_yes=False,
            closed_time="2026-01-01T00:00:00Z",
            volume=5000.0,
        )
        assert m.categories == []
        assert m.clob_token_id == ""
        assert m.price_at_24h is None
        assert m.price_at_48h is None
        assert m.price_at_7d is None

    def test_negative_volume_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResolvedMarket(
                market_id="m1",
                question="Q?",
                resolved_yes=True,
                closed_time="t",
                volume=-1.0,
            )


class TestBrierComparison:
    def test_valid(self) -> None:
        bc = BrierComparison(
            n_events=10,
            delphi_brier=0.18,
            market_brier_24h=0.20,
            market_brier_48h=0.22,
            market_brier_7d=0.25,
            delphi_skill_vs_24h=0.10,
        )
        assert bc.n_events == 10
        assert bc.per_event == []

    def test_brier_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrierComparison(
                n_events=5,
                delphi_brier=1.5,  # > 1.0
                market_brier_24h=0.2,
                market_brier_48h=0.2,
                market_brier_7d=0.2,
                delphi_skill_vs_24h=0.0,
            )


class TestPriceMovement:
    def test_signed_delta(self) -> None:
        """delta_p can be negative (price dropped)."""
        pm = PriceMovement(
            market_id="m1",
            timestamp=1710500000,
            delta_p=-0.15,
            price_before=0.65,
            price_after=0.50,
        )
        assert pm.delta_p == pytest.approx(-0.15)

    def test_frozen(self) -> None:
        pm = PriceMovement(
            market_id="m1",
            timestamp=1710500000,
            delta_p=0.10,
            price_before=0.50,
            price_after=0.60,
        )
        with pytest.raises(ValidationError):
            pm.delta_p = 0.20  # type: ignore[misc]


class TestCorrelationResult:
    def test_optional_fields(self) -> None:
        """All optional fields default to None."""
        cr = CorrelationResult(n_movements=0, n_with_news=0)
        assert cr.spearman_rho is None
        assert cr.spearman_pvalue is None
        assert cr.granger_f_stat is None
        assert cr.granger_pvalue is None
        assert cr.granger_best_lag is None
        assert cr.news_precedes_market_pct is None

    def test_with_values(self) -> None:
        cr = CorrelationResult(
            n_movements=42,
            n_with_news=30,
            spearman_rho=0.35,
            spearman_pvalue=0.02,
            granger_f_stat=4.5,
            granger_pvalue=0.04,
            granger_best_lag=3,
            news_precedes_market_pct=71.4,
        )
        assert cr.n_movements == 42
        assert cr.spearman_rho == pytest.approx(0.35)
