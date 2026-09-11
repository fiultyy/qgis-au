#!/usr/bin/env python3
"""
NSW Property Sales → Cadastre Parcel Matching (Full NSW)
=========================================================
Matches 2.2M NSW property sales records against 132 LGA cadastre GPKPs
using lot/plan number matching.

Strategy:
  Phase 1: Scan all 132 GPKPs, build global index {lotidstring → (x, y, file_idx)}
           Pre-compute PointOnSurface for every cadastre polygon.
  Phase 2: Stream CSV, parse legal_description, look up in index, write output.

Output:
  - nsw-property-matched.gpkg    (parcel-level PointOnSurface, EPSG:3857)
  - nsw-property-unmatched.gpkg  (attributes only, no geometry)
  - nsw-property-match-report.txt

Usage:
  python3 nsw_property_match.py                  # full run
  python3 nsw_property_match.py --test-lga COFFS_HARBOUR   # single LGA test
  python3 nsw_property_match.py --limit 100000   # limit CSV rows
"""

import csv
import re
import os
import sys
import time
import glob
import argparse
from collections import defaultdict
from osgeo import ogr, osr

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# ─── Configuration ────────────────────────────────────────────────────────────

CSV_PATH = "/home/yy/qgis-data/coffs-harbour/nsw-property-sales-data-updated20260721.csv"
CADASTRE_DIR = "/home/yy/qgis-data/cadastre"
OUTPUT_DIR = "/home/yy/qgis-data"
REPORT_PATH = os.path.join(OUTPUT_DIR, "nsw-property-match-report.txt")

OUTPUT_SRS = 3857  # Web Mercator (same as cadastre GPKPs)

# Test-LGA → postcode mapping for CSV filtering in test mode
# Only used when --test-lga is specified, to avoid scanning 2.2M rows
TEST_LGA_POSTCODES = {
    'COFFS_HARBOUR': {'2450', '2452', '2453', '2454', '2455', '2456', '2460'},
}

# ─── Legal Description Parser ─────────────────────────────────────────────────

def parse_legal_description(desc):
    """Parse a NSW property legal description into a list of parcel tuples.

    Each tuple is (lot, section_or_None, plan_prefix, plan_number).

    Handles:
      - lot/plan:           "6/255079"
      - lot/SPplan:         "5/SP36793"
      - multi-lot/plan:     "200, 201/1183461"
      - lot/section/plan:   "1/5/11100" or "14/A/17053"
      - multi-parcel:       "1/211950 5/1232772"
      - PT prefix:          "PT 106/1252949"
      - letter lots:        "B/367420"
      - complex multi:      "45, 46/2/2149"
    """
    if not desc or not desc.strip():
        return []

    desc = desc.strip()

    # Remove PT (part lot) prefix
    desc = re.sub(r'\bPT\s+', '', desc, flags=re.I)

    # Normalize: remove space after comma so "45, 46" → "45,46"
    desc = re.sub(r',\s+', ',', desc)

    results = []
    # Split into parcels by whitespace
    parcels = desc.split()

    for parcel in parcels:
        parcel = parcel.strip().strip(',')
        if not parcel:
            continue

        slash_count = parcel.count('/')

        if slash_count == 1:
            # Format: lot/plan or lot/SPplan
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
            # Format: lot/section/plan
            parts = parcel.split('/')
            if len(parts) != 3:
                continue
            lot_str = parts[0].strip()
            section = parts[1].strip()
            plan_str = parts[2].strip()

            plan_prefix, plan_num = _parse_plan(plan_str)
            if plan_num is None:
                continue

            for lot in lot_str.split(','):
                lot = lot.strip()
                if lot:
                    results.append((lot, section, plan_prefix, plan_num))
        else:
            # No slash or too many – skip
            continue

    return results


