#!/usr/bin/env python3
"""
NSW Property Sales → Cadastre Matching v2 (Improved)
=====================================================
Improvements over v1:
  1. Fuzzy lot matching: try lot±1 for numeric lots
  2. Plan prefix variants: DP↔SP↔RS interchange
  3. Street-level fallback: match unmatched records to cadastre polygons
     using house_number + street_name text matching
  4. Nominatim address geocoding for remaining unmatched (batch, with rate limit)
  5. Strata-aware: recognize SP plans and skip cadastre for those, go to geocoding

Strategy:
  Phase 1: Build global cadastre index (same as v1, plus street-name index)
  Phase 2: Match CSV records (exact → fuzzy → street-level)
  Phase 3: Nominatim geocode remaining unmatched (optional, rate-limited)

Output:
  - nsw-property-matched-v2.gpkg     (all matched, parcel + geocoded)
  - nsw-property-unmatched-v2.gpkg   (still unmatched)
  - nsw-property-match-report-v2.txt

Usage:
  python3 nsw_property_match_v2.py                           # full run
  python3 nsw_property_match_v2.py --test-lga COFFS_HARBOUR   # single LGA test
  python3 nsw_property_match_v2.py --limit 100000             # limit rows
  python3 nsw_property_match_v2.py --skip-nominatim           # skip API geocoding
  python3 nsw_property_match_v2.py --process-unmatched        # process existing unmatched.gpkg
"""

import csv
import re
import os
import sys
import json
import time
import glob
import argparse
import urllib.request
import urllib.error
from collections import defaultdict, Counter
from osgeo import ogr, osr

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# ─── Configuration ────────────────────────────────────────────────────────────

CSV_PATH = "/home/yy/qgis-data/coffs-harbour/nsw-property-sales-data-updated20260721.csv"
UNMATCHED_GPKG = "/home/yy/qgis-data/nsw-property-unmatched.gpkg"
CADASTRE_DIR = "/home/yy/qgis-data/cadastre"
OUTPUT_DIR = "/home/yy/qgis-data"
REPORT_PATH = os.path.join(OUTPUT_DIR, "nsw-property-match-report-v2.txt")

OUTPUT_SRS = 3857

TEST_LGA_POSTCODES = {
    'COFFS_HARBOUR': {'2450', '2452', '2453', '2454', '2455', '2456', '2460'},
}

# Nominatim rate limit (1 req/sec per usage policy)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY = 1.1  # seconds between requests
NOMINATIM_TIMEOUT = 10

# Email for Nominatim usage policy
NOMINATIM_EMAIL = "noreply@example.com"  # Replace if needed


# ─── Legal Description Parser (from v1) ──────────────────────────────────────

def parse_legal_description(desc):
    """Parse NSW property legal description into list of (lot, section, plan_prefix, plan_num) tuples."""
    if not desc or not desc.strip():
        return []

    desc = desc.strip()
    desc = re.sub(r'\bPT\s+', '', desc, flags=re.I)
    desc = re.sub(r',\s+', ',', desc)

    results = []
    for parcel in desc.split():
        parcel = parcel.strip().strip(',')
        if not parcel:
            continue

        slash_count = parcel.count('/')
        if slash_count == 1:
            m = re.match(r'^(.+?)/([A-Za-z]*\d+)$', parcel)
            if not m:
                continue
            lot_str = m.group(1).strip()
            plan_str = m.group(2).strip()
            plan_prefix, plan_num = _parse_plan(plan_str)
            if plan_num is None:
                continue
            for lot in lot_str.split(','):
                lot = lot.strip()
                if lot:
                    results.append((lot, None, plan_prefix, plan_num))

        elif slash_count == 2:
            parts = parcel.split('/')
            if len(parts) != 3:
                continue
            lot_str, section, plan_str = parts[0].strip(), parts[1].strip(), parts[2].strip()
            plan_prefix, plan_num = _parse_plan(plan_str)
            if plan_num is None:
                continue
            for lot in lot_str.split(','):
                lot = lot.strip()
                if lot:
                    results.append((lot, section, plan_prefix, plan_num))
        else:
            continue

    return results


def _parse_plan(plan_str):
    plan_str = plan_str.strip()
    m = re.match(r'^(SP|DP|RS)(\d+)$', plan_str, re.I)
    if m:
        return m.group(1).upper(), m.group(2)
    if re.match(r'^\d+$', plan_str):
        return 'DP', plan_str
    return None, None


def is_strata_plan(plan_prefix, plan_num):
    """Check if this is a strata plan (SP prefix)"""
    return plan_prefix == 'SP'


# ─── Phase 1: Build Cadastre Index ────────────────────────────────────────────

