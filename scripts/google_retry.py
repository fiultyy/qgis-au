#!/usr/bin/env python3
"""
NSW Failed Property → Google Geocoding API (retry for Photon+Nominatim failures)
===============================================================================
Reads photon-failed CSV, geocodes via Google Maps Geocoding API, appends to GPKG.

Usage:
  python3 google_retry.py [--start N] [--test 10]

Rate limit: 50 req/sec (free tier), but we do 5/sec to be safe.
1688 records ≈ ~6 min.
"""
import json, os, sys, time, urllib.request, urllib.parse, csv, argparse
from osgeo import ogr, osr

FAILED_CSV  = "/home/yy/qgis-data/nsw-property-photon-failed.csv"
OUTPUT_GPKG = "/home/yy/qgis-data/nsw-property-photon-geocoded.gpkg"
INPUT_GPKG  = "/home/yy/qgis-data/nsw-property-v3-still-unmatched.gpkg"
GOOGLE_KEY  = os.environ.get("GOOGLE_GEOCODING_KEY", "")   # key 已于 2026-08 轮换取消,按需从环境变量注入
PROGRESS_FILE = "/home/yy/qgis-data/google-progress.json"
LOCK_FILE = "/home/yy/qgis-data/google-geocode.lock"
REMAINING_CSV = "/home/yy/qgis-data/google-remaining.csv"
INTERVAL = 0.25  # 4 req/sec safe rate

SRID_4326 = osr.SpatialReference()
SRID_4326.ImportFromEPSG(4326)


def acquire_lock():
    if os.path.exists(LOCK_FILE):
        try:
            pid = int(open(LOCK_FILE).read().strip() or "0")
            os.kill(pid, 0)
            print(f"ALREADY_RUNNING (PID {pid}). Exiting 0.")
            return False
        except (ProcessLookupError, ValueError):
            try: os.remove(LOCK_FILE)
            except OSError: pass
        except OSError:
            return False
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True


def release_lock():
    try: os.remove(LOCK_FILE)
    except OSError: pass


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            p = json.load(f)
        if p.get("done"):
            print("ALREADY_DONE. Exiting 0.")
            return None
        return set(p.get("done_keys", []))
    return set()


def save_progress(done_keys, matched, failed, total, done=False):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({
            "done_keys": list(done_keys),
            "matched": matched, "failed": failed,
            "processed": len(done_keys), "total": total,
            "done": done
        }, f)


def geocode_google(address):
    """Returns (lon, lat, formatted_address) or None."""
    try:
        params = urllib.parse.urlencode({
            "address": address,
            "key": GOOGLE_KEY,
        })
        url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        if data.get("status") == "OK":
            r = data["results"][0]
            loc = r["geometry"]["location"]
            return (loc["lng"], loc["lat"], r.get("formatted_address", ""))
        elif data.get("status") == "OVER_QUERY_LIMIT":
            print("  ⚠ OVER_QUERY_LIMIT — backing off 5s")
            time.sleep(5)
            return geocode_google(address)  # retry once
        return None
    except Exception as e:
        print(f"  ⚠ error: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--test", type=int, default=0)
    args = ap.parse_args()

    if not acquire_lock():
        sys.exit(0)

    try:
        done_keys = load_progress()
        if done_keys is None:
            release_lock()
            sys.exit(0)

        rows = []
        with open(FAILED_CSV, newline="") as f:
            for r in csv.DictReader(f):
                key = r["property_id"]
                if key not in done_keys:
                    rows.append(r)

        if args.test > 0:
            rows = rows[args.start:args.start + args.test]
        elif args.start > 0:
            rows = rows[args.start:]

        total = len(rows)
        if total == 0:
            print("NOTHING_TO_DO. Exiting 0.")
            release_lock()
            sys.exit(0)

        print(f"Starting Google Geocoding retry: {total} records (skip {len(done_keys)} done)")
        sys.stdout.flush()

        # Open GPKG for append
        driver = ogr.GetDriverByName("GPKG")
        ds = ogr.Open(OUTPUT_GPKG, 1)
        if not ds:
            print(f"FATAL: Cannot open {OUTPUT_GPKG}")
            sys.exit(1)
        layer = ds.GetLayerByName("geocoded")
        layer_defn = layer.GetLayerDefn()

        # Load input GPKG for full field data
        input_ds = ogr.Open(INPUT_GPKG)
        input_layer = input_ds.GetLayer()
        pid_map = {}
        for feat in input_layer:
            pid = feat.GetFieldAsString("property_id")
            pid_map[pid] = feat

        matched, failed = 0, 0
        remaining = []

        for idx, row in enumerate(rows):
            pid = row["property_id"]
            address = row["address"]

            result = geocode_google(address)
            if result:
                lon, lat, fmt_addr = result
                orig = pid_map.get(pid)
                feat = ogr.Feature(layer_defn)
                feat.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT ({lon} {lat})"))
                if orig:
                    for i in range(layer_defn.GetFieldCount()):
                        fn = layer_defn.GetFieldDefn(i).GetName()
                        if fn in ("geocode_source", "geocode_lon", "geocode_lat", "geocode_method"):
                            continue
                        if orig.IsFieldSet(i):
                            feat.SetField(i, orig.GetFieldAsString(i))
                else:
                    if layer.GetFieldIndex("property_id") >= 0:
                        feat.SetField("property_id", str(int(float(pid))))
                feat.SetField("geocode_source", "google")
                feat.SetField("geocode_lon", lon)
                feat.SetField("geocode_lat", lat)
                feat.SetField("geocode_method", "google_geocoding")
                layer.CreateFeature(feat)
                feat = None
                matched += 1
            else:
                failed += 1
                remaining.append(row)

            done_keys.add(pid)
            time.sleep(INTERVAL)

            progress = (idx + 1) / total * 100
            print(f"  [{idx+1:,}/{total:,}] matched={matched:,} failed={failed:,} ({progress:.1f}%)")
            sys.stdout.flush()

            if (idx + 1) % 200 == 0 or idx == total - 1:
                ds.SyncToDisk()
                save_progress(done_keys, matched, failed, total)

        if remaining:
            with open(REMAINING_CSV, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=remaining[0].keys())
                w.writeheader()
                w.writerows(remaining)

        save_progress(done_keys, matched, failed, total, done=True)
        print(f"\nDONE! Google Geocoding retry complete.")
        print(f"  Matched: {matched} | Still failed: {failed} | Output: {OUTPUT_GPKG}")
        if remaining:
            print(f"  Remaining: {REMAINING_CSV}")

        ds = None
        input_ds = None

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        release_lock()


if __name__ == "__main__":
    main()
