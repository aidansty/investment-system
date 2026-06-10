# GICS Sector and Sub-Industry classification
# Static lookup table — update quarterly with universe review
# Used for concentration limits and overlap detection

SECTOR_SUBINDUSTRY_MAP = {
    # Semiconductors
    "NVDA": ("Technology", "Semiconductors"),
    "AMD": ("Technology", "Semiconductors"),
    "INTC": ("Technology", "Semiconductors"),
    "MU": ("Technology", "Semiconductors"),
    "AVGO": ("Technology", "Semiconductors"),
    "QCOM": ("Technology", "Semiconductors"),
    "AMAT": ("Technology", "Semiconductor Equipment"),
    "LRCX": ("Technology", "Semiconductor Equipment"),
    "KLAC": ("Technology", "Semiconductor Equipment"),
    "MCHP": ("Technology", "Semiconductors"),
    "ON": ("Technology", "Semiconductors"),
    "STX": ("Technology", "Technology Hardware"),
    "WDC": ("Technology", "Technology Hardware"),
    "HPE": ("Technology", "Technology Hardware"),

    # Software
    "MSFT": ("Technology", "Systems Software"),
    "ORCL": ("Technology", "Application Software"),
    "ADBE": ("Technology", "Application Software"),
    "CRM": ("Technology", "Application Software"),
    "NOW": ("Technology", "Application Software"),
    "INTU": ("Technology", "Application Software"),
    "CDNS": ("Technology", "Application Software"),
    "SNPS": ("Technology", "Application Software"),
    "WDAY": ("Technology", "Application Software"),

    # Cybersecurity
    "PANW": ("Technology", "Cybersecurity"),
    "CRWD": ("Technology", "Cybersecurity"),
    "FTNT": ("Technology", "Cybersecurity"),

    # Cloud / SaaS
    "DDOG": ("Technology", "Cloud Software"),
    "TEAM": ("Technology", "Cloud Software"),
    "OKTA": ("Technology", "Cloud Software"),

    # Consumer Tech / Internet
    "AAPL": ("Technology", "Technology Hardware"),
    "META": ("Communication Services", "Interactive Media"),
    "GOOGL": ("Communication Services", "Interactive Media"),
    "GOOG": ("Communication Services", "Interactive Media"),
    "AMZN": ("Consumer Discretionary", "Internet Retail"),
    "NFLX": ("Communication Services", "Entertainment"),
    "TSLA": ("Consumer Discretionary", "Automobiles"),

    # Financials
    "JPM": ("Financials", "Diversified Banks"),
    "BAC": ("Financials", "Diversified Banks"),
    "GS": ("Financials", "Investment Banking"),
    "MS": ("Financials", "Investment Banking"),
    "V": ("Financials", "Payment Processing"),
    "MA": ("Financials", "Payment Processing"),
    "AXP": ("Financials", "Consumer Finance"),
    "SPGI": ("Financials", "Financial Exchanges"),
    "MCO": ("Financials", "Financial Exchanges"),

    # Healthcare — Managed Care
    "UNH": ("Healthcare", "Managed Care"),
    "HUM": ("Healthcare", "Managed Care"),
    "ELV": ("Healthcare", "Managed Care"),
    "CI": ("Healthcare", "Managed Care"),
    "MOH": ("Healthcare", "Managed Care"),
    "CNC": ("Healthcare", "Managed Care"),

    # Healthcare — Pharmaceuticals
    "LLY": ("Healthcare", "Pharmaceuticals"),
    "MRK": ("Healthcare", "Pharmaceuticals"),
    "PFE": ("Healthcare", "Pharmaceuticals"),
    "ABBV": ("Healthcare", "Pharmaceuticals"),
    "BMY": ("Healthcare", "Pharmaceuticals"),
    "JNJ": ("Healthcare", "Pharmaceuticals"),

    # Healthcare — Biotech
    "AMGN": ("Healthcare", "Biotechnology"),
    "GILD": ("Healthcare", "Biotechnology"),
    "REGN": ("Healthcare", "Biotechnology"),
    "VRTX": ("Healthcare", "Biotechnology"),
    "BIIB": ("Healthcare", "Biotechnology"),
    "MRNA": ("Healthcare", "Biotechnology"),

    # Healthcare — Medical Devices
    "MDT": ("Healthcare", "Medical Devices"),
    "ABT": ("Healthcare", "Medical Devices"),
    "ISRG": ("Healthcare", "Medical Devices"),
    "BSX": ("Healthcare", "Medical Devices"),
    "EW": ("Healthcare", "Medical Devices"),
    "TMO": ("Healthcare", "Life Sciences Tools"),
    "DHR": ("Healthcare", "Life Sciences Tools"),

    # Energy
    "XOM": ("Energy", "Integrated Oil & Gas"),
    "CVX": ("Energy", "Integrated Oil & Gas"),
    "COP": ("Energy", "E&P"),
    "EOG": ("Energy", "E&P"),
    "DVN": ("Energy", "E&P"),
    "OXY": ("Energy", "E&P"),

    # Industrials
    "CAT": ("Industrials", "Construction Machinery"),
    "DE": ("Industrials", "Agricultural Machinery"),
    "HON": ("Industrials", "Industrial Conglomerates"),
    "GE": ("Industrials", "Industrial Conglomerates"),
    "RTX": ("Industrials", "Aerospace & Defense"),
    "LMT": ("Industrials", "Aerospace & Defense"),
    "NOC": ("Industrials", "Aerospace & Defense"),
    "GD": ("Industrials", "Aerospace & Defense"),

    # Consumer Discretionary
    "AMZN": ("Consumer Discretionary", "Internet Retail"),
    "HD": ("Consumer Discretionary", "Home Improvement Retail"),
    "LOW": ("Consumer Discretionary", "Home Improvement Retail"),
    "MCD": ("Consumer Discretionary", "Restaurants"),
    "SBUX": ("Consumer Discretionary", "Restaurants"),
    "NKE": ("Consumer Discretionary", "Footwear"),
    "TJX": ("Consumer Discretionary", "Apparel Retail"),

    # Communication Services
    "GOOGL": ("Communication Services", "Interactive Media"),
    "META": ("Communication Services", "Interactive Media"),
    "NFLX": ("Communication Services", "Entertainment"),
    "CMCSA": ("Communication Services", "Cable & Satellite"),
    "T": ("Communication Services", "Integrated Telecom"),
    "VZ": ("Communication Services", "Integrated Telecom"),
    "TMUS": ("Communication Services", "Wireless Telecom"),

    # Utilities
    "NEE": ("Utilities", "Electric Utilities"),
    "DUK": ("Utilities", "Electric Utilities"),
    "SO": ("Utilities", "Electric Utilities"),

    # Real Estate
    "PLD": ("Real Estate", "Industrial REITs"),
    "AMT": ("Real Estate", "Tower REITs"),
    "EQIX": ("Real Estate", "Data Center REITs"),
}


def get_sector_info(ticker: str) -> tuple:
    """
    Returns (sector, sub_industry) for a ticker.
    Returns ("Other", "Other") if not in map.
    """
    return SECTOR_SUBINDUSTRY_MAP.get(ticker, ("Other", "Other"))


def detect_sector_overlaps(candidates: list) -> dict:
    """
    Detect sub-industry overlaps among candidates.
    Returns dict: {ticker: overlapping_ticker or None}
    """
    sub_industry_seen = {}
    overlaps = {}

    for c in candidates:
        ticker = c["ticker"]
        _, sub_industry = get_sector_info(ticker)

        if sub_industry == "Other":
            overlaps[ticker] = None
            continue

        if sub_industry in sub_industry_seen:
            # Both tickers have overlap
            existing = sub_industry_seen[sub_industry]
            overlaps[ticker] = existing
            overlaps[existing] = ticker
        else:
            sub_industry_seen[sub_industry] = ticker
            overlaps[ticker] = None

    return overlaps
