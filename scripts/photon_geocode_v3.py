#!/usr/bin/env python3
"""
NSW Unmatched Property → Photon Geocoder (v3 - Fixed Resume)
=============================================================
Fixes v2 bugs:
- SetNextByIndex overridden by for-loop ResetReading()
- CreateDataSource overwrites output on every restart

Usage:
  python3 photon_geocode_v3.py [--start 0] [--test 100]
"""
import json, os, sys, time, urllib.request, urllib.parse, csv
from osgeo import ogr, osr

# Photon via local proxy (direct TCP blocked)
# Keep proxy env vars as-is

from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import threading

INPUT_GPKG = "/home/yy/qgis-data/nsw-property-v3-still-unmatched.gpkg"
OUTPUT_GPKG = "/home/yy/qgis-data/nsw-property-photon-geocoded.gpkg"
FAILED_CSV = "/home/yy/qgis-data/nsw-property-photon-failed.csv"
PROGRESS_FILE = "/home/yy/qgis-data/photon-progress.json"

PHOTON_URL = "https://photon.komoot.io/api/"
MAX_WORKERS = 5
BATCH_SIZE = 500  # checkpoint every 500

SRID_4326 = osr.SpatialReference(); SRID_4326.ImportFromEPSG(4326)
GPKG_LOCK = threading.Lock()


def geocode(address, retries=2):
    for attempt in range(retries + 1):
        try:
            params = urllib.parse.urlencode({"q": address, "limit": 1})
            url = f"{PHOTON_URL}?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "NSW-Property-Geocoder/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            feats = data.get("features", [])
            if feats:
                coords = feats[0]["geometry"]["coordinates"]
                return (coords[0], coords[1])
            return None
        except Exception:
            if attempt < retries:
                time.sleep(1 + attempt)
            else:
                return None


def build_address(house, street, locality, postcode):
    parts = []
    if house: parts.append(house)
    if street: parts.append(f"{street},")
    parts.append(locality)
    if postcode: parts.append(postcode)
    parts.append("NSW, Australia")
    return " ".join(parts)


FIELD_NAMES = [
    "property_id","sale_counter","property_name","unit_number",
    "house_number","street_name","locality","post_code",
    "area","area_type","contract_date","settlement_date",
    "purchase_price","zoning","nature_of_property","primary_purpose",
    "strata_lot_number","dealing_number","legal_description",
    "geocode_source"
]


def load_records_from(start_idx):
    """Load records from GPKG starting at FID-based index (0-based)."""
    ds = ogr.Open(INPUT_GPKG)
    layer = ds.GetLayer()
    total = layer.GetFeatureCount()

    # Use SQL to properly skip — GDAL for-loop resets SetNextByIndex
    # FID is 1-based in this GPKG; start_idx is 0-based count
    # So we want features where FID > start_idx
    table = layer.GetName()
    sql = f'SELECT * FROM "{table}" WHERE rowid > {start_idx} ORDER BY rowid'
    result = ds.ExecuteSQL(sql)
    
    records = []
    feat = result.GetNextFeature()
    while feat:
        rec = {
            "idx": start_idx + len(records),
            "property_id": feat.GetFieldAsString("property_id"),
            "house_number": feat.GetFieldAsString("house_number") or "",
            "street_name": feat.GetFieldAsString("street_name") or "",
            "locality": feat.GetFieldAsString("locality") or "",
            "post_code": feat.GetFieldAsString("post_code") or "",
            "raw": {f: (feat.GetFieldAsString(f) or "") for f in FIELD_NAMES}
        }
        records.append(rec)
        feat = result.GetNextFeature()
    
    ds.ReleaseResultSet(result)
    ds = None
    return records, total


def open_output_gpkg():
    """Open output GPKG for append if exists, create new otherwise."""
    driver = ogr.GetDriverByName("GPKG")
    
    if os.path.exists(OUTPUT_GPKG) and os.path.getsize(OUTPUT_GPKG) > 1000:
        # Open existing for append
        ds = ogr.Open(OUTPUT_GPKG, 1)  # 1 = read/write
        if ds:
            layer = ds.GetLayerByName("geocoded")
            if layer:
                return ds, layer
    
    # Create new
    ds = driver.CreateDataSource(OUTPUT_GPKG)
    layer = ds.CreateLayer("geocoded", SRID_4326, ogr.wkbPoint)
    
    field_defs = [
        ("property_id", ogr.OFTString), ("sale_counter", ogr.OFTString),
        ("property_name", ogr.OFTString), ("unit_number", ogr.OFTString),
        ("house_number", ogr.OFTString), ("street_name", ogr.OFTString),
        ("locality", ogr.OFTString), ("post_code", ogr.OFTString),
        ("area", ogr.OFTString), ("area_type", ogr.OFTString),
        ("contract_date", ogr.OFTString), ("settlement_date", ogr.OFTString),
        ("purchase_price", ogr.OFTString), ("zoning", ogr.OFTString),
        ("nature_of_property", ogr.OFTString), ("primary_purpose", ogr.OFTString),
        ("strata_lot_number", ogr.OFTString), ("dealing_number", ogr.OFTString),
        ("legal_description", ogr.OFTString), ("geocode_source", ogr.OFTString),
        ("geocode_lon", ogr.OFTReal), ("geocode_lat", ogr.OFTReal),
        ("geocode_method", ogr.OFTString),
    ]
    for fname, ftype in field_defs:
        layer.CreateField(ogr.FieldDefn(fname, ftype))
    
    return ds, layer