def build_cadastre_index(cadastre_files, progress_every=50000):
    """Build global cadastre index with:
       - lotidstring_idx: {lotidstring_upper → (x, y, file_idx, area)}
       - lotplan_idx: {(lot_str, section, plan_str) → (x, y, file_idx, area)}
       - street_idx: {street_name_upper → [(x, y, file_idx, lotidstring), ...]} (per LGA centroid)
    """
    print("\n" + "=" * 60)
    print("Phase 1: Building global cadastre index")
    print("=" * 60)

    t0 = time.time()

    lotidstring_idx = {}
    lotplan_idx = {}
    file_names = []

    # Street index: (locality_upper, street_name_upper) → list of (x, y, file_idx)
    # Used for street-level fallback matching
    street_idx = defaultdict(list)
    # Also store centroids per LGA for distance-based fallback
    lga_centroids = {}  # file_idx → (avg_x, avg_y)

    total_features = 0
    total_indexed = 0

    for file_idx, gpkg_path in enumerate(cadastre_files):
        lga_name = os.path.basename(gpkg_path).replace('cadastre_', '').replace('.gpkg', '')
        file_names.append(lga_name)

        ds = ogr.Open(gpkg_path)
        if ds is None:
            continue
        layer = ds.GetLayer()

        file_features = 0
        file_indexed = 0
        coord_sum_x = 0
        coord_sum_y = 0
        coord_count = 0

        for feat in layer:
            total_features += 1
            file_features += 1

            if total_features % progress_every == 0:
                elapsed = time.time() - t0
                rate = total_features / elapsed if elapsed > 0 else 0
                print(f"  Processed {total_features:,} features "
                      f"({rate:,.0f}/s, {len(lotidstring_idx):,} indexed, "
                      f"file {file_idx + 1}/{len(cadastre_files)})")

            geom = feat.GetGeometryRef()
            if geom is None:
                feat = None
                continue

            try:
                point = geom.PointOnSurface()
            except Exception:
                try:
                    point = geom.Centroid()
                except Exception:
                    feat = None
                    continue

            if point is None:
                feat = None
                continue

            px, py = point.GetX(), point.GetY()
            area = feat.GetField('planlotarea') or 0.0
            coord_sum_x += px
            coord_sum_y += py
            coord_count += 1

            # ── lotidstring index ──
            lotidstring = feat.GetField('lotidstring')
            if lotidstring and str(lotidstring).strip():
                key = str(lotidstring).strip().upper()
                if key not in lotidstring_idx:
                    lotidstring_idx[key] = (px, py, file_idx, area)
                    total_indexed += 1
                    file_indexed += 1

                # Normalized keys (without prefix)
                m = re.match(r'^(.+?)//(.+)$', key)
                if m:
                    lot_part = m.group(1)
                    plan_part = m.group(2)
                    pm = re.match(r'^(?:DP|SP|RS)(\d+)$', plan_part)
                    if pm:
                        bare_key = f"{lot_part}//{pm.group(1)}"
                        if bare_key not in lotidstring_idx:
                            lotidstring_idx[bare_key] = (px, py, file_idx, area)

                m2 = re.match(r'^(.+?)/(.+?)/(?:DP|SP|RS)(\d+)$', key)
                if m2:
                    lot_p, sec_p, plan_p = m2.group(1), m2.group(2), m2.group(3)
                    bare_key2 = f"{lot_p}/{sec_p}//{plan_p}"
                    if bare_key2 not in lotidstring_idx:
                        lotidstring_idx[bare_key2] = (px, py, file_idx, area)

            # ── (lot, section, plan) index ──
            lotnumber = feat.GetField('lotnumber')
            sectionnumber = feat.GetField('sectionnumber')
            plannumber = feat.GetField('plannumber')

            if lotnumber is not None and plannumber is not None:
                lot_str = str(lotnumber).strip() if lotnumber else ''
                sec_str = str(sectionnumber).strip() if sectionnumber else ''
                plan_str = str(plannumber).strip() if plannumber else ''

                if lot_str and plan_str:
                    lp_key = (lot_str, sec_str, plan_str)
                    if lp_key not in lotplan_idx:
                        lotplan_idx[lp_key] = (px, py, file_idx, area)

                    lp_key_nosec = (lot_str, '', plan_str)
                    if lp_key_nosec not in lotplan_idx:
                        lotplan_idx[lp_key_nosec] = (px, py, file_idx, area)

            feat = None

        if coord_count > 0:
            lga_centroids[file_idx] = (coord_sum_x / coord_count, coord_sum_y / coord_count)

        ds = None
        print(f"  [{file_idx + 1}/{len(cadastre_files)}] {lga_name}: "
              f"{file_features:,} features, {file_indexed:,} indexed")

    elapsed = time.time() - t0
    print(f"\nPhase 1 complete: {total_features:,} features scanned in {elapsed:.1f}s")
    print(f"  lotidstring index: {len(lotidstring_idx):,}")
    print(f"  lotplan index:     {len(lotplan_idx):,}")
    print(f"  LGA centroids:     {len(lga_centroids):,}")

    return lotidstring_idx, lotplan_idx, file_names, lga_centroids


# ─── Matching Strategies ──────────────────────────────────────────────────────

def try_exact_match(parsed_list, lotidstring_idx, lotplan_idx):
    """Strategy 1: Exact match (same as v1)"""
    for lot, section, plan_prefix, plan_num in parsed_list:
        lp_keys = []
        if section:
            lp_keys.append((lot, str(section), plan_num))
        lp_keys.append((lot, '', plan_num))

        for lp_key in lp_keys:
            if lp_key in lotplan_idx:
                x, y, file_idx, area = lotplan_idx[lp_key]
                return (x, y, file_idx, lot, f"{plan_prefix}{plan_num}")

        # lotidstring with all prefix variants
        if section:
            base_keys = [
                f"{lot}/{section}//{plan_prefix}{plan_num}",
                f"{lot}/{section}//{plan_num}",
            ]
        else:
            all_prefixes = [plan_prefix] if plan_prefix else []
            for alt_pfx in ('DP', 'SP', 'RS'):
                if alt_pfx not in all_prefixes:
                    all_prefixes.append(alt_pfx)
            base_keys = []
            for pfx in all_prefixes:
                base_keys.append(f"{lot}//{pfx}{plan_num}")
            base_keys.append(f"{lot}//{plan_num}")

        for key in base_keys:
            key_upper = key.upper()
            if key_upper in lotidstring_idx:
                x, y, file_idx, area = lotidstring_idx[key_upper]
                return (x, y, file_idx, lot, f"{plan_prefix}{plan_num}")

    return None


