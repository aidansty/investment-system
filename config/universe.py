# S&P 500 + Nasdaq 100 combined universe
# Version 1.2 - live yfinance audit June 2026
# Removed: ANSS(acquired), CDAY/DAY(renamed), DFS(acquired), CTLT(acquired)
#          HES(acquired), K(acquired), JNPR(acquired), MRO(acquired), WBA(private)
# Fixed: FI -> FISV
# Next quarterly review: September 2026

SP500_TICKERS = [
    "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD","ABNB",
    "AKAM","ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG","MO","AMZN",
    "AMCR","AEE","AAL","AEP","AXP","AIG","AMT","AWK","AMP","AME","AMGN","APH",
    "ADI","AON","APA","AAPL","AMAT","APTV","ACGL","ADM","ANET","AJG",
    "AIZ","T","ATO","ADSK","ADP","AZO","AVB","AVY","AXON","BKR","BALL","BAC",
    "BK","BBWI","BAX","BDX","BRK-B","BBY","BIO","TECH","BIIB","BLK","BX","BA",
    "BSX","BMY","AVGO","BR","BRO","BF-B","BLDR","BG","CDNS","CZR","CPT",
    "CPB","COF","CAH","KMX","CCL","CARR","CAT","CBOE","CBRE","CDW","CE",
    "COR","CNC","CNX","CF","CRL","SCHW","CHTR","CVX","CMG","CB","CHD",
    "CI","CINF","CTAS","CSCO","C","CFG","CLX","CME","CMS","KO","CTSH","CL",
    "CMCSA","CMA","CAG","COP","ED","STZ","CEG","COO","CPRT","GLW","CPAY","CTVA",
    "CSGP","COST","CTRA","CCI","CSX","CMI","CVS","DHI","DHR","DRI","DVA",
    "DECK","DE","DAL","DVN","DXCM","FANG","DLR","DG","DLTR","D","DPZ",
    "DOV","DOW","DTE","DUK","DD","EMN","ETN","EBAY","ECL","EIX","EW",
    "EA","ELV","LLY","EMR","ENPH","ETR","EOG","EPAM","EQT","EFX","EQIX","EQR",
    "ESS","EL","ETSY","EG","EVRG","ES","EXC","EXPE","EXPD","EXR","XOM","FFIV",
    "FDS","FICO","FAST","FRT","FDX","FIS","FITB","FSLR","FE","FISV","FMC","F",
    "FTNT","FTV","FOXA","FOX","BEN","FCX","GRMN","IT","GE","GEHC","GEV","GEN",
    "GNRC","GD","GIS","GM","GPC","GILD","GPN","GL","GDDY","GS","HAL","HIG",
    "HAS","HCA","DOC","HSIC","HSY","HPE","HLT","HOLX","HD","HON","HRL",
    "HST","HWM","HPQ","HUBB","HUM","HBAN","HII","IBM","IEX","IDXX","ITW","INCY",
    "IR","PODD","INTC","ICE","IFF","IP","IPG","INTU","ISRG","IVZ","INVH","IQV",
    "IRM","JBHT","JBL","JKHY","J","JNJ","JCI","JPM","KVUE","KDP",
    "KEY","KEYS","KMB","KIM","KMI","KLAC","KHC","KR","LHX","LH","LRCX","LW",
    "LVS","LDOS","LEN","LII","LIN","LYV","LKQ","LMT","L","LOW","LULU","LYB",
    "MTB","MPC","MKTX","MAR","MMC","MLM","MAS","MA","MTCH","MKC","MCD",
    "MCK","MDT","MRK","META","MET","MTD","MGM","MCHP","MU","MSFT","MAA","MRNA",
    "MHK","MOH","TAP","MDLZ","MPWR","MNST","MCO","MS","MOS","MSI","MSCI","NDAQ",
    "NTAP","NOC","NFLX","NEM","NWSA","NWS","NEE","NKE","NI","NDSN","NSC","NTRS",
    "NRG","NUE","NVDA","NVR","NXPI","ORLY","OXY","ODFL","OMC","ON","OKE",
    "ORCL","OTIS","OGN","PCAR","PKG","PANW","PH","PAYX","PAYC","PYPL",
    "PNR","PEP","PFE","PCG","PM","PSX","PNW","PNC","POOL","PPG","PPL",
    "PFG","PG","PGR","PLD","PRU","PEG","PTC","PSA","PHM","PWR",
    "QCOM","DGX","RL","RJF","RTX","O","REG","REGN","RF","RSG","RMD","RVTY",
    "ROK","ROL","ROP","ROST","RCL","SPGI","CRM","SBAC","SLB","STX","SRE","NOW",
    "SHW","SPG","SWKS","SJM","SNA","SOLV","SO","LUV","SWK","SBUX","STT","STLD",
    "STE","SYK","SMCI","SYF","SNPS","SYY","TMUS","TROW","TTWO","TPR","TGT",
    "TEL","TDY","TFX","TER","TSLA","TXN","TXT","TMO","TJX","TSCO","TT","TDG",
    "TRV","TRMB","TFC","TYL","TSN","USB","UBER","UDR","ULTA","UNP","UAL","UPS",
    "URI","UNH","UHS","VLO","VTR","VRSN","VRSK","VZ","VRTX","VFC","VTRS","VICI",
    "V","VMC","WRB","GWW","WAB","WMT","DIS","WBD","WM","WAT","WEC","WFC",
    "WELL","WST","WDC","WY","WMB","WTW","WYNN","XEL","XYL","YUM","ZBRA","ZBH","ZTS"
]

NASDAQ100_TICKERS = [
    "ADBE","ADI","ADP","ADSK","AEP","ALGN","AMAT","AMD","AMGN","AMZN",
    "AAPL","ASML","AVGO","BIIB","BKNG","CDNS","CDW","CHTR","CMCSA","COST",
    "CPRT","CRWD","CSCO","CSX","CTAS","CTSH","DDOG","DLTR","DXCM","EA","EBAY",
    "ENPH","EXC","FANG","FAST","FTNT","GILD","GOOGL","GOOG","HON","IDXX",
    "INTC","INTU","ISRG","KDP","KHC","KLAC","LRCX","LULU","MAR",
    "MCHP","MDLZ","MELI","META","MNST","MRNA","MSFT","MU","NFLX","NVDA","NXPI",
    "ODFL","OKTA","ON","ORLY","PANW","PAYX","PCAR","PDD","PEP","PYPL","QCOM",
    "REGN","ROST","SBUX","SNPS","TEAM","TMUS","TSLA","TXN",
    "VRSK","VRTX","WDAY","XEL","ZM","ZS"
]

EXTENDED_TICKERS = ["SPY"]


def get_universe() -> list:
    """
    Returns deduplicated active scanning universe.
    Version 1.2 - audited June 2026
    To expand: add tickers to EXTENDED_TICKERS only.
    Next quarterly review: September 2026
    """
    combined = set(SP500_TICKERS + NASDAQ100_TICKERS + EXTENDED_TICKERS)
    return sorted(list(combined))


def get_universe_metadata() -> dict:
    combined = get_universe()
    return {
        "total": len(combined),
        "sp500": len(SP500_TICKERS),
        "nasdaq100": len(NASDAQ100_TICKERS),
        "extended": len(EXTENDED_TICKERS),
        "version": "1.2",
        "last_audit": "2026-06-03",
        "next_review": "2026-09-01"
    }
