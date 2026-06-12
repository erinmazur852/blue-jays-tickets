#!/usr/bin/env python3
"""Snapshot current lowest resale prices for Blue Jays home games.

Master game list comes from the official MLB schedule (statsapi.mlb.com).
Prices come from Gametime's public venue feed for Rogers Centre.
Games with no Gametime listings yet show price 0 and fill in automatically
on later runs once inventory appears.

Run it any time: python3 fetch_prices.py
Each run appends one row per game to price_history.csv and regenerates data.js
for tracker.html. No dependencies beyond the standard library.
"""
import csv
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY = os.path.join(DIR, "price_history.csv")
SECTION_HISTORY = os.path.join(DIR, "section_history.csv")
DATA_JS = os.path.join(DIR, "data.js")

JAYS_TEAM_ID = 141
ROGERS_CENTRE_VENUE_ID = "55116f6864f9625eb3000001"  # gametime venue id
MLB_URL = (f"https://statsapi.mlb.com/api/v1/schedule?sportId=1"
           f"&teamId={JAYS_TEAM_ID}&season=2026&gameType=R")
GT_URL = (f"https://mobile.gametime.co/v1/events"
          f"?venue_id={ROGERS_CENTRE_VENUE_ID}&per_page=100")
# Gametime prices Rogers Centre in USD; convert with the official BoC rate
BOC_URL = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=1"

FIELDS = ["checked_at", "event_id", "game_date", "game_time", "opponent",
          "min_total_cents", "min_prefee_cents", "usd_cad_rate", "buy_url"]
SECTION_FIELDS = ["checked_at", "event_id", "section_group", "min_total_cents",
                  "min_prefee_cents", "listings", "usd_cad_rate", "buy_url"]


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def mlb_home_games():
    """Remaining (not Final) Jays home games, in Toronto local time."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Toronto")
    games = []
    for date in get_json(MLB_URL).get("dates", []):
        for g in date["games"]:
            if g["teams"]["home"]["team"]["id"] != JAYS_TEAM_ID:
                continue
            if g["status"]["abstractGameState"] == "Final":
                continue
            local = datetime.fromisoformat(
                g["gameDate"].replace("Z", "+00:00")).astimezone(tz)
            games.append({
                "event_id": str(g["gamePk"]),  # stable id, keys targets in the UI
                "game_date": local.strftime("%Y-%m-%d"),
                "game_time": local.strftime("%H:%M"),
                "opponent": g["teams"]["away"]["team"]["name"],
            })
    games.sort(key=lambda g: (g["game_date"], g["game_time"]))
    return games


def gametime_prices():
    """{(date, opponent): {price fields}} for Jays home games with listings."""
    prices = {}
    for item in get_json(GT_URL).get("events", []):
        ev = item.get("event", item)
        name = str(ev.get("name", ""))
        if not name.endswith("at Toronto Blue Jays") or "Parking" in name:
            continue
        dt = ev.get("datetime_local", "")
        mp = ev.get("min_price") or {}
        prices[(dt[:10], name.replace(" at Toronto Blue Jays", ""))] = {
            "min_total_cents": mp.get("total") or 0,
            "min_prefee_cents": mp.get("prefee") or 0,
            "buy_url": ev.get("seo_url", ""),
        }
    return prices


def fetch_sections(event_page_url):
    """Min price per section group, parsed from the listings embedded in a
    Gametime event page (window.__data)."""
    req = urllib.request.Request(event_page_url,
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    start = html.find("window.__data=")
    if start < 0:
        return {}
    blob = re.sub(r'([,\[:])undefined', r'\1null',
                  html[start + len("window.__data="):])
    try:
        data, _ = json.JSONDecoder().raw_decode(blob)
    except json.JSONDecodeError:
        return {}
    listings = ((data.get("redux") or {}).get("listings") or {}).get("listings") or []
    groups = {}
    for l in listings:
        group = (l.get("spot") or {}).get("sectionGroup") or "Other"
        price = l.get("price") or {}
        total = price.get("total") or 0
        if total <= 0:
            continue
        g = groups.setdefault(group, {"min_total_cents": total,
                                      "min_prefee_cents": price.get("prefee") or 0,
                                      "buy_url": l.get("seoUrl") or "",
                                      "listings": 0})
        g["listings"] += 1
        if total < g["min_total_cents"]:
            g.update(min_total_cents=total,
                     min_prefee_cents=price.get("prefee") or 0,
                     buy_url=l.get("seoUrl") or "")
    return groups


def usd_cad_rate():
    """Today's BoC USD/CAD rate; falls back to the last stored rate."""
    try:
        obs = get_json(BOC_URL)["observations"][-1]
        return float(obs["FXUSDCAD"]["v"])
    except Exception:
        if os.path.exists(HISTORY):
            with open(HISTORY, newline="") as f:
                rows = list(csv.DictReader(f))
            if rows and rows[-1].get("usd_cad_rate"):
                return float(rows[-1]["usd_cad_rate"])
        raise SystemExit("could not fetch USD/CAD rate and no cached rate exists")