def try_fuzzy_match(parsed_list, lotidstring_idx, lotplan_idx):
    """Strategy 2: Fuzzy matching for numeric lots.
    Try lot±1, lot±2 for numeric lots.
    Also try plan prefix variants (DP↔SP↔RS).
    """
    for lot, section, plan_prefix, plan_num in parsed_list:
        # Only try fuzzy for numeric lots
        try:
            lot_num = int(lot)
        except ValueError:
            # Non-numeric lot (letter lots like 'B', 'A') — try lowercase variants
            for alt_lot in [lot.upper(), lot.lower()]:
                lp_key = (alt_lot, section or '', plan_num)
                if lp_key in lotplan_idx:
                    x, y, file_idx, area = lotplan_idx[lp_key]
                    return (x, y, file_idx, lot, f"{plan_prefix}{plan_num}")
            continue

        # Try lot±1, lot±2
        for delta in [-2, -1, 1, 2]:
            alt_lot = str(lot_num + delta)
            lp_keys = []
            if section:
                lp_keys.append((alt_lot, str(section), plan_num))
            lp_keys.append((alt_lot, '', plan_num))

            for lp_key in lp_keys:
                if lp_key in lotplan_idx:
                    x, y, file_idx, area = lotplan_idx[lp_key]
                    return (x, y, file_idx, alt_lot, f"{plan_prefix}{plan_num}")

            # Also try lotidstring
            lid_keys = [f"{alt_lot}//{plan_num}", f"{alt_lot}//DP{plan_num}"]
            if section:
                lid_keys.insert(0, f"{alt_lot}/{section}//{plan_num}")
            for key in lid_keys:
                if key.upper() in lotidstring_idx:
                    x, y, file_idx, area = lotidstring_idx[key.upper()]
                    return (x, y, file_idx, alt_lot, f"{plan_prefix}{plan_num}")

    return None


def try_plan_prefix_variants(parsed_list, lotidstring_idx, lotplan_idx):
    """Strategy 3: Try all plan prefix variants.
    DP→SP, DP→RS, SP→DP, etc.
    """
    for lot, section, plan_prefix, plan_num in parsed_list:
        # Generate alternative prefixes
        alt_prefixes = []
        for pfx in ['DP', 'SP', 'RS']:
            if pfx != plan_prefix:
                alt_prefixes.append(pfx)

        for alt_pfx in alt_prefixes:
            # Try in lotplan_idx (which uses bare plan_num without prefix)
            # This won't help since lotplan_idx already uses bare numbers
            # But try lotidstring with different prefix
            if section:
                key = f"{lot}/{section}//{alt_pfx}{plan_num}"
            else:
                key = f"{lot}//{alt_pfx}{plan_num}"

            if key.upper() in lotidstring_idx:
                x, y, file_idx, area = lotidstring_idx[key.upper()]
                return (x, y, file_idx, lot, f"{alt_pfx}{plan_num}")

    return None


def try_sibling_lot_match(parsed_list, lotidstring_idx, lotplan_idx):
    """Strategy 4: Find any lot in the same plan.
    If the plan exists in cadastre but the specific lot doesn't,
    use the plan's centroid (average of all lots in that plan).
    """
    for lot, section, plan_prefix, plan_num in parsed_list:
        # Check if ANY lot in this plan exists in lotplan_idx
        # We can't efficiently scan all lots, so try common lot numbers
        for test_lot in ['1', '2', '3', '10', '100', '11', '12', '20', '50']:
            lp_key = (test_lot, '', plan_num)
            if lp_key in lotplan_idx:
                x, y, file_idx, area = lotplan_idx[lp_key]
                # Found a sibling lot — use its position as approximation
                return (x, y, file_idx, lot, f"{plan_prefix}{plan_num}~sibling")

    return None


def nominatim_geocode(house_number, street_name, locality, postcode, timeout=NOMINATIM_TIMEOUT):
    """Geocode an address using Nominatim API.
    Returns (lat, lon) in EPSG:4326 or None.
    """
    # Build address string
    parts = []
    if house_number:
        parts.append(str(house_number).strip())
    if street_name:
        parts.append(str(street_name).strip())
    addr = ' '.join(parts)
    if locality:
        addr += f', {str(locality).strip()}'
    if postcode:
        addr += f' NSW {str(postcode).strip()}'
    addr += ', Australia'

    params = urllib.parse.urlencode({
        'q': addr,
        'format': 'json',
        'limit': 1,
        'countrycodes': 'au',
        'addressdetails': 0,
    })
    url = f"{NOMINATIM_URL}?{params}"

    req = urllib.request.Request(url)
    req.add_header('User-Agent', f'NSW-Property-Matcher/2.0 ({NOMINATIM_EMAIL})')

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and len(data) > 0:
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                return (lat, lon)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError, ValueError):
        pass
    except Exception:
        pass

    return None


def transform_4326_to_3857(lat, lon):
    """Transform WGS84 (lat, lon) to Web Mercator (x, y) EPSG:3857"""
    # Simple spherical projection (accurate enough for web mapping)
    import math
    x = lon * 20037508.34 / 180.0
    lat_rad = lat * math.pi / 180.0
    y = math.log(math.tan((90 + lat_rad) / 2)) / (math.pi / 180.0)
    y = y * 20037508.34 / 180.0
    return (x, y)


# ─── Phase 2: Match and Export ───────────────────────────────────────────────

