# V4 System Configuration
# All thresholds, parameters, and watchlists in one place
# Edit this file to tune the system — changes propagate everywhere

# =============================================================
# INDUSTRY ETF WATCHLIST — 25 Investable Industries
# These are the industries the intelligence engine scans daily
# =============================================================

INDUSTRY_ETF_MAP = {
    "Semiconductors":        {"etf": "SOXX", "sector": "Technology"},
    "Software":              {"etf": "IGV",  "sector": "Technology"},
    "Cybersecurity":         {"etf": "CIBR", "sector": "Technology"},
    "AI Infrastructure":     {"etf": "BOTZ", "sector": "Technology"},
    "Cloud Computing":       {"etf": "SKYY", "sector": "Technology"},
    "Networking":            {"etf": "FIVG",  "sector": "Technology"},
    "Biotech":               {"etf": "IBB",  "sector": "Healthcare"},
    "Medical Devices":       {"etf": "IHI",  "sector": "Healthcare"},
    "Managed Care":          {"etf": "IHF",  "sector": "Healthcare"},
    "Pharmaceuticals":       {"etf": "XPH",  "sector": "Healthcare"},
    "Defense & Aerospace":   {"etf": "ITA",  "sector": "Industrials"},
    "Energy Transition":     {"etf": "ICLN", "sector": "Energy"},
    "Oil & Gas":             {"etf": "XOP",  "sector": "Energy"},
    "Financials":            {"etf": "XLF",  "sector": "Financials"},
    "Regional Banks":        {"etf": "KRE",  "sector": "Financials"},
    "Investment Banking":    {"etf": "KCE",  "sector": "Financials"},
    "Consumer Discretionary":{"etf": "XLY",  "sector": "Consumer"},
    "Industrial Automation": {"etf": "ROBO", "sector": "Industrials"},
    "Logistics & Transport": {"etf": "IYT",  "sector": "Industrials"},
    "Homebuilders":          {"etf": "XHB",  "sector": "Real Estate"},
    "REITs":                 {"etf": "VNQ",  "sector": "Real Estate"},
    "Commodities":           {"etf": "DJP",  "sector": "Materials"},
    "Clean Energy":          {"etf": "PBW",  "sector": "Energy"},
    "Nuclear Energy":        {"etf": "NLR",  "sector": "Energy"},
    "Emerging Markets":      {"etf": "EEM",  "sector": "International"},
}

# ETF tickers list for price fetching
ALL_INDUSTRY_ETFS = [v["etf"] for v in INDUSTRY_ETF_MAP.values()]

