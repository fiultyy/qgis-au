#!/usr/bin/env python3
"""
Batch geocode REA property listings using Nominatim OpenStreetMap API.
Processes listings with NULL lat/lon, writes coordinates back to SQLite.
SpatiaLite trigger auto-updates geom column.

Usage:
    python3 geocode_listings.py          # process all NULL lat/lon
    python3 geocode_listings.py --limit 50  # test with 50
"""

import urllib.request
import urllib.parse
import json
import sqlite3
import time
import re
import sys
import os

DB_PATH = "/home/yy/qgis-data/property_listings.db"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "PropertyPipeline/1.0 (local research)"
REQUEST_INTERVAL = 1.2  # seconds between requests (Nominatim <=1 req/sec)
RETRY_WAIT = 3.0  # seconds to wait before retry on error
MAX_RETRIES = 1

# Proxy for outbound network (Clash Verge on this host)
PROXY_HANDLER = urllib.request.ProxyHandler({
    "http": "http://127.0.0.1:7892",
    "https": "http://127.0.0.1:7892",
})
OPENER = urllib.request.build_opener(PROXY_HANDLER)

# ─── Address helpers ───────────────────────────────────────────────

def strip_unit_number(address):
    """
    Remove unit/lot numbers from address for better geocoding.
    '107/188 Day Street, Sydney' → '188 Day Street, Sydney'
    '601/38A Cumberland Street, The Rocks' → '38A Cumberland Street, The Rocks'
    '103/107-121 Quay Street, Haymarket' → '107-121 Quay Street, Haymarket'
    '77B/88 Barangaroo Avenue, Barangaroo' → '88 Barangaroo Avenue, Barangaroo'
    'Level 4/21 Barangaroo Ave, Barangaroo' → '21 Barangaroo Ave, Barangaroo'
    '82 Hay Street, Sydney' → unchanged
    """
    # Pattern: something/something → take the part after the last slash
    # but only if there's a slash in the street part (not in suburb)
    # We handle the "unit/street" pattern
    parts = address.split("/", 1)
    if len(parts) == 2:
        # Take everything after the first "/"
        street_part = parts[1].strip()
        # Remove leading/trailing commas
        street_part = street_part.strip(", ").strip()
        if street_part:
            return street_part
    
    # Handle "Level X/Y" pattern - already handled by above
    return address.strip()


def build_queries(address, suburb, state="NSW", country="Australia"):
    """
    Build a list of (query_string, match_type) tuples to try in order.
    Returns list of (query, type) pairs.
    """
    queries = []
    state_country = f"{state}, {country}"
    
    # Clean address
    addr = address.strip() if address else ""
    suburb_clean = suburb.strip() if suburb else ""
    
    # Skip obviously bad addresses
    if not addr or "address available on request" in addr.lower():
        if suburb_clean:
            queries.append((f"{suburb_clean}, {state_country}", "suburb"))
        return queries
    
    # Query 1: Full address with state/country (exact)
    full_q = f"{addr}, {suburb_clean}, {state_country}" if suburb_clean else f"{addr}, {state_country}"
    queries.append((full_q, "exact"))
    
    # Query 2: Strip unit number (street-level)
    stripped = strip_unit_number(addr)
    if stripped != addr:
        street_q = f"{stripped}, {suburb_clean}, {state_country}" if suburb_clean else f"{stripped}, {state_country}"
        queries.append((street_q, "street"))
    
    # Query 3: Suburb fallback
    if suburb_clean:
        queries.append((f"{suburb_clean}, {state_country}", "suburb"))
    
    return queries


# ─── Geocoding ─────────────────────────────────────────────────────

def nominatim_search(query):
    """
    Query Nominatim search API. Returns (lat, lon) or None.
    """
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "au",
    })
    url = f"{NOMINATIM_URL}?{params}"
    
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    
    try:
        with OPENER.open(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise  # let caller handle retry
    
    if data and len(data) > 0:
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return (lat, lon)
    return None


def geocode_one(address, suburb):
    """
    Try geocoding with progressively simpler queries.
    Returns (lat, lon, match_type) or (None, None, "failed").
    """
    queries = build_queries(address, suburb)
    
    for query, match_type in queries:
        for attempt in range(MAX_RETRIES + 1):
            try:
                result = nominatim_search(query)
                if result:
                    return (result[0], result[1], match_type)
                break  # no retry on successful-but-empty response
            except Exception:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_WAIT)
                else:
                    # Network error on this query, try next query
                    break
            finally:
                time.sleep(REQUEST_INTERVAL)
    
    return (None, None, "failed")