def _parse_plan(plan_str):
    """Extract (prefix, number) from plan string. Returns ('DP', '123456') or ('SP', '789')."""
    plan_str = plan_str.strip()
    m = re.match(r'^(SP|DP|RS)(\d+)$', plan_str, re.I)
    if m:
        return m.group(1).upper(), m.group(2)
    # Bare number → assume DP
    if re.match(r'^\d+$', plan_str):
        return 'DP', plan_str
    return None, None


# ─── Phase 1: Build Cadastre Index ────────────────────────────────────────────

def build_cadastre_index(cadastre_files, progress_every=50000):
    """Scan all cadastre GPKPs and build a global lookup index.

    Returns:
      lotidstring_idx: {lotidstring_upper: (x, y, file_idx, area)}
      lotplan_idx: {(lot_str, section_or_empty, plan_str): (x, y, file_idx, area)}
      file_names: list of basenames
      stats: dict with counts
    """
    print("\n" + "=" * 60)
    print("Phase 1: Building global cadastre index")
    print("=" * 60)

    t0 = time.time()

    lotidstring_idx = {}      # lotidstring → (x, y, file_idx, area)
    lotplan_idx = {}           # (lot, section, plan) → (x, y, file_idx, area)
    file_names = []

    total_features = 0
    total_with_geom = 0
    total_indexed = 0
    skipped_no_geom = 0
    skipped_no_lotid = 0

    for file_idx, gpkg_path in enumerate(cadastre_files):
        lga_name = os.path.basename(gpkg_path).replace('cadastre_', '').replace('.gpkg', '')
        file_names.append(lga_name)

        ds = ogr.Open(gpkg_path)
        if ds is None:
            print(f"  WARNING: Cannot open {gpkg_path}")
            continue
        layer = ds.GetLayer()
        count = layer.GetFeatureCount()

        file_features = 0
        file_indexed = 0

        for feat in layer:
            total_features += 1
            file_features += 1

            if total_features % progress_every == 0:
                elapsed = time.time() - t0
                rate = total_features / elapsed if elapsed > 0 else 0
                print(f"  Processed {total_features:,} features "
                      f"({rate:,.0f}/s, {len(lotidstring_idx):,} indexed, "
                      f"file {file_idx + 1}/{len(cadastre_files)})")

            # Get geometry → compute PointOnSurface
            geom = feat.GetGeometryRef()
            if geom is None:
                skipped_no_geom += 1
                continue
            total_with_geom += 1

            try:
                point = geom.PointOnSurface()
            except Exception:
                try:
                    point = geom.Centroid()
                except Exception:
                    skipped_no_geom += 1
                    continue

            if point is None:
                skipped_no_geom += 1
                continue

            px, py = point.GetX(), point.GetY()
            area = feat.GetField('planlotarea') or 0.0

            # Build lotidstring index
            lotidstring = feat.GetField('lotidstring')
            if lotidstring and lotidstring.strip():
                key = lotidstring.strip().upper()
                if key not in lotidstring_idx:
                    lotidstring_idx[key] = (px, py, file_idx, area)
                    total_indexed += 1
                    file_indexed += 1

                # Also build a normalized key without prefix
                # e.g. "2//DP370129" → also store "2//370129"
                m = re.match(r'^(.+?)//(.+)$', key)
                if m:
                    lot_part = m.group(1)
                    plan_part = m.group(2)
                    # Strip DP/SP prefix from plan for a secondary key
                    pm = re.match(r'^(?:DP|SP|RS)(\d+)$', plan_part)
                    if pm:
                        bare_key = f"{lot_part}//{pm.group(1)}"
                        if bare_key not in lotidstring_idx:
                            lotidstring_idx[bare_key] = (px, py, file_idx, area)

                # Also handle section format: "18/76/DP758258"
                m2 = re.match(r'^(.+?)/(.+?)/(?:DP|SP|RS)(\d+)$', key)
                if m2:
                    lot_p, sec_p, plan_p = m2.group(1), m2.group(2), m2.group(3)
                    bare_key2 = f"{lot_p}/{sec_p}//{plan_p}"
                    if bare_key2 not in lotidstring_idx:
                        lotidstring_idx[bare_key2] = (px, py, file_idx, area)

            else:
                skipped_no_lotid += 1

            # Build (lot, section, plan) index
            lotnumber = feat.GetField('lotnumber')
            sectionnumber = feat.GetField('sectionnumber')
            plannumber = feat.GetField('plannumber')

            if lotnumber is not None and plannumber is not None:
                lot_str = str(lotnumber).strip()
                sec_str = str(sectionnumber).strip() if sectionnumber else ''
                plan_str = str(plannumber).strip()
                lp_key = (lot_str, sec_str, plan_str)
                if lp_key not in lotplan_idx:
                    lotplan_idx[lp_key] = (px, py, file_idx, area)

                # Also store without section
                lp_key_nosec = (lot_str, '', plan_str)
                if lp_key_nosec not in lotplan_idx:
                    lotplan_idx[lp_key_nosec] = (px, py, file_idx, area)

            # Clear geometry reference to free memory
            feat = None

        ds = None
        print(f"  [{file_idx + 1}/{len(cadastre_files)}] {lga_name}: "
              f"{file_features:,} features, {file_indexed:,} indexed")

    elapsed = time.time() - t0
    print(f"\nPhase 1 complete: {total_features:,} features scanned in {elapsed:.1f}s")
    print(f"  lotidstring index: {len(lotidstring_idx):,} entries")
    print(f"  lotplan index:     {len(lotplan_idx):,} entries")
    print(f"  Skipped (no geom): {skipped_no_geom:,}")
    print(f"  Skipped (no lotid): {skipped_no_lotid:,}")

    stats = {
        'total_features': total_features,
        'total_with_geom': total_with_geom,
        'total_indexed': total_indexed,
        'skipped_no_geom': skipped_no_geom,
        'skipped_no_lotid': skipped_no_lotid,
        'build_time': elapsed,
    }

    return lotidstring_idx, lotplan_idx, file_names, stats


