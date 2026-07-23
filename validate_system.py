#!/usr/bin/env python3
"""Pre-push validation. Run: python3 validate_system.py before every push."""
import sys, os, json, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
failures = []

print("=" * 55)
print("SYSTEM VALIDATION")
print("=" * 55)

for mod in ["v4_morning", "v4_afternoon"]:
    try:
        __import__(mod)
        print(f"  [PASS] import {mod}")
    except Exception as e:
        failures.append(f"import {mod}: {e}")
        print(f"  [FAIL] import {mod}: {e}")

try:
    from v4.output.dashboard_writer import write_dashboard_data
    with open("v4/config/positions.json") as f:
        positions = json.load(f)["positions"]
    for p in positions:
        p["current_price"] = (p.get("entry_price", 100) or 100) * 1.05
    stock_tickers = [p["ticker"] for p in positions if p["ticker"] not in ("BTC","ETH","XRP","ZEC","SOL","SPY")]

    briefing_text = "## Position Review\n\n" + "\n".join(
        f"{tk} \u2014 HOLD\n- **Today's news impact:** Test news for {tk}\n- **Catalyst status:** Test catalyst\n- **What to do and WHY:** Hold \u2014 validation test reasoning for {tk}\n"
        for tk in stock_tickers)
    sections = {"Position Review": briefing_text.split("## Position Review\n")[1]}

    if os.path.exists("dashboard_data.js"):
        shutil.copy("dashboard_data.js", "/tmp/dashboard_data_backup.js")

    for run_type in ("morning", "afternoon"):
        write_dashboard_data(
            macro={"vix": 18.0, "vix_regime": "Yellow", "vix_trend": "Flat", "spy_daily_change": 0.5},
            industry_results={"top_industries": [], "layer2": [], "high_conviction": [], "layer1": []},
            news_package={"recent_news": [], "forward_catalysts": []},
            positions=positions,
            briefing={"raw_text": briefing_text, "sections": sections} if run_type == "morning" else {"raw_text": "", "sections": {}},
            run_type=run_type,
            today="2099-01-01",
            rules_output={"exit_signals": [], "entry_signals": [], "regime": "Yellow", "regime_score": 58},
            catalyst_opportunities=[],
        )
        with open("dashboard_data.js") as f:
            out = json.loads(f.read().replace("window.BRIEFING_DATA = ", "").rstrip(";"))
        prs = out.get("position_review", [])
        if run_type == "morning":
            missing = set(stock_tickers) - {pr.get("ticker") for pr in prs}
            if missing:
                failures.append(f"morning: positions missing from review: {missing}")
                print(f"  [FAIL] morning write: missing {missing}")
            else:
                stale = [pr["ticker"] for pr in prs if "validation test reasoning" not in (pr.get("what_to_do") or "")]
                if stale:
                    failures.append(f"morning: Claude text NOT used for: {stale}")
                    print(f"  [FAIL] morning: Claude fresh text ignored for {stale}")
                else:
                    print(f"  [PASS] morning write: all {len(stock_tickers)} stocks use fresh Claude text")
        else:
            print(f"  [PASS] afternoon write: no crash, {len(prs)} reviews preserved")

    if os.path.exists("/tmp/dashboard_data_backup.js"):
        shutil.copy("/tmp/dashboard_data_backup.js", "dashboard_data.js")
        print("  [OK] dashboard_data.js restored")
except Exception as e:
    failures.append(f"writer dry run: {e}")
    print(f"  [FAIL] writer CRASH: {e}")
    import traceback; traceback.print_exc()

print("=" * 55)
if failures:
    print(f"RESULT: {len(failures)} FAILURE(S) \u2014 DO NOT PUSH:")
    for f in failures:
        print(f"  X {f}")
    sys.exit(1)
print("RESULT: ALL CHECKS PASSED \u2014 safe to push")
