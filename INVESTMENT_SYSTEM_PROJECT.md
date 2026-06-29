# Investment System — Project Intelligence Document
**Owner:** Aidan Stylarek
**GitHub:** https://github.com/aidansty/investment-system
**Dashboard:** https://aidansty.github.io/investment-system/dashboard.html
**Last updated:** June 28, 2026

---

## THE MISSION

Beat the S&P 500. Grow active stock market capital from $6,750 toward $8,000, then $9,000, then $10,000 and beyond as fast as possible while maintaining disciplined risk management.

---

## CAPITAL STRUCTURE

**Anchor (never touch):**
- SPY permanent hold (~55-60% of active capital)
- Crypto BTC, ETH, ZEC, XRP on Coinbase — NOT counted in active sleeve

**Active Sleeve (~$1,700-$2,800):**
- Maximum 4 concentrated positions
- Rules engine manages all entry/exit decisions here
- Taxable account on Webull — short-term gains taxed at ordinary income rate

---

## CURRENT PORTFOLIO

| Ticker | Term | Entry | Entry Date | Status |
|--------|------|-------|------------|--------|
| SPY | Long-term | $659.44 | 2026-04-14 | Permanent anchor |
| NVDA | Long-term | $205.33 | 2026-04-14 | Hold — AI infrastructure thesis |
| SPCX | Long-term | $183.84 | 2026-04-14 | Hold through index inclusion |
| AMD | Medium-term | $453.74 | 2026-04-14 | Hold — semiconductors thesis |
| MU | Medium-term | $599.21 | 2026-04-14 | WATCH — earnings just reported |
| CRWV | Medium-term | $116.60 | 2026-05-01 | WATCH — down 18%, no catalyst yet |
| INTC | Medium-term | $137.18 | 2026-05-01 | WATCH — Apple partnership |
| HUM | Short-term | $357.37 | 2026-05-15 | WATCH — earnings July 29 |
| SCO | Short-term | $33.09 | 2026-06-10 | WATCH — leveraged ETF max 21 days |
| NOK | Medium-term | $14.11 | 2026-05-01 | Hold — 5G thesis |
| BTC | Long-term | $59,767 | 2026-04-14 | Permanent crypto hold |
| ETH | Long-term | $2,010 | 2026-04-14 | Permanent crypto hold |
| ZEC | Long-term | $482 | 2026-04-14 | Permanent crypto hold |
| XRP | Long-term | $1.18 | 2026-04-14 | Permanent crypto hold |

**Closed:** PLTR (June 2026), UFO (June 23 2026)

---

## V2 RULES ENGINE

File: v4/intelligence/rules_engine.py

### Constants
- MIN_CONVICTION_FULL_ENTRY = 75
- MIN_CONVICTION_HOLD = 40
- MAX_ACTIVE_POSITIONS = 4
- THESIS_BREAK_DAYS = 10
- PORTFOLIO_FLOOR = 0.125 (12.5% max drawdown)
- PERMANENT_HOLDS = {SPY, BTC, ETH, XRP, ZEC}

### Position Sizing (proven by backtest)
- Conviction 88-100: 25% of active sleeve
- Conviction 80-87: 20% of active sleeve
- Conviction 75-79: 15% of active sleeve

### Entry Rules (ALL must be met)
1. Conviction >= 75
2. Industry outperforming SPY over 63 days
3. Regime score >= 40
4. Confirmed catalyst (or conviction >= 85 for reduced entry)
5. Cash above 12% minimum
6. Positions < 4

### Exit Rules
FAST (immediate): thesis-breaking news, what_to_do says CLOSE, leveraged ETF day 21
SLOW (10 consecutive days below conviction 40): conviction drift, industry out of Layer 1

---

## TWO-LAYER INDUSTRY SCANNER

File: v4/intelligence/industry_scanner.py

Layer 1: 25 industry ETFs vs SPY 63-day momentum
Layer 2: 357 individual stocks scored within winning industries
Multi-timeframe: 63-day sustained + 21-day breakout detection
Recommends stock if scores 5+ points above ETF, otherwise ETF

