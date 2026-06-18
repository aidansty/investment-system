from v4.utils.logger import log
from v4.config.settings import INDUSTRY_ETF_MAP


# Map industries to related keywords for news matching
INDUSTRY_NEWS_KEYWORDS = {
    "Semiconductors":         ["semiconductor", "chip", "wafer", "TSMC", "ASML", "fab", "memory", "DRAM", "NAND"],
    "Software":               ["software", "SaaS", "enterprise software", "cloud software", "licensing"],
    "Cybersecurity":          ["cybersecurity", "cyber attack", "ransomware", "data breach", "firewall", "zero-day"],
    "AI Infrastructure":      ["artificial intelligence", "AI", "machine learning", "GPU", "data center", "LLM"],
    "Cloud Computing":        ["cloud", "AWS", "Azure", "Google Cloud", "cloud infrastructure", "hyperscaler"],
    "Networking":             ["networking", "bandwidth", "fiber", "5G", "network infrastructure", "router"],
    "Biotech":                ["biotech", "clinical trial", "FDA approval", "drug", "therapy", "gene"],
    "Medical Devices":        ["medical device", "implant", "surgical", "diagnostic", "MRI", "FDA clearance"],
    "Managed Care":           ["managed care", "health insurance", "Medicare", "Medicaid", "utilization", "CMS"],
    "Pharmaceuticals":        ["pharmaceutical", "drug approval", "patent", "generic", "FDA", "clinical"],
    "Defense & Aerospace":    ["defense", "military", "Pentagon", "DoD", "aerospace", "missile", "contract"],
    "Energy Transition":      ["renewable", "solar", "wind", "battery", "EV", "electric vehicle", "clean energy"],
    "Oil & Gas":              ["oil", "crude", "OPEC", "natural gas", "refinery", "pipeline", "petroleum"],
    "Financials":             ["bank", "interest rate", "Federal Reserve", "credit", "lending", "financial"],
    "Regional Banks":         ["regional bank", "community bank", "deposits", "FDIC", "SVB", "loan"],
    "Investment Banking":     ["IPO", "merger", "acquisition", "M&A", "underwriting", "capital markets"],
    "Consumer Discretionary": ["consumer spending", "retail", "e-commerce", "discretionary", "luxury"],
    "Industrial Automation":  ["automation", "robot", "manufacturing", "industrial", "factory", "AI robot"],
    "Logistics & Transport":  ["logistics", "shipping", "freight", "supply chain", "trucking", "delivery"],
    "Homebuilders":           ["housing", "mortgage", "homebuilder", "real estate", "construction", "home sales"],
    "REITs":                  ["REIT", "commercial real estate", "office", "retail space", "occupancy"],
    "Commodities":            ["commodity", "gold", "copper", "aluminum", "iron ore", "raw material"],
    "Clean Energy":           ["clean energy", "IRA", "solar panel", "wind farm", "green hydrogen"],
    "Nuclear Energy":         ["nuclear", "uranium", "reactor", "SMR", "small modular reactor", "atomic"],
    "Emerging Markets":       ["emerging market", "China", "India", "Brazil", "EM", "developing"],
}

# Second and third order effect mappings
RIPPLE_EFFECTS = {
    "oil_price_spike": {
        "benefits": ["Oil & Gas", "Commodities"],
        "harms": ["Consumer Discretionary", "Logistics & Transport", "Energy Transition"],
        "second_order_benefits": ["Clean Energy", "Nuclear Energy"],
        "duration": "weeks to months",
    },
    "fed_rate_cut": {
        "benefits": ["REITs", "Homebuilders", "Financials", "Consumer Discretionary"],
        "harms": [],
        "second_order_benefits": ["Industrial Automation", "Biotech"],
        "duration": "months",
    },
    "fed_rate_hike": {
        "benefits": ["Financials", "Regional Banks"],
        "harms": ["REITs", "Homebuilders", "Emerging Markets"],
        "second_order_benefits": [],
        "duration": "months",
    },
    "ai_breakthrough": {
        "benefits": ["AI Infrastructure", "Semiconductors", "Cloud Computing", "Software"],
        "harms": [],
        "second_order_benefits": ["Networking", "Cybersecurity"],
        "duration": "months to years",
    },
    "defense_spending_increase": {
        "benefits": ["Defense & Aerospace"],
        "harms": [],
        "second_order_benefits": ["Cybersecurity", "Semiconductors"],
        "duration": "years",
    },
    "china_trade_tension": {
        "benefits": ["Defense & Aerospace", "Commodities"],
        "harms": ["Semiconductors", "Consumer Discretionary", "Emerging Markets"],
        "second_order_benefits": ["Industrial Automation"],
        "duration": "months",
    },
}