def read_csv(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            for k in ("min_total_cents", "min_prefee_cents", "listings"):
                if k in row:
                    row[k] = int(row[k] or 0)
            rows.append(row)
    return rows


def write_data_js():
    history = read_csv(HISTORY)
    sections = read_csv(SECTION_HISTORY)
    with open(DATA_JS, "w") as f:
        f.write("// generated by fetch_prices.py — do not edit\n")
        f.write("const PRICE_HISTORY = ")
        json.dump(history, f)
        f.write(";\nconst SECTION_HISTORY = ")
        json.dump(sections, f)
        f.write(";\n")
    with open(os.path.join(DIR, "data.json"), "w") as f:
        json.dump({"price_history": history, "section_history": sections}, f)


def main():
    checked_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    games = mlb_home_games()
    if not games:
        raise SystemExit("MLB schedule returned no remaining home games")
    prices = gametime_prices()
    rate = usd_cad_rate()

    unlisted = []
    for g in games:
        p = prices.get((g["game_date"], g["opponent"]))
        if p:
            g.update(p)
        else:
            g.update({"min_total_cents": 0, "min_prefee_cents": 0, "buy_url": ""})
            unlisted.append(g)

    new_file = not os.path.exists(HISTORY)
    with open(HISTORY, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for g in games:
            w.writerow({"checked_at": checked_at, "usd_cad_rate": rate, **g})

    priced = [g for g in games if g["min_total_cents"]]

    if "--no-sections" not in sys.argv:
        new_sec = not os.path.exists(SECTION_HISTORY)
        with open(SECTION_HISTORY, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SECTION_FIELDS)
            if new_sec:
                w.writeheader()
            for i, g in enumerate(priced, 1):
                try:
                    groups = fetch_sections(g["buy_url"])
                except Exception:
                    time.sleep(3)
                    try:
                        groups = fetch_sections(g["buy_url"])
                    except Exception as e:
                        print(f"  sections failed for {g['game_date']} "
                              f"{g['opponent']}: {e}", file=sys.stderr)
                        continue
                for name, s in sorted(groups.items()):
                    w.writerow({"checked_at": checked_at, "event_id": g["event_id"],
                                "section_group": name, "usd_cad_rate": rate, **s})
                print(f"  [{i}/{len(priced)}] {g['game_date']} {g['opponent']}: "
                      f"{len(groups)} section groups", flush=True)
                time.sleep(0.4)

    write_data_js()
    cheapest = min(priced, key=lambda g: g["min_total_cents"])
    print(f"{checked_at}  snapshotted {len(games)} games "
          f"({len(priced)} with listings) at USD/CAD {rate}")
    print(f"cheapest right now: ${cheapest['min_total_cents']/100*rate:.2f} CAD total "
          f"({cheapest['opponent']} on {cheapest['game_date']})")
    if unlisted:
        print(f"no listings yet: " +
              ", ".join(f"{g['game_date']} {g['opponent']}" for g in unlisted))


if __name__ == "__main__":
    main()