# Stock leaders per industry — Layer 2 security selection
# These are the individual stocks the system evaluates within each winning industry
INDUSTRY_STOCK_LEADERS = {
    "Semiconductors":        ["NVDA", "AMD", "MU", "AVGO", "TSM", "INTC", "QCOM", "MRVL", "KLAC", "AMAT", "LRCX", "TXN", "ASML", "NXPI", "STM"],
    "Software":              ["MSFT", "CRM", "NOW", "ADBE", "ORCL", "AAPL", "SAP", "WDAY", "TEAM", "ZM", "DDOG", "MDB", "GTLB", "HUBS", "BILL"],
    "Cybersecurity":         ["CRWD", "PANW", "ZS", "FTNT", "S", "CYBR", "OKTA", "RPD", "TENB", "QLYS", "VRNT", "SAIL", "CHKP", "AKAM", "FEYE"],
    "AI Infrastructure":     ["NVDA", "MSFT", "GOOGL", "AMZN", "META", "AMD", "ORCL", "IBM", "SMCI", "ARM", "CRWV", "PLTR", "AI", "IONQ", "RGTI"],
    "Cloud Computing":       ["AMZN", "MSFT", "GOOGL", "NET", "SNOW", "DDOG", "ESTC", "FSLY", "FIVN", "TWLO", "ZI", "BOX", "DOCN", "WK", "APPN"],
    "Networking":            ["CSCO", "ANET", "JNPR", "CIEN", "INFN", "VIAV", "NTGR", "CALX", "COMM", "RBBN", "AAOI", "LITE", "IIVI", "COHR", "FNSR"],
    "Biotech":               ["AMGN", "GILD", "REGN", "VRTX", "MRNA", "BIIB", "ILMN", "EXAS", "SGEN", "ALNY", "BMRN", "IONS", "FOLD", "RARE", "ACAD"],
    "Medical Devices":       ["ABT", "MDT", "ISRG", "SYK", "BSX", "EW", "ZBH", "BAX", "BDX", "TFX", "HOLX", "DXCM", "PODD", "INSP", "NARI"],
    "Managed Care":          ["UNH", "CVS", "HUM", "CI", "MOH", "CNC", "ELV", "OSCR", "HCI", "CLOV", "ACGL", "AFL", "MET", "PRU", "AIG"],
    "Pharmaceuticals":       ["LLY", "JNJ", "PFE", "MRK", "ABBV", "BMY", "AZN", "NVO", "RHHBY", "GSK", "SNY", "TAK", "VTRS", "OGN", "PRGO"],
    "Defense & Aerospace":   ["LMT", "RTX", "NOC", "GD", "HII", "BA", "TDG", "KTOS", "CACI", "LDOS", "SAIC", "DRS", "BWXT", "AXON", "ACHR"],
    "Energy Transition":     ["ENPH", "FSLR", "SEDG", "NEE", "PLUG", "RUN", "ARRY", "NOVA", "SHLS", "STEM", "BE", "BLDP", "FCEL", "CSIQ", "JKS"],
    "Oil & Gas":             ["XOM", "CVX", "COP", "SLB", "EOG", "PXD", "OXY", "DVN", "MPC", "VLO", "PSX", "HES", "APA", "FANG", "HAL"],
    "Financials":            ["JPM", "BAC", "GS", "MS", "V", "MA", "AXP", "BLK", "SCHW", "COF", "DFS", "SYF", "ALLY", "SOFI", "NDAQ"],
    "Regional Banks":        ["WFC", "USB", "PNC", "TFC", "MTB", "CFG", "HBAN", "RF", "KEY", "FITB", "CMA", "SNV", "UMBF", "BOKF", "EWBC"],
    "Investment Banking":    ["GS", "MS", "BX", "KKR", "APO", "CG", "BAM", "ARES", "TPG", "HLNE", "LAZ", "EVR", "PJT", "HLI", "MC"],
    "Consumer Discretionary":["AMZN", "TSLA", "HD", "NKE", "SBUX", "MCD", "TGT", "BKNG", "ABNB", "LVS", "MGM", "DRI", "YUM", "CMG", "DKNG"],
    "Industrial Automation": ["ROK", "HON", "EMR", "PH", "AME", "ROP", "ITW", "GE", "ETN", "DOV", "FTV", "NDSN", "TTC", "MIDD", "FELE"],
    "Logistics & Transport": ["UPS", "FDX", "UBER", "XPO", "ODFL", "SAIA", "CHRW", "EXPD", "ZTO", "JBHT", "HTLD", "WERN", "ARCB", "MRTN", "GXO"],
    "Homebuilders":          ["DHI", "LEN", "NVR", "PHM", "TOL", "MDC", "KBH", "MHO", "CCS", "TMHC", "TPH", "LGIH", "GRBK", "SKY", "CVA"],
    "REITs":                 ["AMT", "PLD", "EQIX", "SPG", "O", "VICI", "WELL", "DLR", "PSA", "EXR", "AVB", "EQR", "UDR", "CPT", "MAA"],
    "Commodities":           ["FCX", "NEM", "GOLD", "AEM", "WPM", "AGI", "KGC", "HL", "CDE", "PAAS", "CLF", "STLD", "NUE", "RS", "CMC"],
    "Clean Energy":          ["ENPH", "FSLR", "NEE", "CEG", "VST", "AES", "D", "SO", "DUK", "XEL", "CWEN", "RNW", "SPWR", "MAXN", "IREN"],
    "Nuclear Energy":        ["CEG", "VST", "CCJ", "LEU", "NNE", "SMR", "BWXT", "DNN", "UEC", "URG", "UUUU", "OKLO", "NANO", "LTBR", "GEV"],
    "Emerging Markets":      ["TSM", "BABA", "SE", "MELI", "PDD", "BIDU", "JD", "NIO", "LI", "XPEV", "GRAB", "GOTO", "GLOB", "VTEX", "DESP"],
}

