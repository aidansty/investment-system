import time
from v4.utils.logger import log
from v4.config.settings import (
    INDUSTRY_ETF_MAP, BENCHMARK_ETF, MOMENTUM_LOOKBACK_DAYS,
    MOMENTUM_SHORT_LOOKBACK, LAYER1_TOP_N, MIN_OUTPERFORMANCE_PCT,
    CONVICTION_WEIGHTS, CONVICTION_HIGH, CONVICTION_MEDIUM
)


def calculate_industry_momentum(prices: dict) -> dict:
    """
    Calculate momentum score for each industry ETF vs SPY benchmark.
    Uses both 63-day and 21-day returns for trend confirmation.
    Returns dict: {industry_name: momentum_data}
    """
    spy_prices = prices.get(BENCHMARK_ETF, [])
    if not spy_prices or len(spy_prices) < MOMENTUM_LOOKBACK_DAYS:
        log("ERROR: SPY price data insufficient for momentum calculation")
        return {}

    spy_63d_return = (spy_prices[-1] / spy_prices[-MOMENTUM_LOOKBACK_DAYS] - 1) * 100
    spy_21d_return = (spy_prices[-1] / spy_prices[-MOMENTUM_SHORT_LOOKBACK] - 1) * 100

    results = {}

    for industry, info in INDUSTRY_ETF_MAP.items():
        etf = info["etf"]
        etf_prices = prices.get(etf, [])

        if not etf_prices or len(etf_prices) < MOMENTUM_LOOKBACK_DAYS:
            log(f"{etf} ({industry}): insufficient price history")
            continue

        try:
            etf_63d = (etf_prices[-1] / etf_prices[-MOMENTUM_LOOKBACK_DAYS] - 1) * 100
            etf_21d = (etf_prices[-1] / etf_prices[-MOMENTUM_SHORT_LOOKBACK] - 1) * 100

            excess_63d = etf_63d - spy_63d_return
            excess_21d = etf_21d - spy_21d_return

            # Momentum score 0-25
            # Full score if strongly outperforming on both timeframes
            if excess_63d > 10 and excess_21d > 5:
                momentum_score = 25
            elif excess_63d > 5 and excess_21d > 0:
                momentum_score = 20
            elif excess_63d > MIN_OUTPERFORMANCE_PCT:
                momentum_score = 15
            elif excess_63d > 0:
                momentum_score = 8
            else:
                momentum_score = 0

            results[industry] = {
                "industry": industry,
                "etf": etf,
                "sector": info["sector"],
                "current_price": round(etf_prices[-1], 2),
                "etf_63d_return": round(etf_63d, 2),
                "etf_21d_return": round(etf_21d, 2),
                "spy_63d_return": round(spy_63d_return, 2),
                "spy_21d_return": round(spy_21d_return, 2),
                "excess_63d": round(excess_63d, 2),
                "excess_21d": round(excess_21d, 2),
                "momentum_score": momentum_score,
                "outperforming": excess_63d > MIN_OUTPERFORMANCE_PCT,
            }

        except Exception as e:
            log(f"Momentum error for {etf}: {e}")
            continue

    log(f"Industry momentum calculated: {len(results)} industries scored")
    outperforming = sum(1 for v in results.values() if v["outperforming"])
    log(f"Outperforming SPY: {outperforming}/25 industries")
    return results


def layer1_filter(momentum_data: dict) -> list:
    """
    Layer 1 — Broad scan filter.
    Narrows 25 industries to top N with meaningful momentum.
    Returns sorted list of qualifying industries.
    """
    qualifying = [
        v for v in momentum_data.values()
        if v["outperforming"]
    ]

    # Sort by 63-day excess return
    qualifying.sort(key=lambda x: x["excess_63d"], reverse=True)

    top = qualifying[:LAYER1_TOP_N]
    log(f"Layer 1 filter: {len(qualifying)} outperforming → top {len(top)} selected")
    return top


def calculate_conviction_score(
    industry_data: dict,
    earnings_score: float = 0,
    event_score: float = 0,
    macro_score: float = 0,
    revenue_growth_score: float = 0,
    fcf_score: float = 0,
    earnings_surprise_score: float = 0,
) -> int:
    """
    7-component evidence-weighted conviction score 0-100.
    Momentum (25%) + Earnings revisions (20%, capped combined at 38%) +
    Revenue growth (15%) + FCF (15%) + Macro (10%) + Catalyst (10%) + Surprise (5%)
    """
    momentum_component = min(25, industry_data.get("momentum_score", 0))
    earnings_component = min(20, round(earnings_score * 20))
    # Cap combined momentum+revisions at 38 to prevent double-counting
    if momentum_component + earnings_component > 38:
        earnings_component = max(0, 38 - momentum_component)
    revenue_component = min(15, round(revenue_growth_score * 15))
    fcf_component = min(15, round(fcf_score * 15))
    macro_component = min(10, round(macro_score * 10))
    event_component = min(10, round(event_score * 10))
    surprise_component = min(5, round(earnings_surprise_score * 5))
    total = (momentum_component + earnings_component + revenue_component +
             fcf_component + macro_component + event_component + surprise_component)
    return min(100, max(0, total))