# ─── Phase 2: Match CSV and Write Output ──────────────────────────────────────

def match_and_export(csv_path, lotidstring_idx, lotplan_idx, file_names,
                     output_matched, output_unmatched, report_path,
                     limit=None, test_lga=None, progress_every=10000):
    """Match CSV records against cadastre index and write output GPKGs."""

    print("\n" + "=" * 60)
    print("Phase 2: Matching CSV records and writing output")
    print("=" * 60)

    t0 = time.time()

    # Create output datasources
    driver = ogr.GetDriverByName("GPKG")
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(OUTPUT_SRS)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    # ── Matched output ──
    if os.path.exists(output_matched):
        driver.DeleteDataSource(output_matched)
    ds_matched = driver.CreateDataSource(output_matched)
    lyr_matched = ds_matched.CreateLayer("property_matched", srs=srs, geom_type=ogr.wkbPoint)

    # ── Unmatched output ──
    if os.path.exists(output_unmatched):
        driver.DeleteDataSource(output_unmatched)
    ds_unmatched = driver.CreateDataSource(output_unmatched)
    lyr_unmatched = ds_unmatched.CreateLayer("property_unmatched", srs=srs, geom_type=ogr.wkbNone)

    # Define output fields
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

    # Start transactions for batch writes (huge speedup for GPKG/SQLite)
    lyr_matched.StartTransaction()
    lyr_unmatched.StartTransaction()
    BATCH_SIZE = 5000

    # Statistics
    stats = defaultdict(int)
    lga_stats = defaultdict(lambda: {'total': 0, 'matched': 0})
    unmatched_reasons = defaultdict(int)
    batch_count = 0

    # ── Helpers ──
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
        # Clean up post code (CSV has "2450.0" format)
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

    # ── Match function ──
    def try_match(parsed_list, lotidstring_idx, lotplan_idx):
        """Try to match parsed legal description against cadastre index.
        Returns (x, y, file_idx, matched_lot, matched_plan) or None.

        Multi-strategy approach (mirrors v2 script):
          1. (lot, plan_num) tuple lookup — most reliable
          2. lotidstring lookup with all prefix variants (DP, SP, RS, bare)
        """
        for lot, section, plan_prefix, plan_num in parsed_list:
            # Strategy 1: (lot, plan_num) tuple lookup — no prefix needed
            lp_keys = []
            if section:
                lp_keys.append((lot, str(section), plan_num))
            lp_keys.append((lot, '', plan_num))

            for lp_key in lp_keys:
                if lp_key in lotplan_idx:
                    x, y, file_idx, area = lotplan_idx[lp_key]
                    return (x, y, file_idx, lot, f"{plan_prefix}{plan_num}")

            # Strategy 2: lotidstring lookup with multiple prefix variants
            # Try the parsed prefix first, then fall back to all others
            if section:
                base_keys = [
                    f"{lot}/{section}//{plan_prefix}{plan_num}",
                    f"{lot}/{section}//{plan_num}",
                ]
            else:
                # Try parsed prefix, then all alternatives
                all_prefixes = [plan_prefix] if plan_prefix else []
                # Add alternative prefixes
                for alt_pfx in ('DP', 'SP', 'RS'):
                    if alt_pfx not in all_prefixes:
                        all_prefixes.append(alt_pfx)

                base_keys = []
                for pfx in all_prefixes:
                    base_keys.append(f"{lot}//{pfx}{plan_num}")
                # Also try bare number (no prefix)
                base_keys.append(f"{lot}//{plan_num}")

            for key in base_keys:
                key_upper = key.upper()
                if key_upper in lotidstring_idx:
                    x, y, file_idx, area = lotidstring_idx[key_upper]
                    plan_display = f"{plan_prefix}{plan_num}"
                    return (x, y, file_idx, lot, plan_display)

        return None

    # Pre-compute postcode filter for test mode
    test_postcodes = None
    if test_lga and test_lga in TEST_LGA_POSTCODES:
        test_postcodes = TEST_LGA_POSTCODES[test_lga]
        print(f"  TEST MODE: Filtering CSV to postcodes {sorted(test_postcodes)}")

    # ── Stream CSV ──
    print(f"  Reading CSV: {csv_path}")

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row_num, row in enumerate(reader):
            if limit and row_num >= limit:
                break

            # Test-mode postcode filter (skip non-matching records entirely)
            if test_postcodes:
                pc = str(row.get("Property post code", "")).strip()
                # Handle "2450.0" format in CSV
                pc_clean = pc.rstrip('.0') if pc.endswith('.0') else pc
                pc_clean = pc_clean.replace('.00', '').strip()
                if pc_clean not in test_postcodes:
                    continue

            stats['total'] += 1

            # Determine locality for LGA stats
            locality = str(row.get("Property locality", "")).strip().upper()
            pc = str(row.get("Property post code", "")).strip()

            ld = str(row.get("Property legal description", "")).strip()

            if not ld:
                stats['unmatched_no_desc'] += 1
                unmatched_reasons['no_legal_description'] += 1
                feat = ogr.Feature(unmatched_defn)
                set_fields(feat, row, ld, "", "", "", "no_legal_description")
                lyr_unmatched.CreateFeature(feat)
                feat = None
                batch_count += 1
                if batch_count % BATCH_SIZE == 0:
                    lyr_matched.CommitTransaction()
                    lyr_unmatched.CommitTransaction()
                    lyr_matched.StartTransaction()
                    lyr_unmatched.StartTransaction()
                if stats['total'] % progress_every == 0:
                    _print_progress(stats, t0, row_num)
                continue

            parsed = parse_legal_description(ld)

            if not parsed:
                stats['unmatched_no_parse'] += 1
                unmatched_reasons['unparseable'] += 1
                feat = ogr.Feature(unmatched_defn)
                set_fields(feat, row, ld, "", "", "", "unparseable")
                lyr_unmatched.CreateFeature(feat)
                feat = None
                batch_count += 1
                if batch_count % BATCH_SIZE == 0:
                    lyr_matched.CommitTransaction()
                    lyr_unmatched.CommitTransaction()
                    lyr_matched.StartTransaction()
                    lyr_unmatched.StartTransaction()
                if stats['total'] % progress_every == 0:
                    _print_progress(stats, t0, row_num)
                continue

            result = try_match(parsed, lotidstring_idx, lotplan_idx)

            if result:
                x, y, file_idx, matched_lot, matched_plan = result
                matched_lga = file_names[file_idx]

                # Test LGA filter (when full index built but testing one LGA)
                if test_lga and matched_lga != test_lga:
                    # Still count it but don't write
                    stats['skipped_other_lga'] = stats.get('skipped_other_lga', 0) + 1
                    continue

                stats['matched'] += 1
                lga_stats[matched_lga]['total'] += 1
                lga_stats[matched_lga]['matched'] += 1

                feat = ogr.Feature(matched_defn)
                set_fields(feat, row, ld, matched_lot, matched_plan, matched_lga, "parcel_matched")

                point = ogr.Geometry(ogr.wkbPoint)
                point.AddPoint(x, y)
                point.AssignSpatialReference(srs)
                feat.SetGeometry(point)
                lyr_matched.CreateFeature(feat)
                feat = None
                batch_count += 1
                if batch_count % BATCH_SIZE == 0:
                    lyr_matched.CommitTransaction()
                    lyr_unmatched.CommitTransaction()
                    lyr_matched.StartTransaction()
                    lyr_unmatched.StartTransaction()
            else:
                stats['unmatched_not_found'] += 1
                unmatched_reasons['lot_plan_not_in_cadastre'] += 1

                feat = ogr.Feature(unmatched_defn)
                set_fields(feat, row, ld, "", "", "", "lot_plan_not_found")
                lyr_unmatched.CreateFeature(feat)
                feat = None
                batch_count += 1
                if batch_count % BATCH_SIZE == 0:
                    lyr_matched.CommitTransaction()
                    lyr_unmatched.CommitTransaction()
                    lyr_matched.StartTransaction()
                    lyr_unmatched.StartTransaction()

            if stats['total'] % progress_every == 0:
                _print_progress(stats, t0, row_num)

    # Final commit
    lyr_matched.CommitTransaction()
    lyr_unmatched.CommitTransaction()

    ds_matched = None
    ds_unmatched = None

    elapsed = time.time() - t0
    stats['match_time'] = elapsed

    _print_report(stats, lga_stats, unmatched_reasons, elapsed, report_path, file_names)

    return stats