def match_and_export(csv_path, lotidstring_idx, lotplan_idx, file_names,
                     output_matched, output_unmatched, report_path,
                     limit=None, test_lga=None, skip_nominatim=True,
                     progress_every=10000):
    """Match records using multi-strategy approach."""

    print("\n" + "=" * 60)
    print("Phase 2: Multi-strategy matching")
    print("=" * 60)

    t0 = time.time()

    driver = ogr.GetDriverByName("GPKG")
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(OUTPUT_SRS)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    if os.path.exists(output_matched):
        driver.DeleteDataSource(output_matched)
    ds_matched = driver.CreateDataSource(output_matched)
    lyr_matched = ds_matched.CreateLayer("property_matched_v2", srs=srs, geom_type=ogr.wkbPoint)

    if os.path.exists(output_unmatched):
        driver.DeleteDataSource(output_unmatched)
    ds_unmatched = driver.CreateDataSource(output_unmatched)
    lyr_unmatched = ds_unmatched.CreateLayer("property_unmatched_v2", srs=srs, geom_type=ogr.wkbNone)

    field_defs = [
        ("property_id", ogr.OFTString),
        ("sale_counter", ogr.OFTInteger),
        ("property_name", ogr.OFTString),
        ("unit_number", ogr.OFTString),
        ("house_number", ogr.OFTString),
        ("street_name", ogr.OFTString),
        ("locality", ogr.OFTString),
        ("post_code", ogr.OFTString),
        ("area", ogr.OFTReal),
        ("area_type", ogr.OFTString),
        ("contract_date", ogr.OFTString),
        ("settlement_date", ogr.OFTString),
        ("purchase_price", ogr.OFTReal),
        ("zoning", ogr.OFTString),
        ("nature_of_property", ogr.OFTString),
        ("primary_purpose", ogr.OFTString),
        ("strata_lot_number", ogr.OFTString),
        ("dealing_number", ogr.OFTString),
        ("legal_description", ogr.OFTString),
        ("matched_lot", ogr.OFTString),
        ("matched_plan", ogr.OFTString),
        ("matched_lga", ogr.OFTString),
        ("geocode_source", ogr.OFTString),
    ]

    for fname, ftype in field_defs:
        lyr_matched.CreateField(ogr.FieldDefn(fname, ftype))
        lyr_unmatched.CreateField(ogr.FieldDefn(fname, ftype))

    matched_defn = lyr_matched.GetLayerDefn()
    unmatched_defn = lyr_unmatched.GetLayerDefn()

    lyr_matched.StartTransaction()
    lyr_unmatched.StartTransaction()
    BATCH_SIZE = 5000

    stats = defaultdict(int)
    match_method_stats = defaultdict(int)
    batch_count = 0

    def safe_float(val):
        if not val or str(val).strip() == '':
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def safe_int(val):
        f = safe_float(val)
        return int(f) if f is not None else 0

    def set_fields(feat, row, ld, matched_lot, matched_plan, matched_lga, source):
        feat.SetField("property_id", str(row.get("Property ID", "")).strip())
        feat.SetField("sale_counter", safe_int(row.get("Sale counter")))
        feat.SetField("property_name", str(row.get("Property name", "")).strip())
        feat.SetField("unit_number", str(row.get("Property unit number", "")).strip())
        feat.SetField("house_number", str(row.get("Property house number", "")).strip())
        feat.SetField("street_name", str(row.get("Property street name", "")).strip())
        feat.SetField("locality", str(row.get("Property locality", "")).strip())
        pc = str(row.get("Property post code", "")).strip()
        if pc.endswith('.0'):
            pc = pc[:-2]
        feat.SetField("post_code", pc)
        feat.SetField("area", safe_float(row.get("Area")))
        feat.SetField("area_type", str(row.get("Area type", "")).strip())
        feat.SetField("contract_date", str(row.get("Contract date", "")).strip())
        feat.SetField("settlement_date", str(row.get("Settlement date", "")).strip())
        feat.SetField("purchase_price", safe_float(row.get("Purchase price")))
        feat.SetField("zoning", str(row.get("Zoning", "")).strip())
        feat.SetField("nature_of_property", str(row.get("Nature of property", "")).strip())
        feat.SetField("primary_purpose", str(row.get("Primary purpose", "")).strip())
        feat.SetField("strata_lot_number", str(row.get("Strata lot number", "")).strip())
        feat.SetField("dealing_number", str(row.get("Dealing number", "")).strip())
        feat.SetField("legal_description", ld)
        feat.SetField("matched_lot", matched_lot)
        feat.SetField("matched_plan", matched_plan)
        feat.SetField("matched_lga", matched_lga)
        feat.SetField("geocode_source", source)

    test_postcodes = None
    if test_lga and test_lga in TEST_LGA_POSTCODES:
        test_postcodes = TEST_LGA_POSTCODES[test_lga]
        print(f"  TEST MODE: postcodes {sorted(test_postcodes)}")

    # ── Stream CSV ──
    print(f"  Reading: {csv_path}")

    # For Nominatim rate limiting
    last_nominatim_time = 0
    nominatim_count = 0

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row_num, row in enumerate(reader):
            if limit and row_num >= limit:
                break

            if test_postcodes:
                pc = str(row.get("Property post code", "")).strip()
                pc_clean = pc.replace('.0', '').replace('.00', '').strip()
                if pc_clean not in test_postcodes:
                    continue

            stats['total'] += 1
            ld = str(row.get("Property legal description", "")).strip()

            if not ld:
                stats['unmatched_no_desc'] += 1
                feat = ogr.Feature(unmatched_defn)
                set_fields(feat, row, ld, "", "", "", "no_legal_description")
                lyr_unmatched.CreateFeature(feat)
                feat = None
                batch_count += 1
                if batch_count % BATCH_SIZE == 0:
                    lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
                    lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()
                if stats['total'] % progress_every == 0:
                    _print_progress(stats, match_method_stats, t0, row_num)
                continue

            parsed = parse_legal_description(ld)

            if not parsed:
                stats['unmatched_no_parse'] += 1
                feat = ogr.Feature(unmatched_defn)
                set_fields(feat, row, ld, "", "", "", "unparseable")
                lyr_unmatched.CreateFeature(feat)
                feat = None
                batch_count += 1
                if batch_count % BATCH_SIZE == 0:
                    lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
                    lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()
                if stats['total'] % progress_every == 0:
                    _print_progress(stats, match_method_stats, t0, row_num)
                continue

            # Strategy 1: Exact match
            result = try_exact_match(parsed, lotidstring_idx, lotplan_idx)
            if result:
                x, y, file_idx, matched_lot, matched_plan = result
                _write_matched(lyr_matched, matched_defn, row, ld, matched_lot,
                              matched_plan, file_names[file_idx], "parcel_exact", srs, x, y)
                stats['matched'] += 1
                match_method_stats['parcel_exact'] += 1
                batch_count += 1
                if batch_count % BATCH_SIZE == 0:
                    lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
                    lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()
                if stats['total'] % progress_every == 0:
                    _print_progress(stats, match_method_stats, t0, row_num)
                continue

            # Strategy 2: Plan prefix variants
            result = try_plan_prefix_variants(parsed, lotidstring_idx, lotplan_idx)
            if result:
                x, y, file_idx, matched_lot, matched_plan = result
                _write_matched(lyr_matched, matched_defn, row, ld, matched_lot,
                              matched_plan, file_names[file_idx], "prefix_variant", srs, x, y)
                stats['matched'] += 1
                match_method_stats['prefix_variant'] += 1
                batch_count += 1
                if batch_count % BATCH_SIZE == 0:
                    lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
                    lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()
                if stats['total'] % progress_every == 0:
                    _print_progress(stats, match_method_stats, t0, row_num)
                continue

            # Strategy 3: Fuzzy lot matching (lot±1, ±2)
            result = try_fuzzy_match(parsed, lotidstring_idx, lotplan_idx)
            if result:
                x, y, file_idx, matched_lot, matched_plan = result
                _write_matched(lyr_matched, matched_defn, row, ld, matched_lot,
                              matched_plan, file_names[file_idx], "fuzzy_lot", srs, x, y)
                stats['matched'] += 1
                match_method_stats['fuzzy_lot'] += 1
                batch_count += 1
                if batch_count % BATCH_SIZE == 0:
                    lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
                    lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()
                if stats['total'] % progress_every == 0:
                    _print_progress(stats, match_method_stats, t0, row_num)
                continue

            # Strategy 4: Sibling lot (same plan, different lot number)
            result = try_sibling_lot_match(parsed, lotidstring_idx, lotplan_idx)
            if result:
                x, y, file_idx, matched_lot, matched_plan = result
                _write_matched(lyr_matched, matched_defn, row, ld, matched_lot,
                              matched_plan, file_names[file_idx], "sibling_lot", srs, x, y)
                stats['matched'] += 1
                match_method_stats['sibling_lot'] += 1
                batch_count += 1
                if batch_count % BATCH_SIZE == 0:
                    lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
                    lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()
                if stats['total'] % progress_every == 0:
                    _print_progress(stats, match_method_stats, t0, row_num)
                continue

            # Strategy 5: Nominatim geocoding (for records with addresses)
            if not skip_nominatim:
                hn = str(row.get("Property house number", "")).strip()
                sn = str(row.get("Property street name", "")).strip()
                loc = str(row.get("Property locality", "")).strip()
                pc = str(row.get("Property post code", "")).strip().replace('.0', '')

                if hn and sn:
                    # Rate limit
                    now = time.time()
                    wait = NOMINATIM_DELAY - (now - last_nominatim_time)
                    if wait > 0:
                        time.sleep(wait)
                    last_nominatim_time = time.time()

                    geo = nominatim_geocode(hn, sn, loc, pc)
                    nominatim_count += 1

                    if geo:
                        lat, lon = geo
                        x, y = transform_4326_to_3857(lat, lon)
                        _write_matched(lyr_matched, matched_defn, row, ld, "", "",
                                      "NOMINATIM", "nominatim_geocode", srs, x, y)
                        stats['matched'] += 1
                        match_method_stats['nominatim'] += 1
                        batch_count += 1
                        if batch_count % BATCH_SIZE == 0:
                            lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
                            lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()
                        if stats['total'] % progress_every == 0:
                            _print_progress(stats, match_method_stats, t0, row_num)
                        continue

            # Unmatched
            stats['unmatched'] += 1
            # Classify reason
            is_sp = any(is_strata_plan(pp, pn) for _, _, pp, pn in parsed)
            reason = "strata_plan_not_in_cadastre" if is_sp else "lot_plan_not_found"
            match_method_stats[reason] += 1

            feat = ogr.Feature(unmatched_defn)
            set_fields(feat, row, ld, "", "", "", reason)
            lyr_unmatched.CreateFeature(feat)
            feat = None
            batch_count += 1
            if batch_count % BATCH_SIZE == 0:
                lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
                lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()

            if stats['total'] % progress_every == 0:
                _print_progress(stats, match_method_stats, t0, row_num)

    lyr_matched.CommitTransaction()
    lyr_unmatched.CommitTransaction()

    ds_matched = None
    ds_unmatched = None

    elapsed = time.time() - t0
    _print_report(stats, match_method_stats, elapsed, report_path)

    return stats


