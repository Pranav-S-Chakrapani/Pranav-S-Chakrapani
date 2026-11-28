#!/usr/bin/env python3
"""
Pulls the last 371 days of contribution counts for GITHUB_LOGIN from the
GitHub GraphQL API and writes them to data/contributions.json.

Needs a token in GH_TOKEN (or GITHUB_TOKEN) with at least `read:user` scope
-- the default Actions GITHUB_TOKEN cannot read another user's contribution
calendar, so the workflow uses a Personal Access Token stored as a repo
secret (see .github/workflows/update-cards.yml).
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def fetch(login: str, token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-card-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    login = os.environ.get("GITHUB_LOGIN", "Pranav-S-Chakrapani")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "contributions.json")

    if not token:
        print("No GH_TOKEN / GITHUB_TOKEN in env -- skipping live fetch.", file=sys.stderr)
        return 1

    data = fetch(login, token)
    if "errors" in data:
        print(f"GraphQL errors: {data['errors']}", file=sys.stderr)
        return 1

    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = []
    for week in weeks:
        for day in week["contributionDays"]:
            days.append({"date": day["date"], "count": day["contributionCount"]})
    days.sort(key=lambda d: d["date"])

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "login": login,
        "days": days,
    }

    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"Wrote {len(days)} days to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
