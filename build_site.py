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


MARK_SVG = ('<svg viewBox="0 0 64 64" fill="none"><polyline points="8,16 24,34 32,26 44,38 56,10" '
            'stroke="#0a1f3c" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>'
            '<circle cx="44" cy="38" r="5" fill="#fff" stroke="#0a1f3c" stroke-width="4"/></svg>')

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
<meta name="theme-color" content="#0a1f3c">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&display=swap">
<link rel="stylesheet" href="/seatdip.css">
{schema}
</head>
<body>
<header class="site-header"><div class="inner">
  <a href="/" class="brand"><span class="mark">{mark}</span>Seat<b>Dip</b>
  <span class="tag">ticket price tracker</span></a>
</div></header>
<div class="wrap">
{body}
</div>
<footer class="site-footer">
<a href="/">Home</a> · <a href="/about.html">About</a> · <a href="/privacy.html">Privacy</a><br>
SeatDip is an independent fan project, not affiliated with MLB or any team or marketplace. Buy links may be affiliate links. Prices shown are indicative and set by the marketplace at checkout.
</footer>
<script>
/* reveal-on-scroll, progressive enhancement only */
(function(){{var els=document.querySelectorAll('.reveal');if(!('IntersectionObserver'in window)){{els.forEach(function(e){{e.classList.add('in')}});return}}
var io=new IntersectionObserver(function(es){{es.forEach(function(en){{if(en.isIntersecting){{en.target.classList.add('in');io.unobserve(en.target)}}}})}},{{rootMargin:'0px 0px -8% 0px'}});
els.forEach(function(e){{io.observe(e)}});}})();
</script>
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
                             schema=schema, body=body, mark=MARK_SVG))


def build(data):
    if os.path.isdir(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE)
    for asset in ("icon.svg", "logo.svg", "about.html", "privacy.html",
                  "data.js", "data.json"):
        src = os.path.join(DIR, asset)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(SITE, asset))
    css = os.path.join(DIR, "assets", "seatdip.css")
    if os.path.exists(css):
        shutil.copy(css, os.path.join(SITE, "seatdip.css"))
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
        f'<a class="team-card reveal" href="/team/{e(t["slug"])}/">'
        f'<div class="name">{e(t["name"])}</div>'
        f'<div class="meta">{len(by_team.get(t["slug"], []))} home games · {e(t["venue"])}</div>'
        f'<span class="div">{e(t["division"])}</span></a>'
        for t in teams)
    ticker = ('<svg class="ticker" viewBox="0 0 200 80" fill="none">'
              '<path d="M4,30 L40,52 L70,40 L110,64 L150,20 L196,8" stroke="#5cf2a0" '
              'stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>'
              '<circle cx="110" cy="64" r="5.5" fill="#fff"/></svg>')
    body = f"""<div class="hero">
  <h1>Catch the <span class="pop">dip</span>.<br>MLB ticket prices, tracked.</h1>
  <p>We watch the lowest price for every MLB home game and keep its history, so
  you can tell a real deal from a fake one — then jump straight to the cheapest seats.</p>
  {ticker}
</div>
<div class="box promo reveal">🔥 <b>Blue Jays fans:</b> try the
<a href="/jays.html">section-by-section live price tracker</a> — every Rogers
Centre section, price-drop history, and your own target alerts.</div>
<div class="section-title">Pick your team</div>
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
            deal = '<span class="badge deal">▼ tracked low</span>' if (
                g["min_cents"] and g["tracked_low"] and g["min_cents"] <= g["tracked_low"]) else ""
            pcell = (f'<span class="price">{price}</span> {deal}'
                     if price else '<span class="price none">tracking…</span>')
            rows.append(
                f'<tr><td class="opp"><a href="/game/{g["game_pk"]}/">{e(g["away_name"])}</a></td>'
                f'<td>{datestr}<br><span style="color:var(--muted);font-size:12px">{timestr}</span></td>'
                f'<td>{pcell}</td></tr>')
        table = ('<div class="table-wrap"><table><thead><tr><th>Opponent</th>'
                 '<th>Date</th><th>From</th></tr></thead><tbody>'
                 + "".join(rows) + "</tbody></table></div>"
                 ) if rows else "<p>No upcoming home games.</p>"
        jays_promo = ('<div class="box promo reveal">🔥 Try the '
                      '<a href="/jays.html">section-by-section live tracker</a> '
                      'for every Rogers Centre section, with price-drop history '
                      'and target-price alerts.</div>') if t["slug"] == "toronto-blue-jays" else ""
        body = f"""<div class="crumb"><a href="/">MLB</a> › {e(t["name"])}</div>
<h1>{e(t["name"])} tickets</h1>
<p style="color:var(--muted);max-width:640px">{len(tg)} upcoming home games at {e(t["venue"])}, {e(t["location"])}.
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
        cur = g["currency"]
        if price:
            amt = f"{g['min_cents']/100:,.0f}"
            price_block = (
                f'<div class="price-hero">${amt}<span class="cur"> {cur} from</span></div>'
                + ('<div style="margin-top:10px"><span class="badge deal">▼ lowest we\'ve tracked</span></div>'
                   if deal else ''))
        else:
            price_block = ('<div class="price-hero" style="font-size:26px">Tracking…</div>'
                           '<p class="price-sub">We\'re pulling live prices for this game. '
                           'Check back soon, or grab the current listing below.</p>')
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
        jays_line = ('<p class="price-sub">Want it by section? Open the '
                     '<a href="/jays.html">live Blue Jays section tracker</a>.</p>'
                     if g["home_slug"] == "toronto-blue-jays" else "")
        body = f"""<div class="crumb"><a href="/">MLB</a> ›
<a href="/team/{e(g["home_slug"])}/">{e(g["home_name"])}</a> › {e(g["away_name"])}</div>
<div class="stub reveal">
  <div class="top">
    <h1 class="match">{e(title_m)}</h1>
    <div class="when">{datestr} · {timestr} · {e(g["venue"])}</div>
  </div>
  <div class="perf"></div>
  <div class="bottom">
    {price_block}
    <div><a class="cta" href="{e(buy_url(g))}" target="_blank" rel="nofollow sponsored">Find tickets <span class="arrow">→</span></a></div>
    <p class="price-sub">We check this game's resale price regularly and keep the
    history, so you can tell a real dip from a fake one. {g["checks"]} checks so far.</p>
    {jays_line}
  </div>
</div>
<p style="margin-top:18px"><a class="btn-ghost" href="/team/{e(g["home_slug"])}/">← all {e(g["home_name"])} home games</a></p>"""
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
