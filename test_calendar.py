import requests
import os
from datetime import date, timedelta

key = os.environ.get("FINNHUB_KEY", "")
today = date.today()
end = today + timedelta(days=60)

print("Test 1: No symbol — should return full market calendar")
url = f"https://finnhub.io/api/v1/calendar/earnings?from={today}&to={end}&token={key}"
r = requests.get(url, timeout=15)
data = r.json()
calendar = data.get("earningsCalendar", [])
print(f"Status: {r.status_code}")
print(f"Total events returned: {len(calendar)}")
if calendar:
    print(f"Sample tickers: {[e['symbol'] for e in calendar[:10]]}")

print()
print("Test 2: With symbol=AAPL — should return only AAPL")
url2 = f"https://finnhub.io/api/v1/calendar/earnings?from={today}&to={end}&symbol=AAPL&token={key}"
r2 = requests.get(url2, timeout=15)
data2 = r2.json()
calendar2 = data2.get("earningsCalendar", [])
print(f"Status: {r2.status_code}")
print(f"Events for AAPL: {len(calendar2)}")
if calendar2:
    print(f"Data: {calendar2}")

print()
print("Test 3: Check if our universe tickers appear in global calendar")
universe_sample = ["NVDA", "MSFT", "META", "AMZN", "GOOGL"]
symbols_in_calendar = [e['symbol'] for e in calendar]
for ticker in universe_sample:
    found = ticker in symbols_in_calendar
    print(f"  {ticker}: {'found' if found else 'NOT found'} in calendar")
