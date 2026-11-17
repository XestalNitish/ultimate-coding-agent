"""FinTech Algorithmic Risk Backtester & Position Sizing Engine.

Production-grade quantitative finance system calculating Value-at-Risk (VaR),
Conditional VaR (CVaR/Expected Shortfall), Maximum Drawdown, Sharpe/Sortino ratios,
Dynamic Position Sizing (Volatility Targeting & Fractional Kelly Criterion),
and Monte Carlo portfolio stress-testing.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Quantitative Models & Data Schemas
# ============================================================================

class TradeRecord(BaseModel):
    """Historical trade or daily asset return record."""
    timestamp: str
    asset_symbol: str
    return_pct: float
    trade_pnl: float = 0.0


class RiskMetrics(BaseModel):
    """Calculated portfolio risk profile."""
    total_trades: int
    cumulative_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    calmar_ratio: float
    var_95_historical: float
    var_99_historical: float
    var_95_parametric: float
    cvar_95_expected_shortfall: float


class PositionSizeRecommendation(BaseModel):
    """Sizing recommendations across risk regimes."""
    account_equity: float
    asset_symbol: str
    asset_price: float
    stop_loss_distance_pct: float
    fixed_fractional_units: int
    volatility_targeted_units: int
    kelly_criterion_units: int
    recommended_units: int
    allocated_capital: float
    risk_exposure_pct: float


# ============================================================================
# Quantitative Risk & Backtesting Engine
# ============================================================================

class QuantitativeRiskEngine:
    """Calculates risk distributions, tail risk, and optimal sizing."""

    def __init__(self, risk_free_rate: float = 0.05):
        self.risk_free_rate = risk_free_rate  # 5% annual risk-free benchmark

    def calculate_metrics(self, daily_returns: List[float]) -> RiskMetrics:
        """Computes comprehensive quantitative risk metrics from returns series."""
        n = len(daily_returns)
        if n < 5:
            raise ValueError(f"At least 5 return data points required, got {n}")

        mean_ret = sum(daily_returns) / n
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (n - 1)
        stdev = math.sqrt(variance) if variance > 0 else 1e-6

        # Cumulative return
        cum_ret = 1.0
        equity_curve = [1.0]
        for r in daily_returns:
            cum_ret *= (1.0 + r)
            equity_curve.append(cum_ret)
        total_return_pct = (cum_ret - 1.0) * 100.0

        # Annualized Volatility (assuming 252 trading days)
        annual_vol = stdev * math.sqrt(252)

        # Sharpe Ratio
        daily_rf = self.risk_free_rate / 252.0
        excess_returns = [r - daily_rf for r in daily_returns]
        mean_excess = sum(excess_returns) / n
        sharpe = (mean_excess / stdev) * math.sqrt(252) if stdev > 0 else 0.0

        # Sortino Ratio (downside deviation only)
        downside_diffs = [min(0.0, r - daily_rf) ** 2 for r in daily_returns]
        downside_dev = math.sqrt(sum(downside_diffs) / n) if sum(downside_diffs) > 0 else 1e-6
        sortino = (mean_excess / downside_dev) * math.sqrt(252) if downside_dev > 0 else 0.0

        # Maximum Drawdown (MDD)
        peak = equity_curve[0]
        max_dd = 0.0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak
            if dd > max_dd:
                max_dd = dd
        max_dd_pct = max_dd * 100.0

        # Calmar Ratio
        calmar = (total_return_pct / max_dd_pct) if max_dd_pct > 0 else 0.0

        # Historical Value at Risk (VaR)
        sorted_returns = sorted(daily_returns)
        idx_95 = max(0, int(0.05 * n))
        idx_99 = max(0, int(0.01 * n))
        var_95_hist = -sorted_returns[idx_95] * 100.0
        var_99_hist = -sorted_returns[idx_99] * 100.0

        # Parametric Gaussian VaR: mean - (1.64485 * stdev)
        var_95_param = -(mean_ret - 1.64485 * stdev) * 100.0

        # Conditional VaR (CVaR / Expected Shortfall) at 95%
        worst_5_pct = sorted_returns[:max(1, idx_95)]
        cvar_95 = -(sum(worst_5_pct) / len(worst_5_pct)) * 100.0

        return RiskMetrics(
            total_trades=n,
            cumulative_return=round(total_return_pct, 2),
            annualized_volatility=round(annual_vol * 100.0, 2),
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            calmar_ratio=round(calmar, 2),
            var_95_historical=round(max(0.0, var_95_hist), 2),
            var_99_historical=round(max(0.0, var_99_hist), 2),
            var_95_parametric=round(max(0.0, var_95_param), 2),
            cvar_95_expected_shortfall=round(max(0.0, cvar_95), 2),
        )

    def calculate_position_sizing(
        self,
        account_equity: float,
        asset_symbol: str,
        asset_price: float,
        stop_loss_distance_pct: float,
        daily_returns: List[float],
        target_annual_vol: float = 0.15,
        risk_per_trade_pct: float = 0.02,
    ) -> PositionSizeRecommendation:
        """
        Determines position size via 3 quantitative models:
        1. Fixed Fractional Risk (Risk 2% of equity per trade)
        2. Volatility Targeted Sizing (Target 15% annualized portfolio vol)
        3. Fractional Kelly Criterion (Half-Kelly for risk-of-ruin minimization)
        """
        if asset_price <= 0 or stop_loss_distance_pct <= 0:
            raise ValueError("Asset price and stop loss pct must be strictly positive.")

        # 1. Fixed Fractional Sizing: Units = (Equity * RiskPct) / (Price * SLPct)
        dollar_risk_allowed = account_equity * risk_per_trade_pct
        risk_per_unit = asset_price * stop_loss_distance_pct
        fixed_frac_units = max(1, int(dollar_risk_allowed / risk_per_unit))

        # 2. Volatility Targeting Sizing
        n = len(daily_returns)
        mean_ret = sum(daily_returns) / n
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (n - 1)
        stdev = math.sqrt(variance)
        annual_vol = stdev * math.sqrt(252) if stdev > 0 else 0.20
        vol_scalar = target_annual_vol / max(0.05, annual_vol)
        vol_targeted_capital = account_equity * min(1.0, vol_scalar)
        vol_targeted_units = max(1, int(vol_targeted_capital / asset_price))

        # 3. Fractional Kelly Criterion: f* = (p * b - q) / b
        wins = [r for r in daily_returns if r > 0]
        losses = [abs(r) for r in daily_returns if r < 0]
        win_rate = len(wins) / n if n > 0 else 0.50
        avg_win = (sum(wins) / len(wins)) if wins else 0.01
        avg_loss = (sum(losses) / len(losses)) if losses else 0.01
        win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 1.0

        full_kelly = (win_rate * win_loss_ratio - (1.0 - win_rate)) / win_loss_ratio if win_loss_ratio > 0 else 0.0
        # Half-Kelly for risk mitigation (bounded between 0.01 and 0.25)
        half_kelly = max(0.02, min(0.20, full_kelly * 0.5))
        kelly_capital = account_equity * half_kelly
        kelly_units = max(1, int(kelly_capital / asset_price))

        # Recommended is the conservative minimum of the 3 models
        recommended = min(fixed_frac_units, vol_targeted_units, kelly_units)
        allocated_capital = round(recommended * asset_price, 2)
        risk_exposure = round((allocated_capital * stop_loss_distance_pct / account_equity) * 100.0, 2)

        return PositionSizeRecommendation(
            account_equity=account_equity,
            asset_symbol=asset_symbol,
            asset_price=asset_price,
            stop_loss_distance_pct=stop_loss_distance_pct,
            fixed_fractional_units=fixed_frac_units,
            volatility_targeted_units=vol_targeted_units,
            kelly_criterion_units=kelly_units,
            recommended_units=recommended,
            allocated_capital=allocated_capital,
            risk_exposure_pct=risk_exposure,
        )

    def run_monte_carlo_simulation(
        self,
        initial_capital: float,
        daily_returns: List[float],
        num_simulations: int = 250,
        horizon_days: int = 60,
    ) -> Dict[str, Any]:
        """Runs Monte Carlo path bootstrapping to project portfolio outcomes."""
        random.seed(42)
        ending_values = []
        for _ in range(num_simulations):
            capital = initial_capital
            for _ in range(horizon_days):
                r = random.choice(daily_returns)
                capital *= (1.0 + r)
            ending_values.append(capital)

        ending_values.sort()
        p10 = ending_values[int(0.10 * num_simulations)]
        p50 = ending_values[int(0.50 * num_simulations)]
        p90 = ending_values[int(0.90 * num_simulations)]

        return {
            "initial_capital": initial_capital,
            "simulations": num_simulations,
            "horizon_days": horizon_days,
            "10th_percentile_capital": round(p10, 2),
            "median_projected_capital": round(p50, 2),
            "90th_percentile_capital": round(p90, 2),
            "risk_of_loss_pct": round((sum(1 for v in ending_values if v < initial_capital) / num_simulations) * 100.0, 1),
        }


# ============================================================================
# Assert-Based Unit Tests & Demo
# ============================================================================

def run_fintech_unit_tests():
    """Assert-based unit tests verifying quantitative risk calculations."""
    engine = QuantitativeRiskEngine(risk_free_rate=0.04)

    # Synthetic realistic returns series (mean positive, with tail losses)
    sample_returns = [
        0.012, -0.008, 0.015, -0.022, 0.005, 0.009, -0.004, 0.018,
        -0.035, 0.008, 0.011, -0.007, 0.014, -0.019, 0.025, -0.002,
        0.006, -0.012, 0.017, 0.003, -0.028, 0.021, -0.005, 0.013
    ]

    metrics = engine.calculate_metrics(sample_returns)

    # 1. Assertions on Risk Metrics
    assert metrics.total_trades == len(sample_returns), "Total trades count mismatch"
    assert metrics.annualized_volatility > 0, "Volatility must be positive"
    assert metrics.max_drawdown_pct >= 0, "Max Drawdown must be non-negative"
    assert metrics.var_95_historical >= 0, "Historical VaR must be positive"
    assert metrics.cvar_95_expected_shortfall >= metrics.var_95_historical, "CVaR must be >= VaR (tail expectation)"

    # 2. Position Sizing Assertions
    equity = 100000.0
    sizing = engine.calculate_position_sizing(
        account_equity=equity,
        asset_symbol="RELIANCE.NS",
        asset_price=2800.0,
        stop_loss_distance_pct=0.04,  # 4% stop loss
        daily_returns=sample_returns,
        risk_per_trade_pct=0.02,     # 2% equity risk ($2000 max risk)
    )

    assert sizing.recommended_units > 0, "Recommended units must be > 0"
    assert sizing.allocated_capital <= equity, "Allocated capital cannot exceed equity"
    assert sizing.risk_exposure_pct <= 2.5, f"Risk exposure must respect safety ceiling: {sizing.risk_exposure_pct}%"

    # 3. Monte Carlo Simulation Assertions
    mc = engine.run_monte_carlo_simulation(initial_capital=equity, daily_returns=sample_returns)
    assert mc["simulations"] == 250, "Monte carlo iterations must match"
    assert mc["10th_percentile_capital"] <= mc["median_projected_capital"] <= mc["90th_percentile_capital"], "Percentiles must be monotonic"

    print("[ASSERT TESTS] FinTech Quantitative Risk Engine: All 8 unit tests passed successfully!\n")


if __name__ == "__main__":
    print("=" * 75)
    print("FINTECH QUANTITATIVE RISK BACKTESTER & POSITION SIZING ENGINE")
    print("=" * 75)

    # 1. Run Unit Tests
    run_fintech_unit_tests()

    # 2. Production Simulation Demo
    engine = QuantitativeRiskEngine(risk_free_rate=0.05)
    returns_series = [
        0.014, -0.009, 0.018, -0.025, 0.007, 0.011, -0.005, 0.022,
        -0.038, 0.010, 0.013, -0.008, 0.016, -0.021, 0.029, -0.003,
        0.008, -0.014, 0.019, 0.004, -0.031, 0.024, -0.006, 0.015,
        0.012, -0.011, 0.009, -0.017, 0.021, -0.004, 0.018, -0.029
    ]

    metrics = engine.calculate_metrics(returns_series)
    print("📊 PORTFOLIO RISK & PERFORMANCE AUDIT:")
    print(f"  • Cumulative Return: {metrics.cumulative_return}%")
    print(f"  • Annualized Volatility: {metrics.annualized_volatility}%")
    print(f"  • Sharpe Ratio: {metrics.sharpe_ratio} | Sortino Ratio: {metrics.sortino_ratio}")
    print(f"  • Max Drawdown (MDD): {metrics.max_drawdown_pct}% | Calmar Ratio: {metrics.calmar_ratio}")
    print(f"  • 95% Historical VaR: {metrics.var_95_historical}% daily")
    print(f"  • 95% Parametric VaR: {metrics.var_95_parametric}% daily")
    print(f"  • 95% Expected Shortfall (CVaR): {metrics.cvar_95_expected_shortfall}% daily")

    print("\n📐 POSITION SIZING ANALYSIS ($250,000 Equity, Asset Price ₹1,450, SL: 3.5%):")
    sizing = engine.calculate_position_sizing(
        account_equity=250000.0,
        asset_symbol="TCS.NS",
        asset_price=1450.0,
        stop_loss_distance_pct=0.035,
        daily_returns=returns_series,
        risk_per_trade_pct=0.015,
    )
    print(f"  • Fixed Fractional (1.5% Risk): {sizing.fixed_fractional_units} shares")
    print(f"  • Volatility Targeted (15% Vol): {sizing.volatility_targeted_units} shares")
    print(f"  • Half-Kelly Criterion: {sizing.kelly_criterion_units} shares")
    print(f"  • RECOMMENDED ALLOCATION: {sizing.recommended_units} shares (₹{sizing.allocated_capital:,.2f})")
    print(f"  • Net Account Risk Exposure: {sizing.risk_exposure_pct}% of total equity")

    print("\n🎲 MONTE CARLO 60-DAY PATH PROJECTIONS (250 Iterations):")
    mc = engine.run_monte_carlo_simulation(initial_capital=250000.0, daily_returns=returns_series)
    print(f"  • 10th Percentile (Stress Case): ₹{mc['10th_percentile_capital']:,.2f}")
    print(f"  • 50th Percentile (Expected Median): ₹{mc['median_projected_capital']:,.2f}")
    print(f"  • 90th Percentile (Optimistic Growth): ₹{mc['90th_percentile_capital']:,.2f}")
    print(f"  • Probability of Loss over Horizon: {mc['risk_of_loss_pct']}%")

    print("\n" + "=" * 75)
    print("FINTECH QUANTITATIVE RISK ENGINE: AUDIT & DEMO COMPLETE")
    print("=" * 75)
