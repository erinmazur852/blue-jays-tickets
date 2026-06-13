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
GAMETIME = "https://mobile.gametime.co/v1"
VENUES_FILE = os.path.join(DIR, "gametime_venues.json")
SEASON = 2026

# Gametime prices every venue in USD; the public site shows USD.
PRICE_FIELDS = ["checked_at", "game_pk", "home_slug", "date",
                "min_cents", "prefee_cents", "currency", "source"]


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


# ---- Gametime resale price layer ------------------------------------------

def gametime_prices(venue_id, team_name):
    """{date -> (min_total_cents, min_prefee_cents, buy_url)} for a team's
    home games, from that stadium's Gametime venue feed (USD)."""
    url = f"{GAMETIME}/events?venue_id={venue_id}&per_page=100"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                data = json.load(r)
            break
        except Exception:
            time.sleep(1.5 + attempt)
    else:
        return {}
    last = team_name.split()[-1]
    prices = {}
    for item in data.get("events", []):
        ev = item.get("event", item)
        name = str(ev.get("name", ""))
        if "Parking" in name or not name.endswith(f"at {team_name}") and last not in name:
            continue
        if " at " not in name:
            continue
        date = (ev.get("datetime_local") or "")[:10]
        mp = ev.get("min_price") or {}
        total = mp.get("total") or 0
        if not date or total <= 0:
            continue
        prices[date] = (total, mp.get("prefee") or 0, ev.get("seo_url", ""))
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
    venues = json.load(open(VENUES_FILE)) if os.path.exists(VENUES_FILE) else {}

    # gather Gametime prices per home venue (one call per team with games left)
    home_team_ids = {g["home_id"] for g in games}
    team_prices = {}
    for tid in home_team_ids:
        t = tm[tid]
        vid = (venues.get(t["slug"]) or {}).get("venue_id")
        if not vid:
            team_prices[tid] = {}
            continue
        try:
            team_prices[tid] = gametime_prices(vid, t["name"])
        except Exception:
            team_prices[tid] = {}
        time.sleep(0.3)

    new_rows = []
    for g in games:
        home = tm[g["home_id"]]
        p = team_prices.get(g["home_id"], {}).get(g["date"])
        g["home_slug"] = home["slug"]
        g["home_name"] = home["name"]
        g["currency"] = "USD"
        if p:
            g["min_cents"], g["prefee_cents"], g["buy_url"] = p
            new_rows.append({
                "checked_at": checked_at, "game_pk": g["game_pk"],
                "home_slug": home["slug"], "date": g["date"],
                "min_cents": p[0], "prefee_cents": p[1],
                "currency": "USD", "source": "gametime"})
        else:
            g["min_cents"] = g["prefee_cents"] = 0
            g["buy_url"] = ""
        # deal signal vs our own tracked low
        past = [int(r["min_cents"]) for r in prior.get(str(g["game_pk"]), [])
                if int(r["min_cents"]) > 0]
        g["tracked_low"] = min(past) if past else 0
        g["checks"] = len(past) + (1 if p else 0)

    if new_rows:
        append_history(new_rows)

    out = {
        "generated_at": checked_at,
        "has_prices": True,
        "teams": sorted(
            (t for t in tm.values() if t["id"] in home_team_ids),
            key=lambda t: t["name"]),
        "games": sorted(games, key=lambda g: (g["date"], g["home_slug"])),
    }
    with open(SITE_DATA, "w") as f:
        json.dump(out, f)

    priced = sum(1 for g in games if g["min_cents"])
    print(f"{checked_at}  {len(out['teams'])} teams, {len(games)} games, "
          f"{priced} priced via Gametime")


if __name__ == "__main__":
    main()