def score_macro_alignment(industry: str, macro: dict) -> float:
    """
    Score how well macro conditions align with this industry (0-1).
    Uses VIX regime, trend, and economic conditions.
    """
    score = 0.5  # neutral baseline

    vix_regime = macro.get("vix_regime", "Yellow")
    vix_trend = macro.get("vix_trend", "Flat")

    # VIX regime
    if vix_regime == "Green":
        score += 0.2
    elif vix_regime == "Red":
        score -= 0.3

    # VIX trend
    if vix_trend == "Falling":
        score += 0.15
    elif vix_trend == "Spiking":
        score -= 0.2

    # Industry-specific macro sensitivity
    defensive_industries = {"Managed Care", "Pharmaceuticals", "REITs", "Utilities"}
    cyclical_industries = {"Semiconductors", "Consumer Discretionary", "Oil & Gas"}

    if vix_regime == "Red":
        if industry in defensive_industries:
            score += 0.15  # Defensives benefit in high vol
        if industry in cyclical_industries:
            score -= 0.15  # Cyclicals hurt in high vol

    return max(0.0, min(1.0, score))


def run_industry_scan(prices: dict, news: list, macro: dict) -> dict:
    """
    Full industry intelligence scan.
    Returns structured results for all 25 industries
    with conviction scores and Layer 1/2 classifications.
    """
    log("=== Starting V4 Industry Intelligence Scan ===")

    # Calculate momentum for all 25 industries
    momentum_data = calculate_industry_momentum(prices)

    if not momentum_data:
        log("ERROR: No momentum data — cannot continue scan")
        return {"layer1": [], "layer2": [], "all_industries": {}}

    # Layer 1 — broad filter
    layer1_industries = layer1_filter(momentum_data)
    layer1_names = {ind["industry"] for ind in layer1_industries}

    # Layer 2 — deep analysis on Layer 1 survivors
    layer2_results = []

    for ind_data in layer1_industries:
        industry = ind_data["industry"]

        # Macro alignment score
        macro_score = score_macro_alignment(industry, macro)

        # Event score — placeholder, filled by event detection engine
        event_score = 0.5  # neutral until event engine runs

        # Earnings revision score — placeholder
        earnings_score = 0.5  # neutral until earnings engine runs

        # Calculate conviction
        conviction = calculate_conviction_score(
            ind_data,
            earnings_score=earnings_score,
            event_score=event_score,
            macro_score=macro_score,
        )

        layer2_results.append({
            **ind_data,
            "conviction_score": conviction,
            "macro_score": round(macro_score, 2),
            "event_score": round(event_score, 2),
            "earnings_score": round(earnings_score, 2),
            "macro_alignment": macro.get("vix_regime", "Yellow"),
            "in_layer2": True,
        })

    # Sort by conviction
    layer2_results.sort(key=lambda x: x["conviction_score"], reverse=True)

    log(f"Layer 2 complete: {len(layer2_results)} industries with conviction scores")
    if layer2_results:
        top = layer2_results[0]
        log(f"Top industry: {top['industry']} ({top['etf']}) — Conviction: {top['conviction_score']}/100")

    # Industries not in Layer 1
    all_industries = {}
    for industry, data in momentum_data.items():
        if industry in layer1_names:
            # Find in layer2 results
            for l2 in layer2_results:
                if l2["industry"] == industry:
                    all_industries[industry] = l2
                    break
        else:
            all_industries[industry] = {**data, "conviction_score": 0, "in_layer2": False}

    high_conviction = [i for i in layer2_results if i["conviction_score"] >= CONVICTION_HIGH]
    medium_conviction = [i for i in layer2_results if CONVICTION_MEDIUM <= i["conviction_score"] < CONVICTION_HIGH]

    log(f"High conviction (70+): {len(high_conviction)} industries")
    log(f"Medium conviction (45-69): {len(medium_conviction)} industries")

    return {
        "layer1": layer1_industries,
        "layer2": layer2_results,
        "all_industries": all_industries,
        "high_conviction": high_conviction,
        "medium_conviction": medium_conviction,
        "top_industries": layer2_results[:4],
    }