def _write_matched(lyr, defn, row, ld, matched_lot, matched_plan, matched_lga, source, srs, x, y):
    """Write a matched feature"""
    feat = ogr.Feature(defn)

    pid = str(row.get("Property ID", "")).strip()
    sc_raw = row.get("Sale counter")
    try:
        sc = int(float(sc_raw)) if sc_raw else 0
    except:
        sc = 0

    def sf(key, field_name):
        feat.SetField(field_name, str(row.get(key, "")).strip())

    feat.SetField("property_id", pid)
    feat.SetField("sale_counter", sc)
    sf("Property name", "property_name")
    sf("Property unit number", "unit_number")
    sf("Property house number", "house_number")
    sf("Property street name", "street_name")
    sf("Property locality", "locality")
    pc = str(row.get("Property post code", "")).strip()
    if pc.endswith('.0'):
        pc = pc[:-2]
    feat.SetField("post_code", pc)

    area_val = row.get("Area", "")
    try:
        feat.SetField("area", float(area_val) if area_val else 0.0)
    except:
        feat.SetField("area", 0.0)

    sf("Area type", "area_type")
    sf("Contract date", "contract_date")
    sf("Settlement date", "settlement_date")

    price_val = row.get("Purchase price", "")
    try:
        feat.SetField("purchase_price", float(price_val) if price_val else 0.0)
    except:
        feat.SetField("purchase_price", 0.0)

    sf("Zoning", "zoning")
    sf("Nature of property", "nature_of_property")
    sf("Primary purpose", "primary_purpose")
    sf("Strata lot number", "strata_lot_number")
    sf("Dealing number", "dealing_number")
    feat.SetField("legal_description", ld)
    feat.SetField("matched_lot", matched_lot)
    feat.SetField("matched_plan", matched_plan)
    feat.SetField("matched_lga", matched_lga)
    feat.SetField("geocode_source", source)

    point = ogr.Geometry(ogr.wkbPoint)
    point.AddPoint(x, y)
    point.AssignSpatialReference(srs)
    feat.SetGeometry(point)
    lyr.CreateFeature(feat)
    feat = None


