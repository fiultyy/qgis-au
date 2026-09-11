#!/usr/bin/env python3
"""
NSW Unmatched Property → Photon Geocoder
========================================
Batch geocode the 98,712 unmatched NSW properties via Photon (komoot.io API).
Writes results to GPKG with coordinates, logs failures to CSV.

Usage:
  python3 photon_geocode.py [--batch-size 5000] [--start 0] [--test 100]
"""
import json, os, sys, time, urllib.request, urllib.parse, csv
from osgeo import ogr, osr
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse

INPUT_GPKG = "/home/yy/qgis-data/nsw-property-v3-still-unmatched.gpkg"
OUTPUT_GPKG = "/home/yy/qgis-data/nsw-property-photon-geocoded.gpkg"
FAILED_CSV = "/home/yy/qgis-data/nsw-property-photon-failed.csv"
PROGRESS_FILE = "/home/yy/qgis-data/photon-progress.json"

PHOTON_URL = "https://photon.komoot.io/api/"
RATE_LIMIT_S = 0.1  # 100ms between batches
MAX_WORKERS = 8    # parallel requests
BATCH_LOG = 1000

SRID_4326 = osr.SpatialReference(); SRID_4326.ImportFromEPSG(4326)


def build_address(feat):
    """Build address string from property fields."""
    house = (feat.GetFieldAsString("house_number") or "").strip()
    street = (feat.GetFieldAsString("street_name") or "").strip()
    locality = (feat.GetFieldAsString("locality") or "").strip()
    postcode = (feat.GetFieldAsString("post_code") or "").strip()
    
    parts = []
    if house:
        parts.append(house)
    if street:
        parts.append(f"{street},")
    parts.append(locality)
    if postcode:
        parts.append(postcode)
    parts.append("NSW, Australia")
    return " ".join(parts)


def geocode(address, retries=2):
    """Geocode via Photon. Returns (lon, lat) or None."""
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
                return (coords[0], coords[1])  # (lon, lat)
            return None
        except Exception as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
            else:
                return None


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"processed": 0, "matched": 0, "failed": 0}


def save_progress(prog):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(prog, f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", type=int, default=0, help="Only process N records (test mode)")
    ap.add_argument("--start", type=int, default=0, help="Start from index")
    args = ap.parse_args()

    ds = ogr.Open(INPUT_GPKG)
    layer = ds.GetLayer()
    total = layer.GetFeatureCount()
    print(f"Input: {total:,} unmatched records", flush=True)

    prog = load_progress()
    start_idx = args.start or prog["processed"]
    if args.test:
        end_idx = start_idx + args.test
        print(f"TEST MODE: processing {args.test} records from index {start_idx}", flush=True)
    else:
        end_idx = total

    # Create output GPKG
    out_driver = ogr.GetDriverByName("GPKG")
    if os.path.exists(OUTPUT_GPKG) and start_idx == 0:
        os.remove(OUTPUT_GPKG)
    out_ds = out_driver.CreateDataSource(OUTPUT_GPKG)
    out_layer = out_ds.CreateLayer("geocoded", SRID_4326, ogr.wkbPoint)
    
    # Copy fields from input + add geocode metadata
    ldefn = layer.GetLayerDefn()
    field_names = []
    for i in range(ldefn.GetFieldCount()):
        fdefn = ldefn.GetFieldDefn(i)
        out_layer.CreateField(fdefn)
        field_names.append(fdefn.GetName())
    out_layer.CreateField(ogr.FieldDefn("geocode_lon", ogr.OFTReal))
    out_layer.CreateField(ogr.FieldDefn("geocode_lat", ogr.OFTReal))
    out_layer.CreateField(ogr.FieldDefn("geocode_method", ogr.OFTString))

    # Failed CSV
    failed_exists = os.path.exists(FAILED_CSV) and start_idx > 0
    failed_f = open(FAILED_CSV, "a" if failed_exists else "w", newline="")
    failed_writer = csv.writer(failed_f)
    if not failed_exists:
        failed_writer.writerow(["index", "property_id", "address", "error"])

    # Process
    layer.SetNextByIndex(start_idx)
    matched = prog["matched"]
    failed = prog["failed"]
    count = 0

    for feat in layer:
        idx = start_idx + count
        if idx >= end_idx:
            break

        address = build_address(feat)
        if not address or address.strip() == "NSW Australia":
            failed += 1
            failed_writer.writerow([idx, feat.GetFieldAsString("property_id"), address, "no_address"])
            count += 1
            continue

        result = geocode(address)
        time.sleep(RATE_LIMIT_S)

        if result:
            lon, lat = result
            point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint(lon, lat)

            out_feat = ogr.Feature(out_layer.GetLayerDefn())
            # Copy fields
            for fn in field_names:
                val = feat.GetFieldAsString(fn)
                if val:
                    out_feat.SetField(fn, val)
            out_feat.SetField("geocode_lon", lon)
            out_feat.SetField("geocode_lat", lat)
            out_feat.SetField("geocode_method", "photon_komoot")
            out_feat.SetGeometry(point)
            out_layer.CreateFeature(out_feat)
            out_feat = None
            matched += 1
        else:
            failed += 1
            failed_writer.writerow([idx, feat.GetFieldAsString("property_id"), address, "no_result"])

        count += 1
        if count % BATCH_LOG == 0:
            prog = {"processed": idx + 1, "matched": matched, "failed": failed}
            save_progress(prog)
            pct = matched / (matched + failed) * 100 if (matched + failed) else 0
            print(f"  [{idx+1:,}/{end_idx:,}] matched={matched:,} failed={failed:,} ({pct:.1f}% hit)" , flush=True)

    # Final save
    prog = {"processed": idx + 1 if count > 0 else start_idx, "matched": matched, "failed": failed}
    save_progress(prog)
    failed_f.close()

    print(f"\n{'='*50}")
    print(f"Done! Processed: {count:,}")
    print(f"Matched: {matched:,}")
    print(f"Failed:  {failed:,}")
    print(f"Output:  {OUTPUT_GPKG}")
    print(f"Failed:  {FAILED_CSV}")

    out_ds = None
    ds = None


if __name__ == "__main__":
    main()
