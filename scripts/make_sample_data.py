#!/usr/bin/env python3
"""One-off helper: writes data/contributions.json with plausible fake data
so generate_cards.py can be run and screenshotted before the real Action
has run once. Not used in CI -- fetch_contributions.py replaces this file
with real data there.
"""
import json
import os
import random
from datetime import datetime, timedelta, timezone

random.seed(7)

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "contributions.json")

today = datetime.now(timezone.utc).date()
days = []
streak_break_at = random.randint(0, 3)  # days ago a streak might have broken
for i in range(370, -1, -1):
    d = today - timedelta(days=i)
    weekday = d.weekday()
    base = 1 if weekday < 5 else 0.4
    count = max(0, int(random.gauss(base * 3, 2.2)))
    if i <= 11 and i != streak_break_at:
        count = max(count, random.randint(1, 6))
    days.append({"date": d.isoformat(), "count": count})

data = {
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "login": "Pranav-S-Chakrapani",
    "days": days,
}

with open(OUT, "w") as f:
    json.dump(data, f, indent=2)

print(f"Wrote sample data: {OUT}")
