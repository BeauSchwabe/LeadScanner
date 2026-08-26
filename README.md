# Lead Scanner

Find local businesses that match a service you offer — with an automated
website audit built in, so you know who actually needs you.

Give it a location and, in plain English, what kind of business you're
looking for ("electronics manufacturers", "law firms", "roofing
contractors", anything). It searches Google Places for matching businesses
in that area, pulls contact info, and — optionally — audits each business's
website (mobile-friendliness, HTTPS, staleness, DIY-builder detection, or a
missing site entirely) so you can prioritize outreach instead of guessing.

Output: a single CSV file, sorted by lead score.

Single file, no framework, no server — just Python and one dependency.

## Quick start

### 1. Get a free Google API key (~5 minutes)

1. Go to [console.cloud.google.com](https://console.cloud.google.com/) and
   sign in with any Google account. New accounts get $300 in free trial
   credit — this tool uses only a tiny fraction of that for normal use.
2. Create a project (or use the default one Google gives you).
3. In the search bar at the top, search **"Places API"** and click
   **Enable**. Then search **"Geocoding API"** and enable that too.
4. Left menu → **APIs & Services → Credentials → "+ Create credentials" →
   "API key"**. Copy the key.
5. *(Recommended)* Click into the key's settings and, under **API
   restrictions**, limit it to just Places API and Geocoding API.

### 2. Install

```bash
pip install requests
```

That's the only dependency.

### 3. Run

```bash
python lead_scanner.py
```

First run walks you through a short setup wizard — API key, default
location, and what kind of business you're looking for — then saves your
answers to `~/.lead_scanner_config.json` so you don't re-enter them every
time.

Once configured, you can also run it non-interactively:

```bash
python lead_scanner.py --location "Denver, CO" --interest "commercial roofing contractors"
python lead_scanner.py --location "Austin, TX" --interest "law firms" --audit-site --limit 40
```

## Options

| Flag | Description |
|---|---|
| `--location TEXT` | City/region to search, e.g. `"Oklahoma City, OK"` |
| `--radius-miles N` | Search radius in miles (default 30) |
| `--interest TEXT` | Plain-English business interest, comma-separated for multiple |
| `--preset NAME` | Use a built-in preset instead of `--interest`: `electronics`, `web_design`, `3d_printing` |
| `--audit-site` | Run the website audit (recommended for web design leads; adds time since it visits every site) |
| `--limit N` | Max results per search term (default 20) |
| `--output PATH` | Output CSV file (default `leads.csv`) |
| `--reconfigure` | Re-run the setup wizard and overwrite saved config |
| `--api-key KEY` | Pass the API key directly instead of using saved config or the `GOOGLE_PLACES_API_KEY` env variable |

Run `python lead_scanner.py --help` any time for the full instructions —
they're built into the script itself.

## Reading the output CSV

- **Lead Score** — higher = more promising. With `--audit-site` on, this
  weights missing/broken/DIY-builder sites highest. Without it, this
  weights review volume (a rough "this is a real, established business"
  signal) and having an existing website (someone to call).
- **Site Audit Status** *(only with `--audit-site`)* —
  `no_website`, `unreachable`, `ssl_error`, `flagged`, or `looks_ok`.
- **Site Notes** *(only with `--audit-site`)* — the specific things the
  audit flagged, e.g. "No mobile viewport meta tag", "Built on
  Wix/Squarespace", "Footer/content year appears stale (2019)". This is a
  *heuristic* screen, not a technical audit — always look at the actual
  site before pitching.

## Config file

Your API key and last-used settings are saved to
`~/.lead_scanner_config.json` so you don't have to re-enter them each run.
Delete that file (or run with `--reconfigure`) any time to start fresh.
The API key is stored in plain text in that file — it's excluded from this
repo via `.gitignore`, and you should keep it out of anything you share.

## Limitations

- The website audit is intentionally lightweight — a handful of HTTP
  requests and pattern checks — built to surface candidates fast, not
  replace a human look at the site.
- Google Places text search returns up to ~60 results per search term
  (3 pages of 20); `--limit` caps how many you pull per term, not the true
  universe of matching businesses.
- Respect robots.txt / reasonable rate limits if you scale this up — the
  current version runs simple sequential requests with no aggressive
  concurrency, which is deliberate.

## License

MIT — see [LICENSE](LICENSE).

---

Designed and built by [Beau Schwabe](https://weathersiren.com).