# All individual stocks to fetch prices for
ALL_STOCKS = list(set(s for stocks in INDUSTRY_STOCK_LEADERS.values() for s in stocks))

# Benchmark
BENCHMARK_ETF = "SPY"

# =============================================================
# CONVICTION SCORE FORMULA
# Each component scores 0-25, total 0-100
# =============================================================

CONVICTION_WEIGHTS = {
    "industry_momentum":    25,  # ETF relative strength vs SPY
    "earnings_revision":    25,  # Aggregate earnings trend within industry
    "event_catalyst":       25,  # Quality and recency of confirming events
    "macro_alignment":      25,  # Whether macro conditions favor this industry
}

# Thresholds
CONVICTION_HIGH =    75   # High conviction — recommend entry (raised from 70)
CONVICTION_MEDIUM =  40   # Medium conviction — monitor closely (lowered from 45)
CONVICTION_LOW =      0   # Below this — no recommendation, hold cash

# Maximum industries to surface in daily briefing
MAX_INDUSTRIES_BRIEFING = 4

# =============================================================
# INDUSTRY MOMENTUM PARAMETERS
# =============================================================

MOMENTUM_LOOKBACK_DAYS = 63       # 63-day relative strength vs SPY
MOMENTUM_SHORT_LOOKBACK = 21      # 21-day for recent trend confirmation
LAYER1_TOP_N = 10                 # Layer 1 narrows to top N industries
MIN_OUTPERFORMANCE_PCT = 2.0      # Minimum outperformance vs SPY to qualify

# =============================================================
# PORTFOLIO RULES — mirrors Investor One-Pager
# =============================================================

MAX_POSITION_SIZE_PCT = 0.15      # Never exceed 15% in single position
MAX_SHORT_TERM_ALLOCATION = 0.30  # Short-term catalyst holdings max 30%
PORTFOLIO_MIN_POSITIONS = 8       # Guideline minimum
PORTFOLIO_MAX_POSITIONS = 20      # Guideline maximum

# Loss thresholds
POSITION_REVIEW_LOSS_PCT = 0.10   # Mandatory review at 10% loss
POSITION_EXIT_LOSS_PCT =   0.15   # Strong exit signal at 15% loss
PORTFOLIO_DRAWDOWN_PAUSE = 0.15   # Pause new positions at 15% drawdown
PORTFOLIO_DRAWDOWN_HALT =  0.20   # Full reassessment at 20% drawdown

# =============================================================
# SCHEDULE
# =============================================================

MORNING_RUN_TIME = "08:45"        # ET
AFTERNOON_RUN_TIME = "14:45"      # ET
BRIEFING_DEADLINE = "09:20"       # ET — must deliver before this

# =============================================================
# DATA SOURCES
# =============================================================

NEWS_MAX_HEADLINES = 50           # Headlines to fetch per morning run
NEWS_LOOKBACK_HOURS = 20          # Hours of news to pull
EARNINGS_LOOKBACK_QUARTERS = 6    # Quarters of earnings history

# =============================================================
# TELEGRAM
# =============================================================

TELEGRAM_MORNING_MAX_CHARS = 4000   # Telegram message limit
TELEGRAM_SUMMARY_MAX_LINES = 20     # Keep morning summary concise
