#!/usr/bin/env python3
"""
property_pipeline.py — Property Listings Data Cleaning Pipeline

Cleans scraped property listing JSON into a SQLite database with normalised
fields, deduplication, status tracking, and optional daemon mode.

Usage:
  python3 property_pipeline.py --once      # Process all scraped/*.json once
  python3 property_pipeline.py --watch N   # Daemon: scan every N seconds
  python3 property_pipeline.py --stats     # Print database statistics
"""

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
import sys

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = "/home/yy/qgis-data"
SCRAPE_DIR  = os.path.join(BASE_DIR, "scraped")
PROCESSED   = os.path.join(SCRAPE_DIR, "processed")
DB_PATH     = os.path.join(BASE_DIR, "property_listings.db")

# ── Source mapping ───────────────────────────────────────────────────────────
SOURCE_MAP = {
    "realestate.com.au": "rea",
    "domain.com.au":     "domain",
    "homely.com.au":     "homely",
}

# ── Property type normalisation ──────────────────────────────────────────────
PROPERTY_TYPE_MAP = {
    "apartment": "apartment",
    "unit":      "apartment",
    "flat":      "apartment",
    "house":     "house",
    "townhouse": "townhouse",
    "studio":    "studio",
    "villa":     "villa",
    "duplex":    "duplex",
    "terrace":   "terrace",
    "land":      "land",
}


def normalise_property_type(raw):
    """Normalise raw property type string to canonical lowercase value."""
    if not raw:
        return "other"
    key = raw.strip().lower()
    return PROPERTY_TYPE_MAP.get(key, "other")


# ── Price parsing ────────────────────────────────────────────────────────────

def parse_price(raw):
    """
    Parse a raw price string into (price_min, price_max, price_display).

    Returns:
        (int|None, int|None, str|None)
    """
    if not raw or not raw.strip():
        return (None, None, None)

    text = raw.strip()
    lower = text.lower()

    # Skip rental prices
    if any(kw in lower for kw in ("$pw", "per week", "p.w.", "/week", "weekly")):
        return (None, None, None)

    # Contact agent / POA / TBA — no numeric price
    if any(kw in lower for kw in ("contact agent", "poa", "price on application",
                                   "tba", "tbc", "n/a", "on request")):
        return (None, None, None)

    # Try to find all monetary amounts in the string.
    # Supports optional $ prefix, comma separators, and m/k suffixes.
    # Matches: $1,200,000 | $1.2m | $850,000 | 1.75M | 1.5mil | $1.21mil
    amounts = []
    for m in re.finditer(r'(?:\$\s*)?([\d,]+(?:\.\d+)?)\s*(mil|m|k)?\b', text, re.IGNORECASE):
        num_str = m.group(1).replace(",", "")
        suffix  = (m.group(2) or "").lower()
        try:
            val = float(num_str)
        except ValueError:
            continue
        if suffix in ("m", "mil"):
            val *= 1_000_000
        elif suffix == "k":
            val *= 1_000
        # Sanity: ignore implausible values (< 10k likely not a sale price)
        if val < 10_000:
            continue
        amounts.append(int(val))

    if not amounts:
        # Could not extract any number
        # Auction with no extractable guide → display "Auction"
        if "auction" in lower:
            return (None, None, "Auction")
        return (None, None, text if text else None)

    # Build display: prefer original text, but use "Auction" if auction keyword present
    display = "Auction" if "auction" in lower else text

    if len(amounts) == 1:
        return (amounts[0], amounts[0], display)
    else:
        return (min(amounts), max(amounts), display)


# ── Land size parsing ────────────────────────────────────────────────────────