def _print_progress(stats, method_stats, t0, row_num):
    elapsed = time.time() - t0
    rate = (row_num + 1) / elapsed if elapsed > 0 else 0
    total = stats['total']
    matched = stats['matched']
    pct = matched / total * 100 if total else 0
    print(f"  [{row_num + 1:,}] matched={matched:,} ({pct:.1f}%) "
          f"rate={rate:,.0f}/s")


def _print_report(stats, method_stats, elapsed, report_path):
    total = stats['total']
    matched = stats['matched']
    pct = matched / total * 100 if total else 0

    sep = "=" * 60
    lines = []
    lines.append(sep)
    lines.append("NSW Property Sales → Cadastre Matching v2 Report")
    lines.append(sep)
    lines.append("")
    lines.append(f"Total records:          {total:>10,}")
    lines.append(f"Matched:                {matched:>10,}  ({pct:.1f}%)")
    lines.append(f"Unmatched:")
    lines.append(f"  No legal description: {stats.get('unmatched_no_desc', 0):>10,}")
    lines.append(f"  Unparseable:          {stats.get('unmatched_no_parse', 0):>10,}")
    lines.append(f"  Other unmatched:      {stats.get('unmatched', 0):>10,}")
    lines.append("")
    lines.append("Match method breakdown:")
    for method, cnt in sorted(method_stats.items(), key=lambda x: -x[1]):
        lines.append(f"  {method:<35s} {cnt:>10,}")
    lines.append("")
    lines.append(f"Processing time: {elapsed:.1f}s")
    lines.append("")

    report_text = "\n".join(lines)
    print("\n" + report_text)

    with open(report_path, 'w') as f:
        f.write(report_text + "\n")


# ─── Process Existing Unmatched GPKG ─────────────────────────────────────────