def _print_progress(stats, t0, row_num):
    elapsed = time.time() - t0
    rate = (row_num + 1) / elapsed if elapsed > 0 else 0
    total = stats['total']
    matched = stats['matched']
    rate_pct = matched / total * 100 if total else 0
    print(f"  [{row_num + 1:,}] matched={matched:,} ({rate_pct:.1f}%) "
          f"rate={rate:,.0f}/s")


def _print_report(stats, lga_stats, unmatched_reasons, elapsed, report_path, file_names):
    total = stats['total']
    matched = stats['matched']

    rate = matched / total * 100 if total else 0

    sep = "=" * 60
    lines = []
    lines.append(sep)
    lines.append("NSW Property Sales → Cadastre Matching Report")
    lines.append(sep)
    lines.append("")
    lines.append(f"Total CSV records:      {total:>10,}")
    lines.append(f"Matched to parcel:      {matched:>10,}  ({rate:.1f}%)")
    lines.append(f"Unmatched:")
    lines.append(f"  No legal description: {stats['unmatched_no_desc']:>10,}")
    lines.append(f"  Unparseable desc:     {stats['unmatched_no_parse']:>10,}")
    lines.append(f"  Lot/plan not found:   {stats['unmatched_not_found']:>10,}")
    lines.append(f"")
    lines.append(f"Processing time:        {elapsed:.1f}s")
    lines.append(f"")
    lines.append(f"Output files:")
    lines.append(f"  Matched:   {os.path.join(OUTPUT_DIR, 'nsw-property-matched.gpkg')}")
    lines.append(f"  Unmatched: {os.path.join(OUTPUT_DIR, 'nsw-property-unmatched.gpkg')}")
    lines.append(f"")

    # Per-LGA stats (top 20 + bottom 20)
    lines.append("Per-LGA match rates (top 20 by count):")
    lines.append("-" * 50)
    sorted_lgas = sorted(lga_stats.items(), key=lambda x: -x[1]['total'])
    for lga, s in sorted_lgas[:20]:
        r = s['matched'] / s['total'] * 100 if s['total'] else 0
        lines.append(f"  {lga:<30s} {s['matched']:>6,}/{s['total']:>6,}  ({r:5.1f}%)")
    if len(sorted_lgas) > 40:
        lines.append(f"  ... ({len(sorted_lgas) - 40} more)")
    for lga, s in sorted_lgas[-20:]:
        r = s['matched'] / s['total'] * 100 if s['total'] else 0
        lines.append(f"  {lga:<30s} {s['matched']:>6,}/{s['total']:>6,}  ({r:5.1f}%)")
    lines.append("")

    report_text = "\n".join(lines)
    print("\n" + report_text)

    with open(report_path, 'w') as f:
        f.write(report_text + "\n")
    print(f"\nReport saved to: {report_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NSW Property Sales → Cadastre Matcher")
    parser.add_argument('--test-lga', type=str, default=None,
                        help='Test with single LGA (e.g. COFFS_HARBOUR)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit CSV rows (for testing)')
    parser.add_argument('--skip-index', action='store_true',
                        help='Skip index building (use cached index)')
    args = parser.parse_args()

    # Find all cadastre files
    cadastre_files = sorted(glob.glob(os.path.join(CADASTRE_DIR, "cadastre_*.gpkg")))
    print(f"Found {len(cadastre_files)} cadastre GPKG files")

    if args.test_lga:
        # For test mode, only index the specific LGA GPKG for speed
        test_file = os.path.join(CADASTRE_DIR, f"cadastre_{args.test_lga}.gpkg")
        if os.path.exists(test_file):
            cadastre_files = [test_file]
            print(f"TEST MODE: Only indexing {args.test_lga} GPKG for speed")
        else:
            print(f"TEST MODE: Will only output matches for LGA={args.test_lga}")
            print(f"WARNING: GPKG not found at {test_file}, using all files")

    # Phase 1: Build index
    lotidstring_idx, lotplan_idx, file_names, index_stats = build_cadastre_index(cadastre_files)

    # Phase 2: Match CSV
    output_matched = os.path.join(OUTPUT_DIR, "nsw-property-matched.gpkg")
    output_unmatched = os.path.join(OUTPUT_DIR, "nsw-property-unmatched.gpkg")

    if args.test_lga:
        output_matched = os.path.join(OUTPUT_DIR, f"test-matched-{args.test_lga}.gpkg")
        output_unmatched = os.path.join(OUTPUT_DIR, f"test-unmatched-{args.test_lga}.gpkg")

    stats = match_and_export(
        CSV_PATH, lotidstring_idx, lotplan_idx, file_names,
        output_matched, output_unmatched, REPORT_PATH,
        limit=args.limit, test_lga=args.test_lga
    )

    print("\n✓ Done.")


if __name__ == "__main__":
    main()