def parse_land_size(raw):
    """Parse land size string → float sqm or None."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    # Match patterns like "348m²", "348 sqm", "348m2"
    m = re.match(r'^([\d,.]+)\s*(?:m\s*²?|sqm|m2)?\s*$', text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


# ── Source listing ID extraction ─────────────────────────────────────────────

def extract_listing_id(url, address, suburb):
    """
    Extract unique listing ID from URL; fall back to md5(address+suburb).
    """
    if url:
        # Try to extract trailing numeric ID (e.g. -151586220)
        m = re.search(r'-(\d{5,})(?:\?|$|/)', url)
        if m:
            return m.group(1)
        # Fallback: any long digit sequence at end
        m = re.search(r'(\d{6,})\s*$', url)
        if m:
            return m.group(1)

    # No usable URL → deterministic hash
    key = f"{address or ''}|{suburb or ''}".encode("utf-8")
    return hashlib.md5(key).hexdigest()[:16]


# ── Database ─────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS listings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT NOT NULL,
    source_listing_id   TEXT,
    address             TEXT NOT NULL,
    suburb              TEXT,
    state               TEXT DEFAULT 'NSW',
    postcode            TEXT,
    price_raw           TEXT,
    price_min           INTEGER,
    price_max           INTEGER,
    price_display       TEXT,
    beds                INTEGER,
    baths               INTEGER,
    cars                INTEGER,
    land_size_raw       TEXT,
    land_size_sqm       REAL,
    property_type       TEXT,
    listing_url         TEXT,
    agent_name          TEXT,
    lat                 REAL,
    lon                 REAL,
    price_per_sqm       REAL,
    full_address        TEXT,
    scrape_round        TEXT,
    status              TEXT DEFAULT 'active',
    first_seen          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_json            TEXT,
    UNIQUE(source, source_listing_id)
);

CREATE TABLE IF NOT EXISTS status_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  INTEGER NOT NULL,
    old_status  TEXT,
    new_status  TEXT,
    changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (listing_id) REFERENCES listings(id)
);

CREATE INDEX IF NOT EXISTS idx_listings_status   ON listings(status);
CREATE INDEX IF NOT EXISTS idx_listings_suburb   ON listings(suburb);
CREATE INDEX IF NOT EXISTS idx_listings_source   ON listings(source);
CREATE INDEX IF NOT EXISTS idx_listings_address  ON listings(address);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    # Load SpatiaLite for geometry support (QGIS integration)
    try:
        conn.enable_load_extension(True)
        conn.load_extension('mod_spatialite')
        conn.execute("SELECT InitSpatialMetaData(1)")
        # Register geometry column if not yet present
        exists = conn.execute(
            "SELECT COUNT(*) FROM geometry_columns WHERE f_table_name='listings' AND f_geometry_column='geom'"
        ).fetchone()[0]
        if not exists:
            conn.execute("SELECT AddGeometryColumn('listings','geom',4326,'POINT','XYZ')")
        # Auto-update geom when lat/lon change
        conn.execute('''
            CREATE TRIGGER IF NOT EXISTS listings_geom_update
            AFTER UPDATE OF lat, lon ON listings
            FOR EACH ROW
            WHEN NEW.lat IS NOT NULL AND NEW.lon IS NOT NULL
            BEGIN
                UPDATE listings SET geom = MakePoint(NEW.lon, NEW.lat, 4326) WHERE id = NEW.id;
            END
        ''')
    except Exception as e:
        print(f"  ⚠ SpatiaLite not available: {e}. Geometry features disabled.", file=sys.stderr)
    return conn


# ── Address parsing ──────────────────────────────────────────────────────────

def parse_address_components(address):
    """Try to extract postcode from address string."""
    postcode = None
    state    = "NSW"
    if address:
        m = re.search(r'\b(\d{4})\s*$', address)
        if m:
            postcode = m.group(1)
    return state, postcode


# ── Core processing ──────────────────────────────────────────────────────────

def process_listing(raw, source_key):
    """Clean a single raw listing dict → cleaned dict ready for DB."""

    address = (raw.get("address") or "").strip()
    suburb  = (raw.get("suburb") or "").strip() or None

    if not address:
        return None  # skip invalid

    url = (raw.get("listing_url") or "").strip() or None
    src_id = extract_listing_id(url, address, suburb)

    price_raw = raw.get("price")
    p_min, p_max, p_disp = parse_price(str(price_raw) if price_raw is not None else "")

    land_raw = raw.get("land_size")
    land_sqm = parse_land_size(str(land_raw) if land_raw is not None else "")

    ptype = normalise_property_type(raw.get("property_type"))

    state, postcode = parse_address_components(address)

    def safe_int(v):
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    # Build full address
    parts = [address]
    if suburb:
        parts.append(suburb)
    parts.append(state)
    if postcode:
        parts.append(postcode)
    full_address = ", ".join(parts)

    # Price per sqm
    price_per_sqm = None
    if p_min and land_sqm and land_sqm > 0:
        price_per_sqm = round(p_min / land_sqm, 2)

    return {
        "source":            source_key,
        "source_listing_id": src_id,
        "address":           address,
        "suburb":            suburb,
        "state":             state,
        "postcode":          postcode,
        "price_raw":         str(price_raw) if price_raw is not None else None,
        "price_min":         p_min,
        "price_max":         p_max,
        "price_display":     p_disp,
        "beds":              safe_int(raw.get("beds")),
        "baths":             safe_int(raw.get("baths")),
        "cars":              safe_int(raw.get("cars")),
        "land_size_raw":     str(land_raw) if land_raw is not None else None,
        "land_size_sqm":     land_sqm,
        "property_type":     ptype,
        "listing_url":       url,
        "agent_name":        (raw.get("agent_name") or "").strip() or None,
        "lat":               None,
        "lon":               None,
        "price_per_sqm":     price_per_sqm,
        "full_address":      full_address,
        "scrape_round":      source_key + "_initial",
        "raw_json":          json.dumps(raw, ensure_ascii=False),
    }


def update_geometry(conn, listing_id, lat, lon):
    """Update geom column from lat/lon using SpatiaLite MakePoint."""
    if lat is None or lon is None:
        return
    try:
        conn.execute(
            "UPDATE listings SET geom=MakePoint(?, ?, 4326) WHERE id=?",
            (lon, lat, listing_id)  # Note: MakePoint(x, y) = (lon, lat)
        )
    except Exception:
        pass  # SpatiaLite not available or geom column missing


def upsert_listing(conn, c):
    """Insert or update a cleaned listing. Returns (status_flag, old_status)."""
    cur = conn.execute(
        "SELECT id, status FROM listings WHERE source=? AND source_listing_id=?",
        (c["source"], c["source_listing_id"]),
    )
    row = cur.fetchone()

    if row is None:
        # Insert new
        cols = ", ".join(c.keys())
        phs  = ", ".join(["?"] * len(c))
        conn.execute(
            f"INSERT INTO listings ({cols}) VALUES ({phs})",
            list(c.values()),
        )
        # Update geometry from lat/lon if available (post-insert, requires row id)
        # Geometry is set via trigger or explicit update when coords are populated
        return ("new", None)
    else:
        # Update existing — check status change
        listing_id  = row[0]
        old_status  = row[1]

        update_cols = {k: v for k, v in c.items()
                       if k not in ("source", "source_listing_id")}
        # Always update last_checked; update last_updated only if data changed
        set_parts = [f"{k}=?" for k in update_cols.keys()]
        set_parts.append("last_checked=CURRENT_TIMESTAMP")
        set_parts.append("last_updated=CURRENT_TIMESTAMP")
        set_sql = ", ".join(set_parts)
        values  = list(update_cols.values()) + [listing_id]

        conn.execute(
            f"UPDATE listings SET {set_sql} WHERE id=?",
            values,
        )

        if old_status != "active":
            # Was not active, now active again → status change
            conn.execute(
                "UPDATE listings SET status='active' WHERE id=?",
                (listing_id,),
            )
            conn.execute(
                "INSERT INTO status_history (listing_id, old_status, new_status) VALUES (?, ?, ?)",
                (listing_id, old_status, "active"),
            )

        return ("updated", old_status)


def process_file(conn, filepath):
    """Process one scraped JSON file. Returns (processed_count, error_count)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ✗ Error reading {filepath}: {e}")
        return (0, 1)

    raw_source = data.get("source", "unknown")
    source_key = SOURCE_MAP.get(raw_source, raw_source.split(".")[0] if raw_source else "unknown")

    listings = data.get("listings", [])
    if not listings:
        print(f"  · {os.path.basename(filepath)}: no listings found")
        return (0, 0)

    processed = 0
    errors    = 0

    for raw in listings:
        try:
            cleaned = process_listing(raw, source_key)
            if cleaned is None:
                errors += 1
                continue
            upsert_listing(conn, cleaned)
            processed += 1
        except Exception as e:
            print(f"  ✗ Listing error: {e}")
            errors += 1

    conn.commit()
    print(f"  ✓ {os.path.basename(filepath)}: {processed} processed, {errors} errors")

    # Move to processed/
    os.makedirs(PROCESSED, exist_ok=True)
    dest = os.path.join(PROCESSED, os.path.basename(filepath))
    try:
        shutil.move(filepath, dest)
        print(f"  → Moved to {dest}")
    except OSError as e:
        print(f"  ⚠ Could not move {filepath}: {e}")

    return (processed, errors)