Stock universe: v4/config/settings.py INDUSTRY_STOCK_LEADERS
15 stocks per industry, 25 industries, 357 total stocks

---

## 7-COMPONENT CONVICTION SCORING

| Component | Weight |
|-----------|--------|
| Momentum vs SPY 63-day | 25% |
| Earnings revision direction | 20% |
| Revenue growth | 15% |
| FCF strength | 15% |
| Macro alignment | 10% |
| Event catalyst quality | 10% |
| Earnings surprise history | 5% |

Momentum + earnings revisions capped combined at 38% to prevent double-counting.

---

## CLAUDE'S ROLE (CRITICAL)

Claude is the EXPLANATION layer only. The rules engine decides.
Claude receives rules engine output and explains why signals fired.
Claude NEVER overrides quantitative signals with narrative.

---

## BACKTEST RESULTS (June 28, 2026)

| Period | Strategy | SPY | Alpha |
|--------|----------|-----|-------|
| 2020-2025 | +34.2% | +149.6% | -115% |
| 2022 bear | -8.1% | -15.2% | +7% |
| 2023-2024 | +112.3% | +47.4% | +65% |

2020-2025 underperformance caused by historically unique COVID-stimulus rally unlikely to repeat.
2022-2024 is most representative of current market conditions.

---

## MORNING PIPELINE STEPS (v4_morning.py)

1. Market calendar check
2. Fetch ETF prices (25 industries)
3. Fetch stock prices (357 stocks)
4. Fetch macro (composite regime score)
5. Fetch news (filtered + enriched)
6. Fetch earnings calendar (Finnhub confirmed dates)
7. Fetch quant fundamentals
8. Run industry scanner (Layer 1 + Layer 2)
9. Run rules engine (entry/exit signals with sizing)
10. Generate briefing (Claude explains rules engine output)
11. Record performance vs SPY
12. Write dashboard_data.js
13. Send 2 Telegram messages

---

## AFTERNOON PIPELINE (v4_afternoon.py)

Thesis monitoring ONLY — no new trade recommendations.
Checks each holding for thesis-breaking developments.
Generates exit signal if thesis breaks, confirms intact if not.

---

## DASHBOARD TABS

1. Portfolio — live prices, regime score, dual scoreboard, kill criteria banner
2. Morning Briefing — rules engine signals + Claude explanations
3. Afternoon Update — thesis monitoring results
4. Backtest — validation guide
5. Manage Positions — add/close positions via GitHub API (requires ghp_ token in localStorage)
6. Ask the Desk — Claude chat

Dual scoreboard: My Stocks vs SPY + Total Portfolio vs SPY
Shows Beating/Trailing SPY by X% in clear language.

---

## API CREDENTIALS

| Service | Key |
|---------|-----|
| Telegram Bot Token | 8992325083:AAGw24aLKwkLRPQUCOZg8Jnf_hQxcdgCkX0 |
| Telegram Chat ID | 7737587549 |
| Finnhub | d8fo751r01qn443av1rgd8fo751r01qn443av1s0 |

GitHub Secrets: ANTHROPIC_API_KEY, FINNHUB_KEY, FRED_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

---

## HOW TO CONTINUE DEVELOPMENT

1. Read this document first
2. Check GitHub Actions logs for latest run errors
3. Run: python -c "import sys; sys.path.insert(0,'.'); import v4_morning, v4_afternoon; print('clean')"
4. Always push to main branch
5. Never change conviction weights without 100+ resolved trades

## PENDING ITEMS

1. Monitor Monday 8:45 AM run — first full V2 run
2. Rules engine exit signals need conviction_score from actual scan (currently defaults to 50)
3. Afternoon pipeline rules_output not yet passed to dashboard_writer
4. After 30+ trades: analyze win tracker component attribution
5. After 100+ trades: first conviction weight update
6. Research vs production environment separation