FIELD_DEFS = [
    ("property_id", ogr.OFTString), ("sale_counter", ogr.OFTString),
    ("property_name", ogr.OFTString), ("unit_number", ogr.OFTString),
    ("house_number", ogr.OFTString), ("street_name", ogr.OFTString),
    ("locality", ogr.OFTString), ("post_code", ogr.OFTString),
    ("area", ogr.OFTString), ("area_type", ogr.OFTString),
    ("contract_date", ogr.OFTString), ("settlement_date", ogr.OFTString),
    ("purchase_price", ogr.OFTString), ("zoning", ogr.OFTString),
    ("nature_of_property", ogr.OFTString), ("primary_purpose", ogr.OFTString),
    ("strata_lot_number", ogr.OFTString), ("dealing_number", ogr.OFTString),
    ("legal_description", ogr.OFTString), ("geocode_source", ogr.OFTString),
    ("geocode_lon", ogr.OFTReal), ("geocode_lat", ogr.OFTReal),
    ("geocode_method", ogr.OFTString),
]


def write_feature(out_layer, rec, coords):
    """Write a geocoded feature to output layer."""
    lon, lat = coords
    point = ogr.Geometry(ogr.wkbPoint)
    point.AddPoint(lon, lat)
    feat = ogr.Feature(out_layer.GetLayerDefn())
    for fn in FIELD_DEFS:
        if fn[0] == "geocode_lon":
            feat.SetField("geocode_lon", lon)
        elif fn[0] == "geocode_lat":
            feat.SetField("geocode_lat", lat)
        elif fn[0] == "geocode_method":
            feat.SetField("geocode_method", "photon_komoot")
        elif fn[0] in rec["raw"]:
            val = rec["raw"][fn[0]]
            if val:
                feat.SetField(fn[0], val)
    feat.SetGeometry(point)
    out_layer.CreateFeature(feat)
    feat = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", type=int, default=0)
    ap.add_argument("--start", type=int, default=0)
    args = ap.parse_args()

    # Load progress
    prog = {"processed": 0, "matched": 0, "failed": 0}
    if os.path.exists(PROGRESS_FILE) and args.start > 0:
        with open(PROGRESS_FILE) as f:
            prog = json.load(f)
        print(f"Resuming: processed={prog['processed']:,} matched={prog['matched']:,} failed={prog['failed']:,}", flush=True)

    print(f"Loading records from index {args.start}...", flush=True)
    records, total = load_records_from(args.start)
    if args.test:
        records = records[:args.test]
        print(f"TEST MODE: {args.test} records", flush=True)

    print(f"Processing {len(records):,} records (of {total:,} total) with {MAX_WORKERS} threads...", flush=True)
    print(f"Expected output: ~{len(records)/MAX_WORKERS/60:.0f} min at 5 req/s", flush=True)

    out_ds, out_layer = open_output_gpkg()

    is_new_csv = args.start == 0 or not os.path.exists(FAILED_CSV)
    failed_f = open(FAILED_CSV, "a" if not is_new_csv else "w", newline="")
    failed_writer = csv.writer(failed_f)
    if is_new_csv:
        failed_writer.writerow(["index", "property_id", "address", "error"])

    matched = prog["matched"]
    failed = prog["failed"]
    processed = 0

    def process_one(rec):
        addr = build_address(rec["house_number"], rec["street_name"],
                             rec["locality"], rec["post_code"])
        if not addr or addr.strip() == "NSW, Australia":
            return rec, None, "no_address"
        result = geocode(addr)
        if result:
            return rec, result, "ok"
        return rec, None, "no_result"

    batch_start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}

        for rec in records:
            f = pool.submit(process_one, rec)
            futures[f] = rec

            if len(futures) >= BATCH_SIZE:
                for fut in as_completed(futures):
                    rec, coords, status = fut.result()
                    with GPKG_LOCK:
                        if coords:
                            write_feature(out_layer, rec, coords)
                            matched += 1
                        else:
                            failed += 1
                            failed_writer.writerow([rec["idx"], rec["property_id"],
                                build_address(rec["house_number"], rec["street_name"],
                                             rec["locality"], rec["post_code"]), status])
                    processed += 1

                futures = {}
                elapsed = time.time() - batch_start
                total_done = args.start + processed
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = len(records) - processed
                eta_min = remaining / rate / 60 if rate > 0 else 0
                hit = matched / (matched + failed) * 100 if (matched + failed) else 0
                print(f"  [{total_done:,}/{total:,}] matched={matched:,} failed={failed:,} "
                      f"({hit:.1f}% hit) {rate:.1f}/s ETA={eta_min:.0f}min", flush=True)

                # Checkpoint: flush output
                out_layer.SyncToDisk()
                prog = {"processed": total_done, "matched": matched, "failed": failed}
                with open(PROGRESS_FILE, "w") as f:
                    json.dump(prog, f)

        # Handle remaining futures
        for fut in as_completed(futures):
            rec, coords, status = fut.result()
            with GPKG_LOCK:
                if coords:
                    write_feature(out_layer, rec, coords)
                    matched += 1
                else:
                    failed += 1
                    failed_writer.writerow([rec["idx"], rec["property_id"],
                        build_address(rec["house_number"], rec["street_name"],
                                     rec["locality"], rec["post_code"]), status])
            processed += 1

    # Final save
    total_done = args.start + processed
    prog = {"processed": total_done, "matched": matched, "failed": failed}
    with open(PROGRESS_FILE, "w") as f:
        json.dump(prog, f)
    failed_f.close()

    elapsed = time.time() - batch_start
    hit = matched / (matched + failed) * 100 if (matched + failed) else 0
    print(f"\n{'='*50}", flush=True)
    print(f"Done! Processed {processed:,} new records in {elapsed/60:.1f} min", flush=True)
    print(f"Cumulative: matched={matched:,} | failed={failed:,} | hit={hit:.1f}%", flush=True)
    print(f"Output: {OUTPUT_GPKG}", flush=True)

    out_ds = None


if __name__ == "__main__":
    main()