def run_once():
    """Scan scraped/*.json once, process, and print stats."""
    pattern = os.path.join(SCRAPE_DIR, "*.json")
    files = sorted(glob.glob(pattern))

    if not files:
        print("No JSON files found in scraped/")
        return

    print(f"Found {len(files)} file(s) to process")
    conn = get_db()

    total_processed = 0
    total_errors    = 0

    for fp in files:
        p, e = process_file(conn, fp)
        total_processed += p
        total_errors    += e

    conn.close()
    print(f"\nTotal: {total_processed} processed, {total_errors} errors")
    print_stats()


def run_watch(interval):
    """Daemon mode: scan every `interval` seconds."""
    print(f"Watch mode: scanning every {interval}s. Press Ctrl+C to stop.")
    while True:
        try:
            run_once()
            print(f"\nSleeping {interval}s...\n")
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nShutting down.")
            break
        except Exception as e:
            print(f"Error in watch loop: {e}")
            time.sleep(interval)


# ── Stats ────────────────────────────────────────────────────────────────────

def print_stats():
    """Print database statistics to stdout."""
    conn = get_db()
    c = conn.cursor()

    # Totals
    total      = c.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    active     = c.execute("SELECT COUNT(*) FROM listings WHERE status='active'").fetchone()[0]
    withdrawn  = c.execute("SELECT COUNT(*) FROM listings WHERE status='withdrawn'").fetchone()[0]
    sold       = c.execute("SELECT COUNT(*) FROM listings WHERE status='sold'").fetchone()[0]

    # By source
    rows = c.execute(
        "SELECT source, COUNT(*) FROM listings GROUP BY source ORDER BY COUNT(*) DESC"
    ).fetchall()
    by_source = ", ".join(f"{r[0]}={r[1]}" for r in rows)

    # By property type
    rows = c.execute(
        "SELECT property_type, COUNT(*) FROM listings GROUP BY property_type ORDER BY COUNT(*) DESC"
    ).fetchall()
    by_type = ", ".join(f"{r[0]}={r[1]}" for r in rows)

    # Price coverage
    with_price = c.execute(
        "SELECT COUNT(*) FROM listings WHERE price_min IS NOT NULL"
    ).fetchone()[0]

    # Coordinate coverage
    with_coords = c.execute(
        "SELECT COUNT(*) FROM listings WHERE lat IS NOT NULL AND lon IS NOT NULL"
    ).fetchone()[0]

    # Suburb count
    suburb_count = c.execute(
        "SELECT COUNT(DISTINCT suburb) FROM listings WHERE suburb IS NOT NULL"
    ).fetchone()[0]

    # Potential cross-source duplicates
    dupes = c.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT address, suburb, COUNT(DISTINCT source) AS src_cnt
            FROM listings
            WHERE suburb IS NOT NULL
            GROUP BY address, suburb
            HAVING src_cnt > 1
        )
        """
    ).fetchone()[0]

    print("\n=== Property Pipeline Stats ===")
    print(f"Total: {total} | Active: {active} | Withdrawn: {withdrawn} | Sold: {sold}")
    print(f"By source: {by_source}")
    print(f"By type: {by_type}")
    if total > 0:
        print(f"Price coverage: {with_price / total * 100:.1f}% ({with_price}/{total})")
        print(f"Coordinate coverage: {with_coords / total * 100:.1f}% ({with_coords}/{total})")
    else:
        print("Price coverage: N/A (0/0)")
        print("Coordinate coverage: N/A (0/0)")
    print(f"Suburbs: {suburb_count}")
    if dupes:
        print(f"Potential cross-source duplicates: {dupes}")

    conn.close()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Property listings data cleaning pipeline"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once",   action="store_true", help="Process scraped JSON once")
    group.add_argument("--watch",  type=int, nargs="?", const=300, default=None,
                        metavar="N", help="Daemon mode: scan every N seconds (default 300)")
    group.add_argument("--stats",  action="store_true", help="Print database statistics")
    args = parser.parse_args()

    if args.stats:
        print_stats()
    elif args.watch is not None:
        run_watch(args.watch)
    elif args.once:
        run_once()


if __name__ == "__main__":
    main()
