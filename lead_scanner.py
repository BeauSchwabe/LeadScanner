#!/usr/bin/env python3
"""
================================================================================
 LEAD SCANNER
 Find local businesses that match a service you offer -- with an automated
 website audit built in, so you know who actually needs you.
 Designed and built by Beau Schwabe (weathersiren.com)
================================================================================

WHAT THIS DOES
--------------
You tell it a location and what kind of business interests you (e.g.
"electronics manufacturers", "law firms", "3D printing prospects" -- anything,
in plain English). It searches Google Places for matching businesses in that
area, pulls contact info, and -- optionally -- runs a quick automated audit of
each business's website (mobile-friendliness, HTTPS, staleness, DIY-builder
detection, or a missing site entirely) so you can prioritize outreach.

Output: a single CSV file, sorted by a lead score.

--------------------------------------------------------------------------------
QUICK START
--------------------------------------------------------------------------------

1. GET A FREE GOOGLE API KEY (takes about 5 minutes)

   a. Go to https://console.cloud.google.com/ and sign in with any Google
      account. Google gives new accounts $300 in free trial credit -- this
      tool uses only a tiny fraction of that for normal use.

   b. Create a project (or use the default one Google gives you).

   c. In the search bar at the top, search for "Places API" and click
      Enable. Then search for "Geocoding API" and click Enable on that too.

   d. In the left menu: APIs & Services -> Credentials -> "+ Create
      credentials" -> "API key". Copy the key it gives you.

   e. (Optional but recommended) Click into the key's settings and, under
      "API restrictions", limit it to just Places API and Geocoding API.

2. INSTALL DEPENDENCIES

      pip install requests

   (That's the only dependency -- this tool is a single file, no other
   setup needed.)

3. RUN IT

      python lead_scanner.py

   The first time you run it with no options, it will walk you through a
   short setup wizard (API key, location, what kind of business you're
   looking for) and save your answers so you don't have to re-enter them
   every time.

   Once configured, you can also run it non-interactively:

      python lead_scanner.py --location "Denver, CO" --interest "commercial roofing contractors"
      python lead_scanner.py --location "Austin, TX" --interest "law firms" --audit-site --limit 40

--------------------------------------------------------------------------------
COMMAND LINE OPTIONS (all optional -- omit any of them to be prompted instead)
--------------------------------------------------------------------------------
  --location TEXT       City/region to search, e.g. "Oklahoma City, OK"
  --radius-miles N       Search radius in miles (default 30)
  --interest TEXT        What kind of business you're looking for, plain
                          English, comma-separated for multiple, e.g.
                          "dental offices, chiropractors, law firms"
  --preset NAME          Use a built-in preset instead of --interest:
                          electronics | web_design | 3d_printing
  --audit-site           Run the website audit (recommended for web design
                          leads; adds time since it visits every site)
  --limit N              Max results per search term (default 20)
  --output PATH          Output CSV file (default leads.csv)
  --reconfigure          Re-run the setup wizard and overwrite saved config
  --api-key KEY          Pass the API key directly instead of using saved
                          config or the GOOGLE_PLACES_API_KEY env variable

CONFIG FILE
-----------
Your API key and last-used settings are saved to:
      ~/.lead_scanner_config.json
so you don't have to re-enter them each run. Delete that file (or run with
--reconfigure) any time to start fresh. The API key is stored in plain text
in that file -- keep it out of anything you share or commit to git.
================================================================================
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import requests
except ImportError:
    print("Missing dependency. Run:  pip install requests")
    sys.exit(1)

PLACES_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".lead_scanner_config.json")

CURRENT_YEAR = time.localtime().tm_year

# Built-in starting points -- feel free to use --interest instead for
# anything not covered here.
PRESETS = {
    "electronics": [
        "electronics manufacturer", "industrial automation company",
        "PLC systems integrator", "custom machine builder",
        "process control systems company", "manufacturing company",
        "robotics company",
    ],
    "web_design": [
        "law firm", "dental office", "auto repair shop", "family restaurant",
        "retail boutique", "hvac contractor", "landscaping company",
        "chiropractor", "veterinary clinic", "insurance agency",
    ],
    "3d_printing": [
        "product design firm", "mechanical engineering firm",
        "architecture firm", "jewelry designer", "dental lab",
        "orthotics and prosthetics", "prototype shop",
        "industrial design studio",
    ],
}


def banner():
    print("=" * 60)
    print("  LEAD SCANNER")
    print("  Local business search + automated website audit")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Config load / save / interactive setup
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


def prompt(text: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{text}{suffix}: ").strip()
    return val if val else (default or "")


def run_setup_wizard(existing: dict) -> dict:
    print()
    print("--- First-time setup ---")
    print("(Answers are saved to ~/.lead_scanner_config.json so you only")
    print(" need to do this once. Run with --reconfigure to redo it.)")
    print()

    api_key = existing.get("api_key", "")
    print("1. Google Places API key")
    print("   Don't have one? See the instructions at the top of this file")
    print("   (or run: python lead_scanner.py --help)")
    api_key = prompt("   Enter your API key", api_key)
    while not api_key:
        print("   An API key is required.")
        api_key = prompt("   Enter your API key")

    print()
    location = prompt("2. Default location to search (city, state)",
                       existing.get("location", ""))

    print()
    print("3. What kind of business are you looking for?")
    print("   Type in plain English, comma-separated for more than one.")
    print('   Examples: "electronics manufacturers, industrial automation"')
    print('             "law firms, dental offices, chiropractors"')
    interest = prompt("   Business interest", existing.get("interest", ""))

    cfg = {
        "api_key": api_key,
        "location": location,
        "interest": interest,
    }
    save_config(cfg)
    print()
    print(f"Saved to {CONFIG_PATH}")
    print()
    return cfg


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Lead:
    name: str
    query: str
    address: str = ""
    phone: str = ""
    website: str = ""
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    place_id: str = ""
    site_status: str = ""
    site_notes: list = field(default_factory=list)
    lead_score: int = 0


# ---------------------------------------------------------------------------
# Google Places calls
# ---------------------------------------------------------------------------

def geocode_bias(location: str, api_key: str):
    resp = requests.get(GEOCODE_URL, params={"address": location, "key": api_key}, timeout=15)
    data = resp.json()
    if data.get("status") != "OK" or not data.get("results"):
        print(f"[warn] could not geocode '{location}', proceeding without bias")
        return None
    loc = data["results"][0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def text_search(query: str, location: str, radius_meters: int, api_key: str,
                 latlng=None, limit: int = 20):
    results = []
    params = {"query": f"{query} near {location}", "key": api_key}
    if latlng:
        params["location"] = f"{latlng[0]},{latlng[1]}"
        params["radius"] = radius_meters

    next_token = None
    while len(results) < limit:
        if next_token:
            params = {"pagetoken": next_token, "key": api_key}
            time.sleep(2)
        resp = requests.get(PLACES_TEXT_SEARCH_URL, params=params, timeout=15)
        data = resp.json()
        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            print(f"[warn] search '{query}' returned status={status}: "
                  f"{data.get('error_message', '')}")
            break
        results.extend(data.get("results", []))
        next_token = data.get("next_page_token")
        if not next_token:
            break
    return results[:limit]


def get_details(place_id: str, api_key: str):
    resp = requests.get(
        PLACES_DETAILS_URL,
        params={"place_id": place_id,
                "fields": "formatted_phone_number,website,formatted_address",
                "key": api_key},
        timeout=15,
    )
    data = resp.json()
    return data.get("result", {}) if data.get("status") == "OK" else {}


# ---------------------------------------------------------------------------
# Website audit (lightweight heuristics, not a full technical review)
# ---------------------------------------------------------------------------

def audit_website(url: str) -> tuple:
    notes = []
    if not url:
        return "no_website", ["No website listed in Google Business Profile"]

    try:
        resp = requests.get(url, timeout=10,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; LeadScanner/1.0)"},
                             allow_redirects=True)
    except requests.exceptions.SSLError:
        return "ssl_error", ["SSL certificate error -- site is broken or insecure"]
    except requests.exceptions.RequestException as e:
        return "unreachable", [f"Site did not respond ({type(e).__name__})"]

    if resp.status_code >= 400:
        notes.append(f"Site returned HTTP {resp.status_code}")
    if not url.lower().startswith("https"):
        notes.append("No HTTPS (not secure)")

    html = resp.text.lower()

    if "viewport" not in html:
        notes.append("No mobile viewport meta tag (likely not mobile-responsive)")

    years_found = re.findall(r"(?:19|20)\d{2}", html[-4000:])
    if years_found:
        try:
            most_recent = max(int(y) for y in years_found if 1995 <= int(y) <= CURRENT_YEAR)
            if CURRENT_YEAR - most_recent >= 3:
                notes.append(f"Footer/content year appears stale ({most_recent})")
        except ValueError:
            pass

    if "wix.com" in html or "squarespace" in html:
        notes.append("Built on Wix/Squarespace (DIY builder, often a redesign opportunity)")

    if re.search(r"<table[^>]*>.*<table", html, re.DOTALL):
        notes.append("Table-based layout detected (old-school HTML)")

    if not notes:
        return "looks_ok", ["No obvious red flags from automated check -- review manually"]
    return "flagged", notes


def score_lead(lead: Lead, audited: bool) -> int:
    score = 0
    if audited:
        if lead.site_status == "no_website":
            score += 10
        elif lead.site_status in ("unreachable", "ssl_error"):
            score += 8
        elif lead.site_status == "flagged":
            score += len(lead.site_notes) * 2
    if lead.user_ratings_total and lead.user_ratings_total >= 5:
        score += 3
    if lead.website:
        score += 1
    return score


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(location: str, radius_miles: float, queries: list, limit_per_query: int,
        api_key: str, do_site_audit: bool, output_path: str):
    radius_meters = int(radius_miles * 1609.34)
    latlng = geocode_bias(location, api_key)

    all_leads = []
    seen = set()

    for query in queries:
        print(f"[search] '{query}' near {location} ...")
        results = text_search(query, location, radius_meters, api_key,
                               latlng=latlng, limit=limit_per_query)
        for r in results:
            place_id = r.get("place_id")
            if not place_id or place_id in seen:
                continue
            seen.add(place_id)

            details = get_details(place_id, api_key)
            lead = Lead(
                name=r.get("name", ""),
                query=query,
                address=details.get("formatted_address", r.get("formatted_address", "")),
                phone=details.get("formatted_phone_number", ""),
                website=details.get("website", ""),
                rating=r.get("rating"),
                user_ratings_total=r.get("user_ratings_total"),
                place_id=place_id,
            )

            if do_site_audit:
                status, notes = audit_website(lead.website)
                lead.site_status = status
                lead.site_notes = notes

            lead.lead_score = score_lead(lead, do_site_audit)
            all_leads.append(lead)

    all_leads.sort(key=lambda l: l.lead_score, reverse=True)
    write_csv(all_leads, output_path, do_site_audit)
    print(f"\nDone. {len(all_leads)} unique leads written to {output_path}")


def write_csv(leads: list, path: str, audited: bool):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = ["Lead Score", "Business Name", "Phone", "Website", "Address",
                   "Google Rating", "Rating Count", "Matched Search Term", "Google Place ID"]
        if audited:
            header.insert(4, "Site Notes")
            header.insert(4, "Site Audit Status")
        writer.writerow(header)
        for l in leads:
            row = [l.lead_score, l.name, l.phone, l.website]
            if audited:
                row += [l.site_status, " | ".join(l.site_notes)]
            row += [l.address, l.rating or "", l.user_ratings_total or "", l.query, l.place_id]
            writer.writerow(row)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_queries_from_interest(interest: str) -> list:
    return [term.strip() for term in interest.split(",") if term.strip()]


def main():
    parser = argparse.ArgumentParser(
        description="Find local businesses matching a service you offer, with an optional website audit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--location")
    parser.add_argument("--radius-miles", type=float, default=30)
    parser.add_argument("--interest", help="Plain-English business interest, comma-separated")
    parser.add_argument("--preset", choices=list(PRESETS.keys()))
    parser.add_argument("--audit-site", action="store_true",
                         help="Run the website audit on each result")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", default="leads.csv")
    parser.add_argument("--reconfigure", action="store_true",
                         help="Re-run setup wizard and overwrite saved config")
    parser.add_argument("--api-key", help="Override saved/env API key")
    args = parser.parse_args()

    banner()

    cfg = load_config()
    if args.reconfigure or not cfg.get("api_key"):
        cfg = run_setup_wizard(cfg)

    api_key = args.api_key or os.environ.get("GOOGLE_PLACES_API_KEY") or cfg.get("api_key")
    if not api_key:
        print("No API key available. Run with --reconfigure to set one up.")
        sys.exit(1)

    location = args.location or cfg.get("location")
    if not location:
        location = prompt("Location to search (city, state)")

    if args.preset:
        queries = PRESETS[args.preset]
    elif args.interest:
        queries = build_queries_from_interest(args.interest)
    elif cfg.get("interest"):
        queries = build_queries_from_interest(cfg["interest"])
    else:
        interest = prompt('Business interest (plain English, comma-separated)')
        queries = build_queries_from_interest(interest)

    if not queries:
        print("No search terms provided. Nothing to do.")
        sys.exit(1)

    print()
    print(f"Location: {location}")
    print(f"Radius:   {args.radius_miles} miles")
    print(f"Searching for: {', '.join(queries)}")
    print(f"Website audit: {'on' if args.audit_site else 'off'}")
    print()

    run(
        location=location,
        radius_miles=args.radius_miles,
        queries=queries,
        limit_per_query=args.limit,
        api_key=api_key,
        do_site_audit=args.audit_site,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