# ─── Database ──────────────────────────────────────────────────────

def open_db():
    """Open SQLite with SpatiaLite extension."""
    conn = sqlite3.connect(DB_PATH)
    conn.enable_load_extension(True)
    try:
        conn.load_extension("mod_spatialite")
    except Exception:
        print("  ⚠ SpatiaLite not loaded (geom trigger may not fire)")
    return conn


def get_pending(conn, limit=None):
    """Get listings where lat IS NULL."""
    sql = "SELECT id, address, suburb FROM listings WHERE lat IS NULL ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def update_coords(conn, listing_id, lat, lon):
    """Update lat/lon for a listing. SpatiaLite trigger updates geom."""
    conn.execute(
        "UPDATE listings SET lat=?, lon=? WHERE id=?",
        (lat, lon, listing_id)
    )
    conn.commit()


# ─── Main ──────────────────────────────────────────────────────────

def main():
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        limit = int(sys.argv[idx + 1])
    
    conn = open_db()
    rows = get_pending(conn, limit)
    total = len(rows)
    
    if total == 0:
        print("No listings pending geocoding. All done!")
        conn.close()
        return
    
    print(f"Geocoding {total} listings...", flush=True)
    print(f"DB: {DB_PATH}", flush=True)
    print(f"Rate limit: {REQUEST_INTERVAL}s between requests", flush=True)
    print(flush=True)
    
    stats = {"exact": 0, "street": 0, "suburb": 0, "failed": 0}
    failed_list = []
    
    for i, (listing_id, address, suburb) in enumerate(rows, 1):
        # Progress header every 50
        if (i - 1) % 50 == 0 and i > 1:
            done = stats["exact"] + stats["street"] + stats["suburb"]
            failed = stats["failed"]
            print(f"\n--- Progress: {i-1}/{total} | geocoded: {done} | failed: {failed} ---\n", flush=True)
        
        lat, lon, match_type = geocode_one(address, suburb)
        
        idx_str = f"[{i:03d}/{total}]"
        addr_display = (address or "?")[:50]
        
        if lat is not None:
            update_coords(conn, listing_id, lat, lon)
            stats[match_type] += 1
            print(f"{idx_str} {addr_display} → {lat:.4f}, {lon:.4f} ({match_type})", flush=True)
        else:
            stats["failed"] += 1
            failed_list.append((listing_id, address, suburb))
            print(f"{idx_str} {addr_display} → FAILED", flush=True)
    
    conn.close()
    
    # Final report
    geocoded = stats["exact"] + stats["street"] + stats["suburb"]
    coverage = geocoded / total * 100 if total > 0 else 0
    
    print(f"\n{'='*60}", flush=True)
    print(f"Results ({total} listings processed):", flush=True)
    print(f"  Exact (full address):  {stats['exact']:>4} ({stats['exact']/total*100:.1f}%)", flush=True)
    print(f"  Street (no unit):      {stats['street']:>4} ({stats['street']/total*100:.1f}%)", flush=True)
    print(f"  Suburb fallback:       {stats['suburb']:>4} ({stats['suburb']/total*100:.1f}%)", flush=True)
    print(f"  Failed:                {stats['failed']:>4} ({stats['failed']/total*100:.1f}%)", flush=True)
    print(f"  Coverage: {coverage:.1f}% ({geocoded}/{total})", flush=True)
    
    if failed_list:
        print(f"\nFailed listings ({len(failed_list)}):", flush=True)
        for lid, addr, sub in failed_list:
            print(f"  ID {lid}: {addr}, {sub}", flush=True)
    
    print(f"\n✓ Done. geom column auto-updated by SpatiaLite trigger.", flush=True)


if __name__ == "__main__":
    main()
