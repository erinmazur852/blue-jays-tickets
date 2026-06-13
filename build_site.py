#!/usr/bin/env python3
"""Generate the static SeatDip site from site_data.json into ./site.

One index, one page per team, one page per game, plus sitemap.xml and
robots.txt. Pages are plain pre-rendered HTML so search engines index them
directly — that's the whole point of the SEO surface.
"""
import html
import json
import os
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

DIR = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(DIR, "site")
BASE_URL = os.environ.get("SEATDIP_BASE_URL", "https://seatdip.vercel.app")
ET = ZoneInfo("America/New_York")
MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def e(s):
    return html.escape(str(s), quote=True)


def money(cents, cur):
    return f"${cents/100:,.0f} {cur}" if cents else None


def fmt_dt(iso):
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET)
    return dt, f"{DOW[dt.weekday()]} {MONTHS[dt.month]} {dt.day}, {dt.year}", \
        dt.strftime("%-I:%M %p ET")


def buy_url(g):
    """Marketplace deep link. Swap to affiliate-tracked links post-approval —
    this is the single place to change."""
    import urllib.parse
    q = urllib.parse.quote_plus(f"{g['away_name']} at {g['home_name']}")
    return f"https://www.vividseats.com/search?searchTerm={q}"


SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canonical}">
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
{schema}
<style>
  :root{{--navy:#134a8e;--green:#0c8a3e;--bg:#f5f7fa;--card:#fff;--text:#1a2233;--muted:#6b7585}}
  *{{box-sizing:border-box}}
  body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);line-height:1.5}}
  a{{color:var(--navy);text-decoration:none}}
  a:hover{{text-decoration:underline}}
  header{{background:var(--navy);color:#fff;padding:14px 20px}}
  header a{{color:#fff}}
  header .brand{{font-weight:800;font-size:18px}}
  header .brand b{{color:#4ade80}}
  .wrap{{max-width:1000px;margin:0 auto;padding:20px}}
  h1{{font-size:24px;margin:.2em 0}}
  h2{{font-size:17px;margin-top:28px}}
  .sub{{color:var(--muted);font-size:14px}}
  .crumb{{font-size:13px;color:var(--muted);margin-bottom:6px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;margin-top:14px}}
  .card{{background:var(--card);border:1px solid #e6eaf0;border-radius:10px;padding:12px 14px;display:block}}
  .card .t{{font-weight:600}}
  .card .m{{color:var(--muted);font-size:13px}}
  table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden;border:1px solid #e6eaf0;margin-top:12px}}
  th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);padding:9px 12px;background:#fafbfd;border-bottom:2px solid #e6eaf0}}
  td{{padding:9px 12px;border-bottom:1px solid #eef1f5;font-size:14px}}
  tr:last-child td{{border-bottom:none}}
  .price{{font-weight:700}}
  .deal{{display:inline-block;background:var(--green);color:#fff;font-size:11px;padding:2px 7px;border-radius:5px}}
  .cta{{display:inline-block;background:#e8291c;color:#fff;padding:10px 18px;border-radius:8px;font-weight:700;margin-top:8px}}
  .cta:hover{{text-decoration:none;filter:brightness(1.08)}}
  .box{{background:var(--card);border:1px solid #e6eaf0;border-radius:10px;padding:16px;margin-top:14px}}
  footer{{max-width:1000px;margin:30px auto;padding:0 20px;color:var(--muted);font-size:12px}}
</style>
</head>
<body>
<header><div class="wrap" style="padding:0"><a href="/" class="brand">Seat<b>Dip</b></a></div></header>
<div class="wrap">
{body}
</div>
<footer>
<a href="/">Home</a> · <a href="/about.html">About</a> · <a href="/privacy.html">Privacy</a><br>
SeatDip is an independent fan project, not affiliated with MLB or any team or marketplace. Buy links may be affiliate links. Prices shown are indicative and set by the marketplace at checkout.
</footer>
</body>
</html>
"""


def write(path, content):
    full = os.path.join(SITE, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


def page(path, title, desc, body, schema=""):
    canonical = f"{BASE_URL}/{path}".replace("/index.html", "/")
    write(path, SHELL.format(title=e(title), desc=e(desc), canonical=e(canonical),
                             schema=schema, body=body))


def build(data):
    if os.path.isdir(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE)
    for asset in ("icon.svg", "logo.svg", "about.html", "privacy.html",
                  "data.js", "data.json"):
        src = os.path.join(DIR, asset)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(SITE, asset))
    # the rich section-level Jays tracker ships at /jays.html
    jays_src = os.path.join(DIR, "index.html")
    if os.path.exists(jays_src):
        shutil.copy(jays_src, os.path.join(SITE, "jays.html"))

    teams = data["teams"]
    games = data["games"]
    by_team = {}
    for g in games:
        by_team.setdefault(g["home_slug"], []).append(g)

    # ---- home / index ----
    cards = "".join(
        f'<a class="card" href="/team/{e(t["slug"])}/">'
        f'<div class="t">{e(t["name"])}</div>'
        f'<div class="m">{len(by_team.get(t["slug"], []))} home games · {e(t["venue"])}</div></a>'
        for t in teams)
    body = f"""<h1>MLB ticket prices &amp; price history</h1>
<p class="sub">Track the lowest resale price for every MLB home game, see whether
today's price is a real deal against its own history, and get to the cheapest
listing fast. Pick your team.</p>
<div class="box">🔥 <b>Blue Jays fans:</b> try the
<a href="/jays.html">section-by-section live price tracker</a> — every Rogers
Centre section, price-drop history, and your own target alerts.</div>
<div class="grid">{cards}</div>"""
    page("index.html", "SeatDip — MLB Ticket Prices & Price History by Team",
         "Compare ticket prices and price history for every MLB team's home games. "
         "See if today's price is a deal and find the cheapest seats by section.",
         body)

    # ---- team pages ----
    for t in teams:
        tg = sorted(by_team.get(t["slug"], []), key=lambda g: g["date"])
        rows = []
        for g in tg:
            _, datestr, timestr = fmt_dt(g["datetime_utc"])
            price = money(g["min_cents"], g["currency"])
            deal = '<span class="deal">tracked low</span>' if (
                g["min_cents"] and g["tracked_low"] and g["min_cents"] <= g["tracked_low"]) else ""
            rows.append(
                f'<tr><td><a href="/game/{g["game_pk"]}/">{e(g["away_name"])}</a></td>'
                f'<td>{datestr}<br><span class="sub">{timestr}</span></td>'
                f'<td class="price">{price or "—"} {deal}</td></tr>')
        table = ("<table><thead><tr><th>Opponent</th><th>Date</th>"
                 "<th>From</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
                 ) if rows else "<p>No upcoming home games.</p>"
        jays_promo = ('<div class="box">🔥 Try the '
                      '<a href="/jays.html">section-by-section live tracker</a> '
                      'for every Rogers Centre section, with price-drop history '
                      'and target-price alerts.</div>') if t["slug"] == "toronto-blue-jays" else ""
        body = f"""<div class="crumb"><a href="/">MLB</a> › {e(t["name"])}</div>
<h1>{e(t["name"])} tickets</h1>
<p class="sub">{len(tg)} upcoming home games at {e(t["venue"])}, {e(t["location"])}.
Lowest prices and price history below — click a game for detail and the
cheapest listing.</p>
{jays_promo}
{table}"""
        page(f"team/{t['slug']}/index.html",
             f"{t['name']} Tickets 2026 — Prices, Schedule & Price History | SeatDip",
             f"Cheap {t['name']} tickets: compare prices and price history for every "
             f"home game at {t['venue']}. See if today's price is a deal.",
             body)

    # ---- game pages ----
    for g in games:
        dt, datestr, timestr = fmt_dt(g["datetime_utc"])
        home = next((t for t in teams if t["slug"] == g["home_slug"]), None)
        title_m = f"{g['away_name']} at {g['home_name']}"
        price = money(g["min_cents"], g["currency"])
        deal = (g["min_cents"] and g["tracked_low"]
                and g["min_cents"] <= g["tracked_low"])
        price_block = (
            f'<p class="price" style="font-size:22px">From {price}'
            + (' <span class="deal">lowest we\'ve tracked</span>' if deal else '')
            + '</p>') if price else (
            '<p class="sub">Live price tracking for this game is starting. '
            'Check back, or grab the current listing below.</p>')
        offers = (f',"offers":{{"@type":"AggregateOffer","lowPrice":'
                  f'{g["min_cents"]/100:.2f},"priceCurrency":"{g["currency"]}",'
                  f'"availability":"https://schema.org/InStock",'
                  f'"url":"{buy_url(g)}"}}') if g["min_cents"] else ""
        schema = ('<script type="application/ld+json">'
                  f'{{"@context":"https://schema.org","@type":"SportsEvent",'
                  f'"name":"{e(title_m)}","startDate":"{g["datetime_utc"]}",'
                  f'"eventStatus":"https://schema.org/EventScheduled",'
                  f'"location":{{"@type":"Place","name":"{e(g["venue"])}"}},'
                  f'"homeTeam":{{"@type":"SportsTeam","name":"{e(g["home_name"])}"}},'
                  f'"awayTeam":{{"@type":"SportsTeam","name":"{e(g["away_name"])}"}}'
                  f'{offers}}}</script>')
        body = f"""<div class="crumb"><a href="/">MLB</a> ›
<a href="/team/{e(g["home_slug"])}/">{e(g["home_name"])}</a> › {e(g["away_name"])}</div>
<h1>{e(title_m)} tickets</h1>
<p class="sub">{datestr} · {timestr} · {e(g["venue"])}</p>
<div class="box">
{price_block}
<a class="cta" href="{e(buy_url(g))}" target="_blank" rel="nofollow sponsored">Find tickets</a>
<p class="sub" style="margin-top:10px">We check this game's resale price regularly and
keep the history so you can tell a real dip from a fake one. {g["checks"]} checks so far.</p>
</div>
<p style="margin-top:18px"><a href="/team/{e(g["home_slug"])}/">← all {e(g["home_name"])} home games</a></p>"""
        page(f"game/{g['game_pk']}/index.html",
             f"{title_m} Tickets — {datestr} | SeatDip",
             f"{title_m} tickets {datestr} at {g['venue']}. "
             f"{'From ' + price + '. ' if price else ''}Price history and the cheapest listing.",
             body, schema)

    # ---- sitemap + robots ----
    urls = [f"{BASE_URL}/"]
    urls += [f"{BASE_URL}/team/{t['slug']}/" for t in teams]
    urls += [f"{BASE_URL}/game/{g['game_pk']}/" for g in games]
    sm = ('<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"<url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    write("sitemap.xml", sm)
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")

    print(f"built {len(urls)} pages → {SITE}")


if __name__ == "__main__":
    with open(os.path.join(DIR, "site_data.json")) as f:
        build(json.load(f))
