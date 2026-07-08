import time
from v4.utils.logger import log
from v4.config.settings import (
    INDUSTRY_ETF_MAP, BENCHMARK_ETF, MOMENTUM_LOOKBACK_DAYS,
    MOMENTUM_SHORT_LOOKBACK, LAYER1_TOP_N, MIN_OUTPERFORMANCE_PCT,
    CONVICTION_WEIGHTS, CONVICTION_HIGH, CONVICTION_MEDIUM,
    INDUSTRY_STOCK_LEADERS,
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


def score_stock_leaders(prices: dict, industry: str, spy_prices: list) -> list:
    """
    Layer 2: Score individual stock leaders within a qualifying industry.
    Returns ranked list of stocks with momentum scores vs SPY.
    Uses multi-timeframe: 63-day sustained + 21-day breakout detection.
    """
    stocks = INDUSTRY_STOCK_LEADERS.get(industry, [])
    if not stocks or not spy_prices:
        return []

    spy_63d = (spy_prices[-1] / spy_prices[-63] - 1) * 100 if len(spy_prices) >= 63 else 0
    spy_21d = (spy_prices[-1] / spy_prices[-21] - 1) * 100 if len(spy_prices) >= 21 else 0

    scored = []
    for ticker in stocks:
        stk_prices = prices.get(ticker, [])
        if not stk_prices or len(stk_prices) < 63:
            continue
        try:
            stk_63d = (stk_prices[-1] / stk_prices[-63] - 1) * 100
            stk_21d = (stk_prices[-1] / stk_prices[-21] - 1) * 100 if len(stk_prices) >= 21 else 0
            exc_63d = stk_63d - spy_63d
            exc_21d = stk_21d - spy_21d

            # Multi-timeframe conviction score
            if exc_63d > 0 and exc_21d > 0:
                # Both timeframes confirm — strong signal
                combined = (exc_63d * 0.6) + (exc_21d * 0.4)
            elif exc_21d > 15 and exc_63d > -5:
                # Strong 21-day breakout even if 63-day not yet confirmed
                combined = exc_21d * 0.85
            else:
                combined = exc_63d

            # Convert to conviction score
            if combined >= 25: conv = 95
            elif combined >= 18: conv = 88
            elif combined >= 12: conv = 82
            elif combined >= 8: conv = 77
            elif combined >= 5: conv = 72
            elif combined >= 2: conv = 65
            elif combined >= 0: conv = 55
            else: conv = max(0, int(40 + combined * 2))

            scored.append({
                "ticker": ticker,
                "conviction": conv,
                "excess_63d": round(exc_63d, 2),
                "excess_21d": round(exc_21d, 2),
                "current_price": round(stk_prices[-1], 2),
                "is_breakout": exc_21d > 15 and exc_63d > -5,
            })
        except Exception as e:
            continue

    return sorted(scored, key=lambda x: x["conviction"], reverse=True)


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
    qualifying.sort(key=lambda x: (x["excess_21d"] * 2 + x["excess_63d"]), reverse=True)

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
    Catalyst-driven conviction score 0-100.
    Reweighted for aggressive monthly growth goals:
    Event catalyst (35%) + 21d breakout momentum (20%) + Earnings revisions (20%) +
    Macro alignment (10%) + 63d sustained momentum (10%) + Earnings surprise (5%)
    """
    excess_21d = industry_data.get("excess_21d", 0)
    breakout_score = min(1.0, max(0, excess_21d / 20))
    breakout_component = min(20, round(breakout_score * 20))
    momentum_component = min(10, industry_data.get("momentum_score", 0) // 2.5)
    event_component = min(35, round(event_score * 35))
    combined_fundamental = (earnings_score * 0.6 + revenue_growth_score * 0.2 + fcf_score * 0.2)
    earnings_component = min(20, round(combined_fundamental * 20))
    macro_component = min(10, round(macro_score * 10))
    surprise_component = min(5, round(earnings_surprise_score * 5))
    total = (event_component + breakout_component + earnings_component +
             macro_component + momentum_component + surprise_component)
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

    # Layer 2: Score stock leaders within each qualifying industry
    spy_prices = prices.get("SPY", [])
    top_industries = layer2_results[:4]
    for ind in top_industries:
        industry_name = ind.get("industry", "")
        stock_scores = score_stock_leaders(prices, industry_name, spy_prices)
        ind["stock_leaders"] = stock_scores[:3]
        etf_conv = ind.get("conviction_score", 0)
        if stock_scores and stock_scores[0]["conviction"] > etf_conv + 5:
            ind["recommended_security"] = stock_scores[0]["ticker"]
            ind["recommended_type"] = "stock"
            ind["recommended_conviction"] = stock_scores[0]["conviction"]
        else:
            ind["recommended_security"] = ind.get("etf", "")
            ind["recommended_type"] = "etf"
            ind["recommended_conviction"] = etf_conv

    return {
        "layer1": layer1_industries,
        "layer2": layer2_results,
        "all_industries": all_industries,
        "high_conviction": high_conviction,
        "medium_conviction": medium_conviction,
        "top_industries": top_industries,
    }
