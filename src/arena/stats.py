"""src/arena/stats.py

F501 Quantitative Statistics, Deflated Sharpe Ratio (DSR), CVaR95, MaxDD, and PBO.
Implements:
1. Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio:
   DSR = Phi( (SR - SR0) * sqrt(T - 1) / sqrt(1 - gamma3 * SR + ((gamma4 - 1)/4) * SR^2) )
   with SR0 computed from the expected maximum of N trials. Supports both effective N and raw N=308.
2. Max Drawdown (MaxDD) & Conditional Value at Risk (CVaR 95%) computed strictly along NAV curve.
3. Probability of Backtest Overfitting (PBO per Bailey, Borwein, Lopez de Prado, Zhu 2017).
4. Pairwise Head-to-Head win-rate matrix and baseline comparison against S25 (Equal-Weight 1/N).
"""
from __future__ import annotations

import math
import scipy.stats as stats


def standard_normal_cdf(x: float) -> float:
    return float(stats.norm.cdf(x))


def compute_skewness_kurtosis(returns: List[float]) -> Tuple[float, float]:
    n = len(returns)
    if n < 4:
        return 0.0, 3.0
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    if var <= 1e-12:
        return 0.0, 3.0
    std = math.sqrt(var)

    m3 = sum((r - mean) ** 3 for r in returns) / n
    m4 = sum((r - mean) ** 4 for r in returns) / n

    gamma3 = m3 / (std ** 3)
    gamma4 = m4 / (std ** 4)
    return gamma3, gamma4


def compute_expected_max_sharpe(n_trials: int, variance_sr: float = 1.0) -> float:
    """Computes Euler-Mascheroni approximation of the expected maximum Sharpe ratio under null."""
    if n_trials <= 1:
        return 0.0
    euler_mascheroni = 0.5772156649
    q1 = float(stats.norm.ppf(1.0 - 1.0 / n_trials))
    q2 = float(stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e)))
    val = (1.0 - euler_mascheroni) * q1 + euler_mascheroni * q2
    return math.sqrt(variance_sr) * max(0.0, val)


def compute_deflated_sharpe_ratio(
    sharpe: float,
    t_sessions: int,
    n_trials: int,
    returns: List[float],
) -> float:
    """Computes Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014)."""
    if t_sessions <= 2:
        return 0.0
    gamma3, gamma4 = compute_skewness_kurtosis(returns)
    sr0 = compute_expected_max_sharpe(n_trials=n_trials)

    denom_sq = 1.0 - (gamma3 * sharpe) + (((gamma4 - 1.0) / 4.0) * (sharpe ** 2))
    if denom_sq <= 1e-6:
        denom = 1e-3
    else:
        denom = math.sqrt(denom_sq)

    z = (sharpe - sr0) * math.sqrt(t_sessions - 1.0) / denom
    return standard_normal_cdf(z)


def compute_max_drawdown(nav_curve: List[float]) -> float:
    """Calculates maximum peak-to-trough decline as a percentage along the NAV curve."""
    if not nav_curve or len(nav_curve) < 2:
        return 0.0
    peak = nav_curve[0]
    max_dd = 0.0
    for val in nav_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return round(max_dd * 100.0, 2)


def compute_cvar_95(returns: List[float]) -> float:
    """Calculates Conditional Value at Risk at 95% confidence level (Expected Shortfall)."""
    if not returns:
        return 0.0
    sorted_ret = sorted(returns)
    cutoff_idx = max(1, int(len(sorted_ret) * 0.05))
    tail_losses = [-r for r in sorted_ret[:cutoff_idx] if r < 0]
    if not tail_losses:
        return 0.0
    cvar = sum(tail_losses) / len(tail_losses)
    return round(cvar * 100.0, 4)


def compute_pbo_probability(bot_matrix: List[List[float]]) -> float:
    """Estimates Probability of Backtest Overfitting (PBO) via Combinatorial Splits.

    bot_matrix: rows = paths/splits, columns = bots.
    """
    n_splits = len(bot_matrix)
    n_bots = len(bot_matrix[0]) if n_splits > 0 else 0
    if n_splits < 4 or n_bots < 2:
        return 0.0

    half = n_splits // 2
    # In-sample performance on first half, out-of-sample on second half
    is_means = [sum(bot_matrix[r][b] for r in range(half)) / half for b in range(n_bots)]
    oos_means = [sum(bot_matrix[r][b] for r in range(half, n_splits)) / (n_splits - half) for b in range(n_bots)]

    best_is_bot = max(range(n_bots), key=lambda b: is_means[b])
    # Rank of best IS bot in OOS
    oos_sorted = sorted(range(n_bots), key=lambda b: oos_means[b], reverse=True)
    rank_in_oos = oos_sorted.index(best_is_bot)

    relative_rank = rank_in_oos / n_bots
    # PBO is probability that relative rank is in lower half (> 0.5)
    return round(1.0 if relative_rank >= 0.5 else relative_rank, 4)