def tag_news_by_industry(news: list) -> dict:
    """
    Tag each news item with relevant industries.
    Returns dict: {industry: [relevant_news_items]}
    """
    industry_news = {industry: [] for industry in INDUSTRY_ETF_MAP.keys()}

    for item in news:
        headline = item.get("headline", "").lower()
        summary = item.get("summary", "").lower()
        text = headline + " " + summary

        for industry, keywords in INDUSTRY_NEWS_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    industry_news[industry].append(item)
                    break  # Only add once per industry

    return industry_news


def score_event_catalyst(industry: str, industry_news: list) -> float:
    """
    Score the event catalyst quality for an industry (0-1).
    Based on number and recency of relevant news items.
    """
    if not industry_news:
        return 0.3  # neutral if no specific news

    # More relevant news = higher score
    news_count = len(industry_news)
    if news_count >= 5:
        return 0.9
    elif news_count >= 3:
        return 0.75
    elif news_count >= 1:
        return 0.6
    return 0.3


def identify_ripple_effects(news: list) -> list:
    """
    Identify second and third order effects from news events.
    Returns list of ripple effect opportunities.
    """
    ripples = []
    combined_text = " ".join([
        item.get("headline", "") + " " + item.get("summary", "")
        for item in news
    ]).lower()

    # Check for trigger events
    trigger_patterns = {
        "oil_price_spike": ["oil price", "crude surges", "opec cut", "oil rally"],
        "fed_rate_cut": ["fed cuts", "rate cut", "fed pivot", "lower rates", "dovish"],
        "fed_rate_hike": ["fed hikes", "rate hike", "hawkish", "higher rates", "tightening"],
        "ai_breakthrough": ["ai breakthrough", "new model", "gpt", "claude", "gemini", "ai chip"],
        "defense_spending_increase": ["defense budget", "military spending", "nato", "defense contract"],
        "china_trade_tension": ["china tariff", "trade war", "export restriction", "china ban"],
    }

    for event_type, patterns in trigger_patterns.items():
        for pattern in patterns:
            if pattern in combined_text:
                effect = RIPPLE_EFFECTS.get(event_type, {})
                if effect:
                    ripples.append({
                        "trigger": event_type,
                        "pattern_matched": pattern,
                        "benefits": effect.get("benefits", []),
                        "harms": effect.get("harms", []),
                        "second_order_benefits": effect.get("second_order_benefits", []),
                        "duration": effect.get("duration", "unknown"),
                    })
                break  # Only match once per event type

    if ripples:
        log(f"Ripple effects identified: {len(ripples)} trigger events detected")
        for r in ripples:
            log(f"  {r['trigger']}: benefits {r['benefits']}, harms {r['harms']}")

    return ripples


def enrich_industries_with_events(layer2_results: list, news: list) -> list:
    """
    Enrich Layer 2 industry results with event intelligence.
    Updates event_score and adds event context to each industry.
    """
    # Tag news by industry
    industry_news = tag_news_by_industry(news)

    # Identify ripple effects
    ripples = identify_ripple_effects(news)

    # Build ripple benefit/harm maps
    ripple_benefits = {}
    ripple_harms = {}
    for ripple in ripples:
        for ind in ripple.get("benefits", []) + ripple.get("second_order_benefits", []):
            ripple_benefits[ind] = ripple_benefits.get(ind, []) + [ripple["trigger"]]
        for ind in ripple.get("harms", []):
            ripple_harms[ind] = ripple_harms.get(ind, []) + [ripple["trigger"]]

    # Update each industry
    enriched = []
    for ind_data in layer2_results:
        industry = ind_data["industry"]
        ind_news = industry_news.get(industry, [])

        event_score = score_event_catalyst(industry, ind_news)

        # Boost for ripple benefits
        if industry in ripple_benefits:
            event_score = min(1.0, event_score + 0.2)

        # Reduce for ripple harms
        if industry in ripple_harms:
            event_score = max(0.0, event_score - 0.25)

        # Recalculate conviction with updated event score
        from v4.intelligence.industry_scanner import calculate_conviction_score
        new_conviction = calculate_conviction_score(
            ind_data,
            earnings_score=ind_data.get("earnings_score", 0.5),
            event_score=event_score,
            macro_score=ind_data.get("macro_score", 0.5),
        )

        enriched.append({
            **ind_data,
            "event_score": round(event_score, 2),
            "conviction_score": new_conviction,
            "relevant_news": ind_news[:3],
            "ripple_benefits": ripple_benefits.get(industry, []),
            "ripple_harms": ripple_harms.get(industry, []),
            "news_count": len(ind_news),
        })

    # Re-sort by updated conviction
    enriched.sort(key=lambda x: x["conviction_score"], reverse=True)
    return enriched
