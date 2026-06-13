#!/usr/bin/env python3
"""Build the SeatDip data layer for all 30 MLB teams.

Schedule + teams: MLB Stats API (no key).
Prices: Ticketmaster Discovery API (set TM_API_KEY) — optional. When the key
is absent, pages still generate from the schedule and prices fill in later.
Resale enrichment for the Jays stays in the separate fetch_prices.py (local).

Writes:
  site_data.json          — everything build_site.py needs
  mlb_price_history.csv    — one row per (game, run) that had a TM price
"""
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DATA = os.path.join(DIR, "site_data.json")
PRICE_HISTORY = os.path.join(DIR, "mlb_price_history.csv")

STATS = "https://statsapi.mlb.com/api/v1"
TM = "https://app.ticketmaster.com/discovery/v2"
TM_KEY = os.environ.get("TM_API_KEY", "").strip()
SEASON = 2026
TZ_FALLBACK = "America/New_York"

PRICE_FIELDS = ["checked_at", "game_pk", "home_slug", "date",
                "min_cents", "max_cents", "currency", "source"]


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SeatDip/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def teams():
    data = get_json(f"{STATS}/teams?sportId=1&season={SEASON}")
    out = {}
    for t in data["teams"]:
        if t.get("sport", {}).get("id") != 1 or not t.get("active"):
            continue
        out[t["id"]] = {
            "id": t["id"],
            "name": t["name"],
            "slug": slugify(t["name"]),
            "abbrev": t.get("abbreviation", ""),
            "location": t.get("locationName", ""),
            "venue": t.get("venue", {}).get("name", ""),
            "league": t.get("league", {}).get("name", ""),
            "division": t.get("division", {}).get("name", ""),
        }
    return out


def schedule(today):
    """All remaining regular-season games, home games attached to each team."""
    url = (f"{STATS}/schedule?sportId=1&season={SEASON}&gameType=R"
           f"&startDate={today}&endDate={SEASON}-11-15&hydrate=venue")
    data = get_json(url)
    games = []
    for date in data.get("dates", []):
        for g in date["games"]:
            if g.get("status", {}).get("abstractGameState") == "Final":
                continue
            home = g["teams"]["home"]["team"]
            away = g["teams"]["away"]["team"]
            games.append({
                "game_pk": g["gamePk"],
                "date": date["date"],
                "datetime_utc": g["gameDate"],
                "home_id": home["id"],
                "away_id": away["id"],
                "away_name": away["name"],
                "venue": g.get("venue", {}).get("name", ""),
            })
    return games


# ---- Ticketmaster price enrichment (optional) -----------------------------

def tm_get(path, **params):
    params["apikey"] = TM_KEY
    url = f"{TM}/{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(3):
        try:
            return get_json(url)
        except Exception:
            time.sleep(2 + attempt)
    return {}


def tm_prices_for_team(team):
    """{date -> (min_cents, max_cents, currency)} for the team's home games."""
    if not TM_KEY:
        return {}
    res = tm_get("attractions.json", keyword=team["name"],
                 classificationName="baseball", size=5)
    attractions = (res.get("_embedded") or {}).get("attractions") or []
    aid = next((a["id"] for a in attractions
                if slugify(a["name"]) == team["slug"]
                or team["name"].endswith(a["name"])), None)
    if not aid:
        return {}
    prices = {}
    page = 0
    while True:
        ev = tm_get("events.json", attractionId=aid,
                    classificationName="baseball", size=100, page=page,
                    sort="date,asc")
        events = (ev.get("_embedded") or {}).get("events") or []
        for e in events:
            name = e.get("name", "")
            # home games only: "<Away> at <Home>" ending in our team
            if " at " not in name or not name.endswith(team["name"].split()[-1]):
                continue
            date = (e.get("dates", {}).get("start", {}) or {}).get("localDate")
            ranges = e.get("priceRanges") or []
            if not date or not ranges:
                continue
            lo = min(r.get("min", 0) for r in ranges if r.get("min"))
            hi = max(r.get("max", 0) for r in ranges if r.get("max"))
            cur = ranges[0].get("currency", "USD")
            if lo:
                prices[date] = (round(lo * 100), round(hi * 100), cur)
        page_info = ev.get("page", {})
        if page + 1 >= page_info.get("totalPages", 1):
            break
        page += 1
        time.sleep(0.25)
    return prices


def append_history(rows):
    new = not os.path.exists(PRICE_HISTORY)
    with open(PRICE_HISTORY, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PRICE_FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def load_history():
    """{game_pk: [rows...]} from prior runs, for deal signals."""
    hist = {}
    if not os.path.exists(PRICE_HISTORY):
        return hist
    with open(PRICE_HISTORY, newline="") as f:
        for r in csv.DictReader(f):
            hist.setdefault(r["game_pk"], []).append(r)
    return hist


def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone().strftime("%Y-%m-%d")
    checked_at = now.astimezone().isoformat(timespec="seconds")

    tm = teams()
    games = schedule(today)
    prior = load_history()

    # gather TM prices per team (only the teams that have home games left)
    team_prices = {}
    home_team_ids = {g["home_id"] for g in games}
    if TM_KEY:
        for tid in home_team_ids:
            try:
                team_prices[tid] = tm_prices_for_team(tm[tid])
            except Exception:
                team_prices[tid] = {}
            time.sleep(0.25)

    new_rows = []
    for g in games:
        home = tm[g["home_id"]]
        p = team_prices.get(g["home_id"], {}).get(g["date"])
        g["home_slug"] = home["slug"]
        g["home_name"] = home["name"]
        if p:
            g["min_cents"], g["max_cents"], g["currency"] = p
            new_rows.append({
                "checked_at": checked_at, "game_pk": g["game_pk"],
                "home_slug": home["slug"], "date": g["date"],
                "min_cents": p[0], "max_cents": p[1],
                "currency": p[2], "source": "ticketmaster"})
        else:
            g["min_cents"] = g["max_cents"] = 0
            g["currency"] = "USD"
        # deal signal vs our own tracked low
        past = [int(r["min_cents"]) for r in prior.get(str(g["game_pk"]), [])
                if int(r["min_cents"]) > 0]
        g["tracked_low"] = min(past) if past else 0
        g["checks"] = len(past) + (1 if p else 0)

    if new_rows:
        append_history(new_rows)

    out = {
        "generated_at": checked_at,
        "has_prices": bool(TM_KEY),
        "teams": sorted(
            (t for t in tm.values() if t["id"] in home_team_ids),
            key=lambda t: t["name"]),
        "games": sorted(games, key=lambda g: (g["date"], g["home_slug"])),
    }
    with open(SITE_DATA, "w") as f:
        json.dump(out, f)

    priced = sum(1 for g in games if g["min_cents"])
    print(f"{checked_at}  {len(out['teams'])} teams, {len(games)} games, "
          f"{priced} priced (TM key: {'yes' if TM_KEY else 'NO — schedule only'})")


if __name__ == "__main__":
    main()
