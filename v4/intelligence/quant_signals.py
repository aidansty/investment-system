import os
import requests
import time
from v4.utils.logger import log

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")


def fetch_stock_fundamentals(ticker: str) -> dict:
    """
    Fetch quantitative fundamental data for a single stock.
    Returns four key signals:
    1. Revenue growth trend (accelerating or decelerating)
    2. Earnings estimate revision direction
    3. Free cash flow positive or negative
    4. Earnings surprise magnitude
    """
    result = {
        "ticker": ticker,
        "revenue_growth_pct": None,
        "revenue_trend": "unknown",
        "estimate_revision": "unknown",
        "fcf_positive": None,
        "avg_earnings_surprise_pct": None,
        "beat_streak": 0,
        "quant_score": 0,
        "quant_summary": [],
    }

    try:
        # --- Finnhub: Basic financials ---
        if FINNHUB_KEY:
            url = f"https://finnhub.io/api/v1/stock/metric?symbol={ticker}&metric=all&token={FINNHUB_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json().get("metric", {})

                # Revenue growth
                rev_growth = data.get("revenueGrowthTTMYoy")
                if rev_growth is not None:
                    result["revenue_growth_pct"] = round(rev_growth * 100, 1)
                    if rev_growth > 0.20:
                        result["revenue_trend"] = "accelerating"
                        result["quant_summary"].append(f"Revenue growing {result['revenue_growth_pct']}% YoY — strong top-line expansion")
                    elif rev_growth > 0.05:
                        result["revenue_trend"] = "growing"
                        result["quant_summary"].append(f"Revenue growing {result['revenue_growth_pct']}% YoY — steady growth")
                    elif rev_growth > 0:
                        result["revenue_trend"] = "slow"
                        result["quant_summary"].append(f"Revenue growing slowly at {result['revenue_growth_pct']}% YoY")
                    else:
                        result["revenue_trend"] = "declining"
                        result["quant_summary"].append(f"Revenue declining {result['revenue_growth_pct']}% YoY — headwind")

                # Free cash flow
                fcf = data.get("freeCashFlowTTM")
                if fcf is not None:
                    result["fcf_positive"] = fcf > 0
                    fcf_b = round(fcf / 1e9, 2)
                    if fcf > 0:
                        result["quant_summary"].append(f"Free cash flow positive at ${fcf_b}B TTM — self-funding growth")
                    else:
                        result["quant_summary"].append(f"Free cash flow negative at ${fcf_b}B TTM — burning cash")

                # Return on equity as proxy for capital efficiency
                roe = data.get("roeTTM")
                if roe is not None:
                    roe_pct = round(roe * 100, 1)
                    if roe_pct > 15:
                        result["quant_summary"].append(f"Return on equity {roe_pct}% — highly efficient capital allocation")
                    elif roe_pct > 0:
                        result["quant_summary"].append(f"Return on equity {roe_pct}%")

            time.sleep(0.15)  # Respect Finnhub rate limits

        # --- Finnhub: Earnings surprises ---
        if FINNHUB_KEY:
            url = f"https://finnhub.io/api/v1/stock/earnings?symbol={ticker}&limit=6&token={FINNHUB_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                earnings = r.json()
                if earnings:
                    surprises = []
                    beats = 0
                    for e in earnings[:4]:
                        actual = e.get("actual")
                        estimate = e.get("estimate")
                        if actual is not None and estimate is not None and estimate != 0:
                            surprise_pct = round((actual - estimate) / abs(estimate) * 100, 1)
                            surprises.append(surprise_pct)
                            if surprise_pct > 0:
                                beats += 1

                    result["beat_streak"] = beats
                    if surprises:
                        avg_surprise = round(sum(surprises) / len(surprises), 1)
                        result["avg_earnings_surprise_pct"] = avg_surprise
                        if avg_surprise > 5:
                            result["quant_summary"].append(f"Averaging {avg_surprise}% earnings beat over last 4 quarters — consistently exceeding expectations")
                        elif avg_surprise > 0:
                            result["quant_summary"].append(f"Averaging {avg_surprise}% earnings beat — modestly outperforming estimates")
                        else:
                            result["quant_summary"].append(f"Averaging {avg_surprise}% earnings miss — struggling to meet expectations")

            time.sleep(0.15)

        # --- Finnhub: Price target / analyst consensus ---
        if FINNHUB_KEY:
            url = f"https://finnhub.io/api/v1/stock/price-target?symbol={ticker}&token={FINNHUB_KEY}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                pt_data = r.json()
                target_mean = pt_data.get("targetMean")
                target_high = pt_data.get("targetHigh")
                if target_mean:
                    result["analyst_target"] = round(target_mean, 2)
                    result["quant_summary"].append(f"Analyst consensus price target ${target_mean:.2f} (high ${target_high:.2f})")

            time.sleep(0.15)

        # --- Calculate quant score ---
        score = 0
        if result["revenue_trend"] == "accelerating":
            score += 25
        elif result["revenue_trend"] == "growing":
            score += 15
        elif result["revenue_trend"] == "slow":
            score += 5

        if result["fcf_positive"] is True:
            score += 20
        elif result["fcf_positive"] is False:
            score -= 10

        if result["avg_earnings_surprise_pct"] is not None:
            if result["avg_earnings_surprise_pct"] > 10:
                score += 30
            elif result["avg_earnings_surprise_pct"] > 5:
                score += 20
            elif result["avg_earnings_surprise_pct"] > 0:
                score += 10
            else:
                score -= 10

        if result["beat_streak"] >= 3:
            score += 25
        elif result["beat_streak"] >= 2:
            score += 15

        result["quant_score"] = max(0, min(100, score))

    except Exception as e:
        log(f"Fundamentals fetch error for {ticker}: {e}")

    return result


def fetch_industry_quant_signals(stocks_in_industry: list) -> dict:
    """
    Aggregate quantitative signals across stocks within an industry.
    Used to strengthen or weaken industry conviction scores.
    """
    if not stocks_in_industry:
        return {"aggregate_quant_score": 50, "signals": []}

    scores = []
    all_signals = []

    for ticker in stocks_in_industry[:5]:  # Max 5 stocks per industry
        fundamentals = fetch_stock_fundamentals(ticker)
        scores.append(fundamentals["quant_score"])
        all_signals.extend(fundamentals["quant_summary"][:2])
        time.sleep(0.2)

    avg_score = round(sum(scores) / len(scores)) if scores else 50

    return {
        "aggregate_quant_score": avg_score,
        "signals": all_signals[:4],
    }
