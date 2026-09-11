#!/usr/bin/env python3
"""
NSW Property Sales Data Cleaning
================================
Cleans 2.2M NSW property sales records.

Operations:
  1. Deduplication: same Property ID + Contract date → keep first
  2. Date standardization: YYYY-MM-DD format, remove 1900-01-01 and future dates
  3. Price cleaning: zero/empty → invalid, >$100M → anomaly, z-score by postcode+area
  4. Area cleaning: zero OK (apartments), inconsistent area type flagged
  5. Output: cleaned CSV.gz + report

Usage:
  python3 nsw_property_clean.py                          # full run
  python3 nsw_property_clean.py --limit 100000           # test with subset
  python3 nsw_property_clean.py --test-lga COFFS_HARBOUR  # Coffs Harbour only
"""

import csv
import sys
import os
import re
import time
import gzip
import json
import argparse
import statistics
from collections import defaultdict, Counter

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# ─── Configuration ────────────────────────────────────────────────────────────

CSV_PATH = "/home/yy/qgis-data/coffs-harbour/nsw-property-sales-data-updated20260721.csv"
OUTPUT_DIR = "/home/yy/qgis-data"

OUTPUT_GZ = os.path.join(OUTPUT_DIR, "nsw-property-sales-cleaned.csv.gz")
REPORT_PATH = os.path.join(OUTPUT_DIR, "nsw-property-clean-report.txt")

# Data cutoff — records after this are future/invalid
DATA_CUTOFF_DATE = "2026-07-31"
EPOCH_DATE_THRESHOLD = "1900-01-02"  # Dates <= 1900-01-01 are invalid

# Price thresholds
PRICE_HIGH_THRESHOLD = 100_000_000  # $100M
PRICE_ZERO_INVALID = True

# Test-LGA postcode filter
TEST_LGA_POSTCODES = {
    'COFFS_HARBOUR': {'2450', '2452', '2453', '2454', '2455', '2456', '2460'},
}

# Original CSV columns
ORIGINAL_COLS = [
    "Property ID", "Sale counter", "Download date / time", "Property name",
    "Property unit number", "Property house number", "Property street name",
    "Property locality", "Property post code", "Area", "Area type",
    "Contract date", "Settlement date", "Purchase price", "Zoning",
    "Nature of property", "Primary purpose", "Strata lot number",
    "Dealing number", "Property legal description"
]

