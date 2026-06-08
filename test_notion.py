import os
from datetime import date
from notion_client import Client
from output.notion import write_trade_candidates, get_notion_client

print("=== Testing Notion Output ===\n")

# Test 1: Connection
notion = get_notion_client()
print("Connection: OK")

# Test 2: Write a test candidate
test_candidates = [
    {
        "ticker": "TEST",
        "tier": "Strong",
        "composite_score": 0.850,
        "rs_score": 45.2,
        "beat_streak": 4,
        "earnings_score": 1.0,
        "catalyst_score": 1.0,
        "has_catalyst": True,
        "days_to_catalyst": 12,
        "catalyst_date": "2026-06-16"
    }
]

write_trade_candidates(test_candidates, date.today())
print("Test candidate written to Notion")
print("\nCheck your Notion Trade Candidates database — you should see TEST")
print("URL: https://app.notion.com/p/376a00e00e2581489cfbcf6f54d45dc5")