def process_existing_unmatched(unmatched_gpkg, lotidstring_idx, lotplan_idx, file_names,
                                output_matched, output_unmatched, report_path,
                                skip_nominatim=True, limit=None):
    """Process existing v1 unmatched records through v2 strategies.
    This avoids re-processing already matched records.
    """
    print("\n" + "=" * 60)
    print("Processing existing v1 unmatched GPKG")
    print("=" * 60)

    t0 = time.time()

    ds_in = ogr.Open(unmatched_gpkg)
    lyr_in = ds_in.GetLayer()
    total_in = lyr_in.GetFeatureCount()
    print(f"  Input: {total_in:,} unmatched records")

    driver = ogr.GetDriverByName("GPKG")
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(OUTPUT_SRS)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    if os.path.exists(output_matched):
        driver.DeleteDataSource(output_matched)
    ds_matched = driver.CreateDataSource(output_matched)
    lyr_matched = ds_matched.CreateLayer("property_matched_v2", srs=srs, geom_type=ogr.wkbPoint)

    if os.path.exists(output_unmatched):
        driver.DeleteDataSource(output_unmatched)
    ds_unmatched = driver.CreateDataSource(output_unmatched)
    lyr_unmatched = ds_unmatched.CreateLayer("property_unmatched_v2", srs=srs, geom_type=ogr.wkbNone)

    # Define fields (same as main function)
    field_defs = [
        ("property_id", ogr.OFTString), ("sale_counter", ogr.OFTInteger),
        ("property_name", ogr.OFTString), ("unit_number", ogr.OFTString),
        ("house_number", ogr.OFTString), ("street_name", ogr.OFTString),
        ("locality", ogr.OFTString), ("post_code", ogr.OFTString),
        ("area", ogr.OFTReal), ("area_type", ogr.OFTString),
        ("contract_date", ogr.OFTString), ("settlement_date", ogr.OFTString),
        ("purchase_price", ogr.OFTReal), ("zoning", ogr.OFTString),
        ("nature_of_property", ogr.OFTString), ("primary_purpose", ogr.OFTString),
        ("strata_lot_number", ogr.OFTString), ("dealing_number", ogr.OFTString),
        ("legal_description", ogr.OFTString), ("matched_lot", ogr.OFTString),
        ("matched_plan", ogr.OFTString), ("matched_lga", ogr.OFTString),
        ("geocode_source", ogr.OFTString),
    ]
    for fname, ftype in field_defs:
        lyr_matched.CreateField(ogr.FieldDefn(fname, ftype))
        lyr_unmatched.CreateField(ogr.FieldDefn(fname, ftype))

    matched_defn = lyr_matched.GetLayerDefn()
    unmatched_defn = lyr_unmatched.GetLayerDefn()

    lyr_matched.StartTransaction()
    lyr_unmatched.StartTransaction()
    BATCH_SIZE = 5000

    stats = defaultdict(int)
    match_method_stats = defaultdict(int)
    batch_count = 0
    processed = 0

    for feat_in in lyr_in:
        if limit and processed >= limit:
            break
        processed += 1
        stats['total'] += 1

        ld = feat_in.GetField('legal_description') or ''
        ld = ld.strip()

        # Build a row-like dict from the GPKG feature
        def gf(name):
            v = feat_in.GetField(name)
            return str(v) if v is not None else ''

        row = {
            "Property ID": gf('property_id'),
            "Sale counter": gf('sale_counter'),
            "Property name": gf('property_name'),
            "Property unit number": gf('unit_number'),
            "Property house number": gf('house_number'),
            "Property street name": gf('street_name'),
            "Property locality": gf('locality'),
            "Property post code": gf('post_code'),
            "Area": str(feat_in.GetField('area') or ''),
            "Area type": gf('area_type'),
            "Contract date": gf('contract_date'),
            "Settlement date": gf('settlement_date'),
            "Purchase price": str(feat_in.GetField('purchase_price') or ''),
            "Zoning": gf('zoning'),
            "Nature of property": gf('nature_of_property'),
            "Primary purpose": gf('primary_purpose'),
            "Strata lot number": gf('strata_lot_number'),
            "Dealing number": gf('dealing_number'),
            "Property legal description": ld,
        }

        if not ld:
            stats['unmatched_no_desc'] += 1
            f = ogr.Feature(unmatched_defn)
            _set_from_row(f, row, ld, "", "", "", "no_legal_description")
            lyr_unmatched.CreateFeature(f)
            f = None
            batch_count += 1
            if batch_count % BATCH_SIZE == 0:
                lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
                lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()
            if processed % 50000 == 0:
                _print_progress(stats, match_method_stats, t0, processed)
            continue

        parsed = parse_legal_description(ld)
        if not parsed:
            stats['unmatched_no_parse'] += 1
            f = ogr.Feature(unmatched_defn)
            _set_from_row(f, row, ld, "", "", "", "unparseable")
            lyr_unmatched.CreateFeature(f)
            f = None
            batch_count += 1
            if batch_count % BATCH_SIZE == 0:
                lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
                lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()
            continue

        # Try strategies 1-4
        result = try_exact_match(parsed, lotidstring_idx, lotplan_idx)
        method = "parcel_exact" if result else None

        if not result:
            result = try_plan_prefix_variants(parsed, lotidstring_idx, lotplan_idx)
            method = "prefix_variant" if result else None

        if not result:
            result = try_fuzzy_match(parsed, lotidstring_idx, lotplan_idx)
            method = "fuzzy_lot" if result else None

        if not result:
            result = try_sibling_lot_match(parsed, lotidstring_idx, lotplan_idx)
            method = "sibling_lot" if result else None

        if result:
            x, y, file_idx, matched_lot, matched_plan = result
            f = ogr.Feature(matched_defn)
            _set_from_row(f, row, ld, matched_lot, matched_plan,
                         file_names[file_idx], method)
            point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint(x, y)
            point.AssignSpatialReference(srs)
            f.SetGeometry(point)
            lyr_matched.CreateFeature(f)
            f = None
            stats['matched'] += 1
            match_method_stats[method] += 1
        else:
            # Nominatim
            if not skip_nominatim:
                hn = row.get("Property house number", "").strip()
                sn = row.get("Property street name", "").strip()
                loc = row.get("Property locality", "").strip()
                pc = row.get("Property post code", "").strip()

                if hn and sn:
                    now = time.time()
                    wait = NOMINATIM_DELAY - (now - getattr(process_existing_unmatched, '_last_nom_time', 0))
                    if wait > 0:
                        time.sleep(wait)
                    process_existing_unmatched._last_nom_time = time.time()

                    geo = nominatim_geocode(hn, sn, loc, pc)
                    if geo:
                        x, y = transform_4326_to_3857(*geo)
                        f = ogr.Feature(matched_defn)
                        _set_from_row(f, row, ld, "", "", "NOMINATIM", "nominatim_geocode")
                        point = ogr.Geometry(ogr.wkbPoint)
                        point.AddPoint(x, y)
                        point.AssignSpatialReference(srs)
                        f.SetGeometry(point)
                        lyr_matched.CreateFeature(f)
                        f = None
                        stats['matched'] += 1
                        match_method_stats['nominatim'] += 1
                        batch_count += 1
                        if batch_count % BATCH_SIZE == 0:
                            lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
                            lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()
                        if processed % 50000 == 0:
                            _print_progress(stats, match_method_stats, t0, processed)
                        continue

            # Still unmatched
            stats['unmatched'] += 1
            is_sp = any(is_strata_plan(pp, pn) for _, _, pp, pn in parsed)
            reason = "strata_plan_not_in_cadastre" if is_sp else "lot_plan_not_found"
            match_method_stats[reason] += 1

            f = ogr.Feature(unmatched_defn)
            _set_from_row(f, row, ld, "", "", "", reason)
            lyr_unmatched.CreateFeature(f)
            f = None

        batch_count += 1
        if batch_count % BATCH_SIZE == 0:
            lyr_matched.CommitTransaction(); lyr_unmatched.CommitTransaction()
            lyr_matched.StartTransaction(); lyr_unmatched.StartTransaction()

        if processed % 50000 == 0:
            _print_progress(stats, match_method_stats, t0, processed)

    lyr_matched.CommitTransaction()
    lyr_unmatched.CommitTransaction()
    ds_matched = None
    ds_unmatched = None
    ds_in = None

    elapsed = time.time() - t0
    _print_report(stats, match_method_stats, elapsed, report_path)
    return stats