# New columns to add
NEW_COLS = ["is_valid", "issues", "price_zscore"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def clean_postcode(pc_raw):
    """Clean postcode: '2325.0' → '2325', '' → ''"""
    if not pc_raw:
        return ''
    pc = str(pc_raw).strip()
    # Handle float format like "2325.0"
    if pc.endswith('.0'):
        pc = pc[:-2]
    elif pc.endswith('.00'):
        pc = pc[:-3]
    # Replace .00 or .0 patterns
    pc = re.sub(r'\.\d+$', '', pc)
    return pc


def clean_price(price_raw):
    """Parse price string → float or None"""
    if not price_raw:
        return None
    s = str(price_raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def clean_area(area_raw):
    """Parse area string → float or None"""
    if not area_raw:
        return None
    s = str(area_raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def standardize_date(date_str):
    """Standardize date to YYYY-MM-DD format.
    Returns (cleaned_date_str, issue_str_or_None)
    """
    if not date_str:
        return '', 'missing_date'

    s = str(date_str).strip()
    if not s:
        return '', 'missing_date'

    # Already YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        pass
    # YYYYMMDD format
    elif re.match(r'^\d{8}$', s):
        s = f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    # DD/MM/YYYY or D/M/YYYY
    elif re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', s):
        parts = s.split('/')
        s = f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
    else:
        return s, 'unrecognized_date_format'

    # Check for epoch dates (1900-01-01 etc)
    if s <= '1900-01-01':
        return s, 'epoch_date'

    # Check for future dates
    if s > DATA_CUTOFF_DATE:
        return s, 'future_date'

    return s, None


def compute_zscore(value, mean, std):
    """Compute z-score safely"""
    if std is None or std == 0 or mean is None:
        return 0.0
    return (value - mean) / std


# ─── Main Cleaning Pipeline ───────────────────────────────────────────────────

def run_cleaning(csv_path, output_gz, report_path, limit=None, test_lga=None):
    """Run the full cleaning pipeline."""

    print("=" * 60)
    print("NSW Property Sales Data Cleaning")
    print("=" * 60)
    print(f"Input:  {csv_path}")
    print(f"Output: {output_gz}")
    if limit:
        print(f"Limit:  {limit:,} rows")
    if test_lga:
        print(f"LGA filter: {test_lga}")

    t0 = time.time()

    # ── Pass 1: Read all data, dedup, clean dates/prices/areas, collect stats ──
    print("\n--- Pass 1: Reading + Dedup + Initial Cleaning ---")

    # Statistics counters
    stats = defaultdict(int)
    issue_counts = defaultdict(int)

    # Group: (postcode, area_type) → list of prices for median computation
    price_groups = defaultdict(list)

    # Dedup tracking
    seen_keys = set()

    # Storage for cleaned records (streamed, not all in memory for 2.2M)
    # We need two passes: 1 for stats, 2 for z-score. For 2.2M rows,
    # we'll store minimal data for pass 2.

    test_postcodes = None
    if test_lga and test_lga in TEST_LGA_POSTCODES:
        test_postcodes = TEST_LGA_POSTCODES[test_lga]

    # We'll store records in memory for two-pass z-score.
    # Each record ~500 bytes, 2.2M * 500 = ~1.1GB. Might be tight.
    # Alternative: use temp file. Let's use a compact in-memory structure.
    records = []  # List of dicts

    BATCH_PRINT = 100000

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row_num, row in enumerate(reader):
            if limit and row_num >= limit:
                break

            # Test-LGA postcode filter
            if test_postcodes:
                pc = clean_postcode(row.get("Property post code", ""))
                if pc not in test_postcodes:
                    continue

            stats['total_input'] += 1

            # ── Dedup ──
            pid = str(row.get("Property ID", "")).strip()
            cd_raw = str(row.get("Contract date", "")).strip()
            dedup_key = (pid, cd_raw)

            if pid and cd_raw and dedup_key in seen_keys:
                stats['duplicates_removed'] += 1
                continue
            if pid and cd_raw:
                seen_keys.add(dedup_key)

            # ── Parse fields ──
            pc = clean_postcode(row.get("Property post code", ""))
            area = clean_area(row.get("Area", ""))
            area_type = str(row.get("Area type", "")).strip()
            price = clean_price(row.get("Purchase price", ""))

            # ── Date cleaning ──
            cd_clean, cd_issue = standardize_date(row.get("Contract date", ""))
            sd_clean, sd_issue = standardize_date(row.get("Settlement date", ""))

            issues = []

            # Date issues
            if cd_issue:
                if cd_issue == 'missing_date':
                    issues.append('contract_date_missing')
                elif cd_issue == 'epoch_date':
                    issues.append('contract_date_epoch')
                elif cd_issue == 'future_date':
                    issues.append('contract_date_future')
                elif cd_issue == 'unrecognized_date_format':
                    issues.append('contract_date_bad_format')
                issue_counts[cd_issue] += 1

            if sd_issue:
                if sd_issue == 'missing_date':
                    issues.append('settlement_date_missing')
                elif sd_issue == 'epoch_date':
                    issues.append('settlement_date_epoch')
                elif sd_issue == 'future_date':
                    issues.append('settlement_date_future')
                elif sd_issue == 'unrecognized_date_format':
                    issues.append('settlement_date_bad_format')
                issue_counts[sd_issue] += 1

            # ── Price cleaning ──
            price_flag = 'valid'
            price_zscore = 0.0

            if price is None or (PRICE_ZERO_INVALID and price == 0):
                issues.append('price_invalid_zero_or_empty')
                issue_counts['price_invalid'] += 1
                price_flag = 'invalid'
            elif price > PRICE_HIGH_THRESHOLD:
                issues.append(f'price_extremely_high_{price:.0f}')
                issue_counts['price_extremely_high'] += 1
                price_flag = 'anomaly'
            else:
                # Collect for z-score computation (group by postcode + area_type)
                if pc and area_type:
                    price_groups[(pc, area_type)].append(price)
                elif pc:
                    price_groups[(pc, '_all')].append(price)

            # ── Area cleaning ──
            if area is not None and area == 0:
                # Zero area — likely apartment, keep but flag
                issues.append('area_zero')
                issue_counts['area_zero'] += 1
            elif area is not None and area < 0:
                issues.append('area_negative')
                issue_counts['area_negative'] += 1

            # Area type consistency: M=square meters, H=hectares
            # Flag if area_type is unusual
            if area_type and area_type not in ('M', 'H', ''):
                issues.append(f'area_type_unusual_{area_type}')
                issue_counts['area_type_unusual'] += 1

            # Cross-check: hectares should be large, meters should be reasonable
            if area is not None and area > 0 and area_type:
                if area_type == 'H' and area < 10:
                    # <10 hectares but marked as hectares — might be wrong unit
                    issues.append('area_type_mismatch_small_hectare')
                    issue_counts['area_type_mismatch'] += 1
                elif area_type == 'M' and area > 1_000_000:
                    # >1km² in square meters — might be hectares
                    issues.append('area_type_mismatch_large_m2')
                    issue_counts['area_type_mismatch'] += 1

            # ── Determine validity ──
            is_valid = 1
            critical_issues = [i for i in issues if i.startswith('price_invalid') or
                             i == 'contract_date_missing' or i == 'contract_date_epoch']
            if critical_issues:
                is_valid = 0
                stats['records_invalid'] += 1
            else:
                stats['records_valid'] += 1

            if issues:
                stats['records_with_issues'] += 1
            else:
                stats['records_clean'] += 1

            # ── Store record ──
            record = {
                # Original fields (cleaned)
                "Property ID": pid,
                "Sale counter": str(row.get("Sale counter", "")).strip(),
                "Download date / time": str(row.get("Download date / time", "")).strip(),
                "Property name": str(row.get("Property name", "")).strip(),
                "Property unit number": str(row.get("Property unit number", "")).strip(),
                "Property house number": str(row.get("Property house number", "")).strip(),
                "Property street name": str(row.get("Property street name", "")).strip(),
                "Property locality": str(row.get("Property locality", "")).strip(),
                "Property post code": pc,
                "Area": str(area) if area is not None else '',
                "Area type": area_type,
                "Contract date": cd_clean,
                "Settlement date": sd_clean,
                "Purchase price": str(price) if price is not None else '',
                "Zoning": str(row.get("Zoning", "")).strip(),
                "Nature of property": str(row.get("Nature of property", "")).strip(),
                "Primary purpose": str(row.get("Primary purpose", "")).strip(),
                "Strata lot number": str(row.get("Strata lot number", "")).strip(),
                "Dealing number": str(row.get("Dealing number", "")).strip(),
                "Property legal description": str(row.get("Property legal description", "")).strip(),
                # New fields
                "_is_valid": is_valid,
                "_issues": issues,
                "_price": price,
                "_price_flag": price_flag,
                "_pc": pc,
                "_area_type": area_type,
            }
            records.append(record)

            stats['total_kept'] += 1

            if (row_num + 1) % BATCH_PRINT == 0:
                elapsed = time.time() - t0
                rate = (row_num + 1) / elapsed if elapsed > 0 else 0
                print(f"  Read {row_num + 1:,} rows, kept {stats['total_kept']:,} "
                      f"({rate:,.0f}/s, dups removed: {stats['duplicates_removed']:,})")

    elapsed_p1 = time.time() - t0
    print(f"\nPass 1 complete: {stats['total_kept']:,} records kept "
          f"({stats['duplicates_removed']:,} duplicates removed) in {elapsed_p1:.1f}s")

    # ── Compute z-scores for prices ──
    print("\n--- Computing price statistics by postcode+area_type ---")

    group_stats = {}  # (pc, at) → (median, mad or std)
    group_count = 0

    for key, prices in price_groups.items():
        if len(prices) < 5:
            # Too few for meaningful stats
            group_stats[key] = (None, None)
            continue
        med = statistics.median(prices)
        # Use MAD (median absolute deviation) — more robust than std
        abs_devs = [abs(p - med) for p in prices]
        mad = statistics.median(abs_devs)
        group_stats[key] = (med, mad)
        group_count += 1

    print(f"  Computed stats for {group_count:,} postcode+area_type groups "
          f"(out of {len(price_groups):,} total)")

    # ── Pass 2: Compute z-scores, flag outliers, write output ──
    print("\n--- Pass 2: Computing z-scores + writing output ---")

    t2 = time.time()

    # Define output columns
    output_cols = ORIGINAL_COLS + ["is_valid", "issues", "price_zscore"]

    outlier_count = 0
    written = 0

    with gzip.open(output_gz, 'wt', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=output_cols, extrasaction='ignore')
        writer.writeheader()

        for rec in records:
            price = rec.pop('_price', None)
            pc = rec.pop('_pc', '')
            at = rec.pop('_area_type', '')
            price_flag = rec.pop('_price_flag', 'valid')
            issues = rec.pop('_issues', [])
            rec['is_valid'] = rec.pop('_is_valid', 1)

            # Compute z-score
            zscore = 0.0
            if price is not None and price > 0 and price_flag == 'valid':
                # Try (pc, at) group, then (pc, '_all')
                stats_pair = group_stats.get((pc, at)) or group_stats.get((pc, '_all'))
                if stats_pair and stats_pair[0] is not None and stats_pair[1] is not None:
                    med, mad = stats_pair
                    if mad > 0:
                        # Robust z-score: 0.6745 * (price - median) / MAD
                        zscore = 0.6745 * (price - med) / mad
                        rec['price_zscore'] = f"{zscore:.2f}"

                        # Flag extreme outliers (>5 robust z-score = >5x median deviation)
                        if abs(zscore) > 5:
                            issues.append(f'price_outlier_zscore_{zscore:.1f}')
                            issue_counts['price_outlier'] += 1
                            outlier_count += 1
                            # Don't invalidate, just flag
                    else:
                        rec['price_zscore'] = '0.00'
                else:
                    rec['price_zscore'] = '0.00'
            else:
                rec['price_zscore'] = ''

            rec['issues'] = json.dumps(issues) if issues else ''

            writer.writerow(rec)
            written += 1

            if written % BATCH_PRINT == 0:
                elapsed = time.time() - t2
                rate = written / elapsed if elapsed > 0 else 0
                print(f"  Written {written:,} records ({rate:,.0f}/s)")

    elapsed_p2 = time.time() - t2
    print(f"\nPass 2 complete: {written:,} records written in {elapsed_p2:.1f}s")

    # ── Generate Report ──
    total = stats['total_input']
    kept = stats['total_kept']
    removed = stats['duplicates_removed']
    valid = stats['records_valid']
    invalid = stats['records_invalid']

    sep = "=" * 60
    lines = []
    lines.append(sep)
    lines.append("NSW Property Sales Data Cleaning Report")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(sep)
    lines.append("")
    lines.append("INPUT SUMMARY")
    lines.append("-" * 40)
    lines.append(f"Total input rows:       {total:>10,}")
    if test_lga:
        lines.append(f"LGA filter:             {test_lga}")
    lines.append("")
    lines.append("DEDUPLICATION")
    lines.append("-" * 40)
    lines.append(f"Duplicate rows removed: {removed:>10,}")
    lines.append(f"Records after dedup:    {kept:>10,}")
    dedup_rate = removed / total * 100 if total else 0
    lines.append(f"Dedup rate:             {dedup_rate:>10.2f}%")
    lines.append("")
    lines.append("VALIDITY SUMMARY")
    lines.append("-" * 40)
    lines.append(f"Valid records:          {valid:>10,}  ({valid/kept*100:.1f}%)" if kept else "")
    lines.append(f"Invalid records:        {invalid:>10,}  ({invalid/kept*100:.1f}%)" if kept else "")
    lines.append(f"Records with issues:    {stats['records_with_issues']:>10,}")
    lines.append(f"Clean records (no flag):{stats['records_clean']:>10,}")
    lines.append("")
    lines.append("ISSUE BREAKDOWN")
    lines.append("-" * 40)
    for issue, cnt in sorted(issue_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {issue:<35s} {cnt:>8,}")
    lines.append(f"  {'price_outliers (z>5)':<35s} {outlier_count:>8,}")
    lines.append("")
    lines.append("DATE CLEANING")
    lines.append("-" * 40)
    lines.append(f"Contract date issues:   {issue_counts.get('missing_date',0) + issue_counts.get('epoch_date',0) + issue_counts.get('future_date',0) + issue_counts.get('unrecognized_date_format',0):>10,}")
    lines.append(f"Settlement date issues: {issue_counts.get('missing_date',0):>10,}")
    lines.append(f"Future dates removed:   {issue_counts.get('future_date',0):>10,}")
    lines.append(f"Epoch dates found:      {issue_counts.get('epoch_date',0):>10,}")
    lines.append("")
    lines.append("PRICE CLEANING")
    lines.append("-" * 40)
    lines.append(f"Invalid (zero/empty):   {issue_counts.get('price_invalid',0):>10,}")
    lines.append(f"Extremely high (>$100M):{issue_counts.get('price_extremely_high',0):>10,}")
    lines.append(f"Outliers (robust z>5):  {outlier_count:>10,}")
    lines.append(f"Stats groups computed:  {group_count:>10,}")
    lines.append("")
    lines.append("AREA CLEANING")
    lines.append("-" * 40)
    lines.append(f"Zero area (apartments?):{issue_counts.get('area_zero',0):>10,}")
    lines.append(f"Negative area:          {issue_counts.get('area_negative',0):>10,}")
    lines.append(f"Area type mismatch:     {issue_counts.get('area_type_mismatch',0):>10,}")
    lines.append(f"Unusual area type:      {issue_counts.get('area_type_unusual',0):>10,}")
    lines.append("")
    lines.append("OUTPUT")
    lines.append("-" * 40)
    lines.append(f"Output file: {output_gz}")
    lines.append(f"Output rows: {written:,}")
    lines.append(f"Output columns: {len(output_cols)}")
    lines.append(f"  Original: {len(ORIGINAL_COLS)}")
    lines.append(f"  Added:    {', '.join(NEW_COLS)}")
    lines.append("")
    lines.append("TIMING")
    lines.append("-" * 40)
    lines.append(f"Pass 1 (read+dedup+clean): {elapsed_p1:.1f}s")
    lines.append(f"Pass 2 (zscore+write):     {elapsed_p2:.1f}s")
    lines.append(f"Total:                     {elapsed_p1 + elapsed_p2:.1f}s")
    lines.append("")

    report_text = "\n".join(lines)
    print("\n" + report_text)

    with open(report_path, 'w') as f:
        f.write(report_text + "\n")
    print(f"\nReport saved to: {report_path}")
    print(f"Output saved to: {output_gz}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NSW Property Sales Data Cleaning")
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit CSV rows (for testing)')
    parser.add_argument('--test-lga', type=str, default=None,
                        help='Test with specific LGA postcodes')
    args = parser.parse_args()

    output_gz = OUTPUT_GZ
    report_path = REPORT_PATH

    if args.test_lga:
        output_gz = os.path.join(OUTPUT_DIR, f"test-cleaned-{args.test_lga}.csv.gz")
        report_path = os.path.join(OUTPUT_DIR, f"test-clean-report-{args.test_lga}.txt")

    run_cleaning(CSV_PATH, output_gz, report_path, limit=args.limit, test_lga=args.test_lga)

    print("\n✓ Cleaning done.")


if __name__ == "__main__":
    main()
