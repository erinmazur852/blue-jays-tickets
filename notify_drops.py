#!/usr/bin/env python3
"""Compare the two most recent snapshots and push a price-drop digest to ntfy.

Sends one notification per run, only when something dropped:
- any game whose overall lowest price went down
- any game that got listings for the first time
- section drops of 5%+ (so a cheap pair appearing in the 100s gets flagged
  even if it doesn't move the game's overall low)

Drops are detected on the raw USD price so FX moves can't fake a drop;
amounts are reported in CAD at that snapshot's BoC rate.

Env: NTFY_TOPIC (required) — the ntfy.sh topic to publish to.
"""
import csv
import os
import sys
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY = os.path.join(DIR, "price_history.csv")
SECTION_HISTORY = os.path.join(DIR, "section_history.csv")
SECTION_DROP_PCT = 5  # ignore smaller section wiggles


def last_two_runs(path, key_fields):
    """{key: row} for the latest and previous checked_at in the file."""
    if not os.path.exists(path):
        return {}, {}
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    stamps = sorted({r["checked_at"] for r in rows})
    if not stamps:
        return {}, {}
    latest = {tuple(r[k] for k in key_fields): r
              for r in rows if r["checked_at"] == stamps[-1]}
    prev = {}
    if len(stamps) > 1:
        prev = {tuple(r[k] for k in key_fields): r
                for r in rows if r["checked_at"] == stamps[-2]}
    return latest, prev


def cad(row):
    return int(row["min_total_cents"]) * float(row["usd_cad_rate"]) / 100


def main():
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        raise SystemExit("NTFY_TOPIC not set")

    latest, prev = last_two_runs(HISTORY, ["event_id"])
    if not prev:
        print("first snapshot, nothing to compare")
        return

    lines = []
    for key, new in sorted(latest.items(),
                           key=lambda kv: (kv[1]["game_date"], kv[1]["game_time"])):
        old = prev.get(key)
        if not old:
            continue
        n, o = int(new["min_total_cents"]), int(old["min_total_cents"])
        label = f"{new['opponent']} {new['game_date']}"
        if o > 0 and 0 < n < o:
            lines.append(f"▼ {label}: ${cad(old):.0f} → ${cad(new):.0f} CAD")
        elif o == 0 and n > 0:
            lines.append(f"new listings: {label} from ${cad(new):.0f} CAD")

    sec_latest, sec_prev = last_two_runs(SECTION_HISTORY,
                                         ["event_id", "section_group"])
    game_meta = {k[0]: v for k, v in latest.items()}
    sec_lines = []
    for key, new in sec_latest.items():
        old = sec_prev.get(key)
        if not old:
            continue
        n, o = int(new["min_total_cents"]), int(old["min_total_cents"])
        if o > 0 and 0 < n < o and (o - n) / o * 100 >= SECTION_DROP_PCT:
            meta = game_meta.get(key[0])
            label = (f"{meta['opponent']} {meta['game_date']}" if meta else key[0])
            sec_lines.append((o - n,
                f"▼ {key[1]} · {label}: ${cad(old):.0f} → ${cad(new):.0f} CAD"))
    # biggest section drops first, cap the list so the push stays readable
    sec_lines.sort(reverse=True)
    if sec_lines:
        lines.append("— sections —")
        lines.extend(l for _, l in sec_lines[:10])
        if len(sec_lines) > 10:
            lines.append(f"…and {len(sec_lines) - 10} more section drops")

    if not lines:
        print("no drops this run")
        return

    body = "\n".join(lines).encode()
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}", data=body,
        headers={"Title": "SeatDip: Jays price drops",
                 "Tags": "baseball,chart_with_downwards_trend",
                 "Priority": "default"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()
    print(f"sent {len(lines)} lines to ntfy/{topic}")


if __name__ == "__main__":
    main()