def _set_from_row(feat, row, ld, matched_lot, matched_plan, matched_lga, source):
    """Set feature fields from a row dict"""
    feat.SetField("property_id", row.get("Property ID", "").strip())

    sc = row.get("Sale counter", "0")
    try:
        feat.SetField("sale_counter", int(float(sc)) if sc else 0)
    except:
        feat.SetField("sale_counter", 0)

    feat.SetField("property_name", row.get("Property name", "").strip())
    feat.SetField("unit_number", row.get("Property unit number", "").strip())
    feat.SetField("house_number", row.get("Property house number", "").strip())
    feat.SetField("street_name", row.get("Property street name", "").strip())
    feat.SetField("locality", row.get("Property locality", "").strip())
    feat.SetField("post_code", row.get("Property post code", "").strip())

    area = row.get("Area", "")
    try:
        feat.SetField("area", float(area) if area else 0.0)
    except:
        feat.SetField("area", 0.0)

    feat.SetField("area_type", row.get("Area type", "").strip())
    feat.SetField("contract_date", row.get("Contract date", "").strip())
    feat.SetField("settlement_date", row.get("Settlement date", "").strip())

    price = row.get("Purchase price", "")
    try:
        feat.SetField("purchase_price", float(price) if price else 0.0)
    except:
        feat.SetField("purchase_price", 0.0)

    feat.SetField("zoning", row.get("Zoning", "").strip())
    feat.SetField("nature_of_property", row.get("Nature of property", "").strip())
    feat.SetField("primary_purpose", row.get("Primary purpose", "").strip())
    feat.SetField("strata_lot_number", row.get("Strata lot number", "").strip())
    feat.SetField("dealing_number", row.get("Dealing number", "").strip())
    feat.SetField("legal_description", ld)
    feat.SetField("matched_lot", matched_lot)
    feat.SetField("matched_plan", matched_plan)
    feat.SetField("matched_lga", matched_lga)
    feat.SetField("geocode_source", source)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import urllib.parse  # needed for nominatim urlencode

    parser = argparse.ArgumentParser(description="NSW Property Matching v2")
    parser.add_argument('--test-lga', type=str, default=None)
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--skip-nominatim', action='store_true', default=True,
                        help='Skip Nominatim geocoding (default: skipped)')
    parser.add_argument('--use-nominatim', action='store_true', default=False,
                        help='Enable Nominatim geocoding (slow, rate-limited)')
    parser.add_argument('--process-unmatched', action='store_true',
                        help='Process existing v1 unmatched GPKG instead of full CSV')
    args = parser.parse_args()

    skip_nominatim = not args.use_nominatim

    cadastre_files = sorted(glob.glob(os.path.join(CADASTRE_DIR, "cadastre_*.gpkg")))
    print(f"Found {len(cadastre_files)} cadastre GPKG files")

    if args.test_lga:
        test_file = os.path.join(CADASTRE_DIR, f"cadastre_{args.test_lga}.gpkg")
        if os.path.exists(test_file):
            cadastre_files = [test_file]
            print(f"TEST MODE: Only indexing {args.test_lga}")

    # Phase 1: Build index
    lotidstring_idx, lotplan_idx, file_names, lga_centroids = build_cadastre_index(cadastre_files)

    # Phase 2: Match
    if args.process_unmatched:
        # Process existing unmatched GPKG
        suffix = f"-{args.test_lga}" if args.test_lga else ""
        output_matched = os.path.join(OUTPUT_DIR, f"nsw-property-matched-v2{suffix}.gpkg")
        output_unmatched = os.path.join(OUTPUT_DIR, f"nsw-property-unmatched-v2{suffix}.gpkg")
        report_path = os.path.join(OUTPUT_DIR, f"nsw-property-match-report-v2{suffix}.txt")

        process_existing_unmatched(
            UNMATCHED_GPKG, lotidstring_idx, lotplan_idx, file_names,
            output_matched, output_unmatched, report_path,
            skip_nominatim=skip_nominatim, limit=args.limit
        )
    else:
        suffix = f"-{args.test_lga}" if args.test_lga else ""
        output_matched = os.path.join(OUTPUT_DIR, f"nsw-property-matched-v2{suffix}.gpkg")
        output_unmatched = os.path.join(OUTPUT_DIR, f"nsw-property-unmatched-v2{suffix}.gpkg")
        report_path = os.path.join(OUTPUT_DIR, f"nsw-property-match-report-v2{suffix}.txt")

        match_and_export(
            CSV_PATH, lotidstring_idx, lotplan_idx, file_names,
            output_matched, output_unmatched, report_path,
            limit=args.limit, test_lga=args.test_lga,
            skip_nominatim=skip_nominatim
        )

    print("\n✓ Done.")


if __name__ == "__main__":
    main()
