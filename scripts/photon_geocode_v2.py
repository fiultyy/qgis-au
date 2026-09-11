#!/usr/bin/env python3
"""
NSW Unmatched Property → Photon Geocoder (v2 - Multithreaded)
=============================================================
Batch geocode v3-still-unmatched NSW properties via Photon API.
Uses ThreadPoolExecutor for real parallelism.

Usage:
  python3 photon_geocode_v2.py [--start 0] [--test 100]
"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error, csv
from osgeo import ogr, osr

# 通过代理访问 Photon（本机需代理出网）
# Proxy is required for outbound HTTPS from this host

from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import threading

INPUT_GPKG = "/home/yy/qgis-data/nsw-property-v3-still-unmatched.gpkg"
OUTPUT_GPKG = "/home/yy/qgis-data/nsw-property-photon-geocoded.gpkg"
FAILED_CSV = "/home/yy/qgis-data/nsw-property-photon-failed.csv"
PROGRESS_FILE = "/home/yy/qgis-data/photon-progress.json"
LOCK_FILE = "/home/yy/qgis-data/photon.lock"

PHOTON_URL = "https://photon.komoot.io/api/"
MAX_WORKERS = 5
BATCH_SIZE = 1000  # log every 1000

# Use system proxy (required for outbound HTTPS from this host)
# Leave default urllib opener which respects HTTP_PROXY/HTTPS_PROXY env vars

SRID_4326 = osr.SpatialReference(); SRID_4326.ImportFromEPSG(4326)
GPKG_LOCK = threading.Lock()


def acquire_lock():
    """Single-instance lock. Returns True if we may run."""
    if os.path.exists(LOCK_FILE):
        try:
            pid = int(open(LOCK_FILE).read().strip() or "0")
            os.kill(pid, 0)  # raises ProcessLookupError if dead
            print(f"ALREADY_RUNNING: another instance (PID {pid}) is geocoding right now. "
                  f"NOT starting a duplicate. Check photon-progress.json for live progress. "
                  f"This is NOT an error and NOT a completion — nothing to report, do not notify. "
                  f"Exiting 0.", flush=True)
            return False
        except (ProcessLookupError, ValueError):
            try: os.remove(LOCK_FILE)  # stale lock — reclaim
            except OSError: pass
        except OSError:
            print(f"ALREADY_RUNNING: lock held by PID {open(LOCK_FILE).read().strip()}. "
                  f"NOT starting a duplicate. Exiting 0.", flush=True)
            return False
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True

def release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except OSError:
        pass


def geocode(address, retries=2):
    """Geocode via Photon. Returns (lon, lat) or None."""
    for attempt in range(retries + 1):
        try:
            params = urllib.parse.urlencode({"q": address, "limit": 1})
            url = f"{PHOTON_URL}?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "NSW-Property-Geocoder/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            feats = data.get("features", [])
            if feats:
                coords = feats[0]["geometry"]["coordinates"]
                return (coords[0], coords[1])
            return None
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                time.sleep(45 * (attempt + 1))  # rate limited — back off hard
                continue
            if attempt < retries:
                time.sleep(1 + attempt)
            else:
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


def load_all_records(start_idx=0):
    """Load input records starting at absolute feature index start_idx.

    NOTE: layer.SetNextByIndex() proved to be a silent no-op in this stack
    (GPKG + python iteration), which caused full re-runs from index 0 on
    every resume. Iterate from 0 and skip manually instead.
    """
    ds = ogr.Open(INPUT_GPKG)
    layer = ds.GetLayer()
    total = layer.GetFeatureCount()

    records = []
    for i, feat in enumerate(layer):
        if i < start_idx:
            continue
        rec = {
            "idx": i,
            "property_id": feat.GetFieldAsString("property_id"),
            "house_number": feat.GetFieldAsString("house_number") or "",
            "street_name": feat.GetFieldAsString("street_name") or "",
            "locality": feat.GetFieldAsString("locality") or "",
            "post_code": feat.GetFieldAsString("post_code") or "",
            "raw": {f: feat.GetFieldAsString(f) for f in [
                "property_id","sale_counter","property_name","unit_number",
                "house_number","street_name","locality","post_code",
                "area","area_type","contract_date","settlement_date",
                "purchase_price","zoning","nature_of_property","primary_purpose",
                "strata_lot_number","dealing_number","legal_description",
                "geocode_source"
            ]}
        }
        records.append(rec)
    ds = None
    return records, total


def preflight(min_ok=3, probes=None):
    """Fire a few real geocode probes; return number of successes."""
    probes = probes or [
        "1 George St Sydney NSW 2000, Australia",
        "12 Blaxland Rd Ryde NSW 2112, Australia",
        "5 Pitt St Marrickville NSW 2204, Australia",
        "100 Main St Blacktown NSW 2148, Australia",
        "7 Ocean Dr Port Macquarie NSW 2444, Australia",
    ]
    ok = 0
    for q in probes:
        if geocode(q):
            ok += 1
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", type=int, default=0)
    ap.add_argument("--start", type=int, default=0)
    args = ap.parse_args()

    if not acquire_lock():
        sys.exit(0)

    print("Preflight: probing Photon health...", flush=True)
    pf_ok = preflight()
    print(f"Preflight: {pf_ok}/5 probes OK", flush=True)
    if pf_ok < 3:
        print("PHOTON_DEGRADED: fewer than 3/5 probes succeeded. "
              "NOT processing anything, progress unchanged. Exiting 0.", flush=True)
        release_lock()
        sys.exit(0)

    if args.start > 0:
        print("NOTE: --start is deprecated (resume is now key-based and idempotent); "
              "ignoring it and processing the full scan with key-skip.", flush=True)
        args.start = 0

    print(f"Loading records from index {args.start}...", flush=True)
    
    # OLD progress-file seeding removed: it accumulated lies across broken
    # resumes. The output GPKG content is now the sole resume truth.
    records, total = load_all_records(args.start)

    # --- Resume truth: skip input rows whose (property_id, sale_counter) key
    # is already geocoded in the output GPKG. Input keys are NOT unique
    # (49,826 distinct over 73,091 rows), so key-skip is the only idempotent
    # resume mechanism; index slicing alone cannot express it.
    done_keys = set()
    if os.path.exists(OUTPUT_GPKG):
        _mds = ogr.Open(OUTPUT_GPKG)
        if _mds is not None:
            _ml = _mds.GetLayerByName("geocoded")
            if _ml is not None:
                for _f in _ml:
                    done_keys.add((_f.GetFieldAsString("property_id"),
                                   _f.GetFieldAsString("sale_counter")))
            _mds = None  # close before reopening for update (SQLite lock)
    pre_matched = len(done_keys)

    rows_total = len(records)
    if done_keys:
        records = [r for r in records
                   if (r["property_id"], r["raw"]["sale_counter"]) not in done_keys]
        rows_pre_covered = rows_total - len(records)
        print(f"Resume: {pre_matched:,} matched keys cover {rows_pre_covered:,} input rows (skipped); "
              f"{len(records):,} records to attempt this run.", flush=True)
    else:
        rows_pre_covered = 0
    if args.test:
        records = records[:args.test]
        print(f"TEST MODE: {args.test} records", flush=True)

    print(f"Processing {len(records):,} records with {MAX_WORKERS} threads...", flush=True)

    # Open or create output GPKG (append mode when resuming)
    driver = ogr.GetDriverByName("GPKG")
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
    if os.path.exists(OUTPUT_GPKG):
        out_ds = ogr.Open(OUTPUT_GPKG, 1)  # open for update (append mode)
        if out_ds is None:
            # fallback: create new
            out_ds = driver.CreateDataSource(OUTPUT_GPKG)
            out_layer = out_ds.CreateLayer("geocoded", SRID_4326, ogr.wkbPoint)
            for fname, ftype in field_defs:
                out_layer.CreateField(ogr.FieldDefn(fname, ftype))
        else:
            out_layer = out_ds.GetLayerByName("geocoded")
            if out_layer is None:
                out_layer = out_ds.CreateLayer("geocoded", SRID_4326, ogr.wkbPoint)
                for fname, ftype in field_defs:
                    out_layer.CreateField(ogr.FieldDefn(fname, ftype))
    else:
        out_ds = driver.CreateDataSource(OUTPUT_GPKG)
        out_layer = out_ds.CreateLayer("geocoded", SRID_4326, ogr.wkbPoint)
        for fname, ftype in field_defs:
            out_layer.CreateField(ogr.FieldDefn(fname, ftype))

    failed_f = open(FAILED_CSV, "w", newline="")  # fresh per run: failed keys are retried on resume
    failed_writer = csv.writer(failed_f)
    failed_writer.writerow(["index", "property_id", "address", "error"])

    matched = pre_matched   # total matched keys (self-corrected from output GPKG)
    failed = 0              # this-run only; failed keys retry on next resume
    processed = 0           # this-run attempts
    display_total = rows_pre_covered + len(records)

    def process_one(rec):
        addr = build_address(rec["house_number"], rec["street_name"],
                             rec["locality"], rec["post_code"])
        if not addr or addr.strip() == "NSW, Australia":
            return rec, None, "no_address"
        result = geocode(addr)
        if result:
            return rec, result, "ok"
        return rec, None, "no_result"

    # Process in batches for progress tracking
    batch_start = time.time()
    STOP_BATCHES = True  # may be set False by circuit breaker below
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        
        for rec in records:
            if not STOP_BATCHES:
                break
            f = pool.submit(process_one, rec)
            futures[f] = rec
            
            # When batch is full, wait for completion
            if len(futures) >= BATCH_SIZE:
                m0, f0 = matched, failed
                for fut in as_completed(futures):
                    rec, coords, status = fut.result()
                    with GPKG_LOCK:
                        if coords:
                            lon, lat = coords
                            point = ogr.Geometry(ogr.wkbPoint)
                            point.AddPoint(lon, lat)
                            feat = ogr.Feature(out_layer.GetLayerDefn())
                            for fn in field_defs:
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
                            matched += 1
                        else:
                            failed += 1
                            failed_writer.writerow([rec["idx"], rec["property_id"],
                                build_address(rec["house_number"], rec["street_name"],
                                             rec["locality"], rec["post_code"]), status])
                    processed += 1
                
                futures = {}
                elapsed = time.time() - batch_start
                total_done = rows_pre_covered + processed
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = len(records) - processed
                eta_min = remaining / rate / 60 if rate > 0 else 0
                hit = matched / (matched + failed) * 100 if (matched + failed) else 0
                print(f"  [{total_done:,}/{display_total:,}] matched={matched:,} failed={failed:,} "
                      f"({hit:.1f}% hit) {rate:.0f}/s ETA={eta_min:.0f}min", flush=True)
                
                prog = {"processed": total_done, "matched": matched, "failed": failed}
                with open(PROGRESS_FILE, "w") as f:
                    json.dump(prog, f)

                # Circuit breaker: if this batch was almost all failures,
                # Photon is likely rate-limited/degraded — stop cleanly at a
                # batch boundary so cron can resume later. Bounded damage <= batch.
                dm, df = matched - m0, failed - f0
                if dm + df >= 500 and dm / (dm + df) < 0.05:
                    print(f"RATE_LIMITED_SUSPECTED: batch match rate {dm}/{dm+df} < 5%. "
                          f"Stopping cleanly at {total_done:,}. Progress saved; "
                          f"cron will resume when Photon recovers.", flush=True)
                    STOP_BATCHES = False
                    futures = {}
                    break

        # Handle remaining futures
        for fut in as_completed(futures):
            rec, coords, status = fut.result()
            with GPKG_LOCK:
                if coords:
                    lon, lat = coords
                    point = ogr.Geometry(ogr.wkbPoint)
                    point.AddPoint(lon, lat)
                    feat = ogr.Feature(out_layer.GetLayerDefn())
                    for fn in field_defs:
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
                    matched += 1
                else:
                    failed += 1
                    failed_writer.writerow([rec["idx"], rec["property_id"],
                        build_address(rec["house_number"], rec["street_name"],
                                     rec["locality"], rec["post_code"]), status])
            processed += 1

    # Final save — pass is complete only if every queued record was attempted
    total_done = rows_pre_covered + processed
    pass_complete = processed >= len(records)
    prog = {"processed": total_done, "matched": matched, "failed": failed,
            "done": bool(pass_complete),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    with open(PROGRESS_FILE, "w") as f:
        json.dump(prog, f)
    failed_f.close()

    elapsed = time.time() - batch_start
    hit = matched / (matched + failed) * 100 if (matched + failed) else 0
    print(f"\n{'='*50}", flush=True)
    print(f"Done! Processed: {processed:,} in {elapsed/60:.1f} min", flush=True)
    print(f"PASS_COMPLETE: {pass_complete} (attempted {processed:,}/{len(records):,} queued)", flush=True)
    print(f"Matched: {matched:,} | Failed: {failed:,} | Hit: {hit:.1f}%", flush=True)
    print(f"Output: {OUTPUT_GPKG}", flush=True)

    out_ds = None
    release_lock()


if __name__ == "__main__":
    main()
