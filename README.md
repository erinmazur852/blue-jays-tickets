# SeatDip — Blue Jays Ticket Price Tracker

Tracks the lowest resale price (overall and per section group) for every
remaining Blue Jays home game at Rogers Centre, in CAD, and pushes a phone
notification when prices drop.

## The site (all 30 MLB teams)

- **`mlb_data.py`** — pulls every team + remaining home game from the MLB
  Stats API (no key) and, if `TM_API_KEY` is set, price ranges from the
  Ticketmaster Discovery API. Accumulates `mlb_price_history.csv` and writes
  `site_data.json`.
- **`build_site.py`** — generates the static site into `site/`: homepage,
  one page per team, one per game (~1,400 pages), plus `sitemap.xml`,
  `robots.txt`, and schema.org markup for search engines. Also bundles the
  Jays dashboard at `/jays.html`.
- **`.github/workflows/mlb-site.yml`** — hourly: fetch → build → deploy
  `site/` to Vercel. Needs secrets `VERCEL_TOKEN`, `VERCEL_ORG_ID`,
  `VERCEL_PROJECT_ID`, and optionally `TM_API_KEY`.

## The Jays section tracker (the original tool)

- **`fetch_prices.py`** — master schedule from the official MLB API, prices
  from Gametime's public feed (USD, converted at the Bank of Canada daily
  rate). Appends snapshots to `price_history.csv` (per game) and
  `section_history.csv` (per section group). `--no-sections` skips the
  slower per-section pass.
- **`notify_drops.py`** — compares the two latest snapshots and pushes a
  digest to [ntfy.sh](https://ntfy.sh) when any game's price dropped, new
  listings appeared, or a section dropped 5%+. Needs `NTFY_TOPIC`.
- **`index.html`** — dashboard, hosted at
  https://erinmazur852.github.io/blue-jays-tickets/ (refreshes with every
  snapshot commit). Section dropdown, per-game section breakdown,
  per-section target prices (stored in your browser), trend sparklines,
  buy links. Also works locally — just open the file.
- **`.github/workflows/track.yml`** — runs the above every 30 minutes.
  GitHub may delay scheduled runs by a few minutes under load.

## Notifications

Install the ntfy app (iOS/Android), subscribe to the topic stored in the
repo's `NTFY_TOPIC` secret. Anyone who knows the topic name can read it,
so treat the name like a password.

## History format

One row per game (or per game+section) per run, with the raw USD cents and
the USD/CAD rate used, so the CAD view stays honest as FX moves.
