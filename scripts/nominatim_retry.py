#!/usr/bin/env python3
"""
NSW Failed Property → Nominatim Geocoder (retry for Photon failures)
=====================================================================
Reads Photon-failed CSV, geocodes via Nominatim, appends to existing GPKG.

Usage:
  python3 nominatim_retry.py [--start N] [--test 10]

Rate limit: 1 req/sec (Nominatim policy), so ~28 min for 1688 records.
"""
import json, os, sys, time, urllib.request, urllib.parse, csv, argparse
from osgeo import ogr, osr

FAILED_CSV  = "/home/yy/qgis-data/nsw-property-photon-failed.csv"
OUTPUT_GPKG = "/home/yy/qgis-data/nsw-property-photon-geocoded.gpkg"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PROGRESS_FILE = "/home/yy/qgis-data/nominatim-progress.json"
LOCK_FILE = "/home/yy/qgis-data/nominatim.lock"
UA = "NSW-Property-Geocode-Retry/1.0 (research)"
REMAINING_CSV = "/home/yy/qgis-data/nominatim-remaining.csv"

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


def geocode_nominatim(address):
    """Returns (lon, lat) or None. Rate: 1 req/sec."""
    try:
        # Clean address: remove "Australia" suffix, normalize
        addr = address.replace(", Australia", "").strip()
        params = urllib.parse.urlencode({
            "q": addr,
            "format": "json",
            "limit": 1,
            "countrycodes": "au",
            "accept-language": "en"
        })
        url = f"{NOMINATIM_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        feats = data.get("features") or data  # Nominatim returns array directly
        if isinstance(data, list) and len(data) > 0:
            lon = float(data[0]["lon"])
            lat = float(data[0]["lat"])
            return (lon, lat)
        return None
    except Exception as e:
        return None


def open_gpkg_append():
    """Open existing GPKG for appending features."""
    driver = ogr.GetDriverByName("GPKG")
    ds = ogr.Open(OUTPUT_GPKG, 1)
    if ds is None:
        print(f"FATAL: Cannot open {OUTPUT_GPKG} for update")
        sys.exit(1)
    layer = ds.GetLayerByName("geocoded")
    if layer is None:
        print("FATAL: 'geocoded' layer not found in GPKG")
        sys.exit(1)
    return ds, layer


def append_feature(layer, property_id, lon, lat):
    """Create and append a point feature to the geocoded layer."""
    # Get layer definition from first feature to match schema
    layer_defn = layer.GetLayerDefn()
    feat = ogr.Feature(layer_defn)
    feat.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT ({lon} {lat})"))
    # Set known fields
    for i in range(layer_defn.GetFieldCount()):
        name = layer_defn.GetFieldDefn(i).GetName()
        if name == "property_id":
            feat.SetField(i, str(int(float(property_id))))
        elif name == "geocode_source":
            feat.SetField(i, "nominatim")
        elif name == "geocode_lon":
            feat.SetField(i, lon)
        elif name == "geocode_lat":
            feat.SetField(i, lat)
        elif name == "geocode_method":
            feat.SetField(i, "nominatim_reverse")
    layer.CreateFeature(feat)
    feat = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--test", type=int, default=0, help="Only process N rows")
    args = ap.parse_args()

    if not acquire_lock():
        sys.exit(0)

    try:
        done_keys = load_progress()
        if done_keys is None:
            release_lock()
            sys.exit(0)

        # Read failed CSV
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

        print(f"Starting Nominatim retry: {total} records (skip {len(done_keys)} done)")
        sys.stdout.flush()

        # Open GPKG for append
        ds, layer = open_gpkg_append()

        # Read original input GPKG to get full field data
        input_gpkg = "/home/yy/qgis-data/nsw-property-v3-still-unmatched.gpkg"
        input_ds = ogr.Open(input_gpkg)
        input_layer = input_ds.GetLayer()
        # Build lookup: property_id -> feature
        pid_map = {}
        for feat in input_layer:
            pid = feat.GetFieldAsString("property_id")
            pid_map[pid] = feat

        matched, failed = 0, 0
        remaining = []

        for idx, row in enumerate(rows):
            pid = row["property_id"]
            address = row["address"]

            result = geocode_nominatim(address)
            time.sleep(1.05)  # Nominatim rate limit: 1 req/sec

            if result:
                lon, lat = result
                # Try to get full record from input GPKG
                orig = pid_map.get(pid)
                if orig:
                    # Copy all fields from original
                    layer_defn = layer.GetLayerDefn()
                    feat = ogr.Feature(layer_defn)
                    feat.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT ({lon} {lat})"))
                    for i in range(layer_defn.GetFieldCount()):
                        fn = layer_defn.GetFieldDefn(i).GetName()
                        val = orig.GetFieldAsString(fn) if orig.IsFieldSet(i) else None
                        if fn in ("geocode_source", "geocode_lon", "geocode_lat", "geocode_method"):
                            continue  # set below
                        if val is not None:
                            feat.SetField(i, val)
                    feat.SetField("geocode_source", "nominatim")
                    feat.SetField("geocode_lon", lon)
                    feat.SetField("geocode_lat", lat)
                    feat.SetField("geocode_method", "nominatim")
                    layer.CreateFeature(feat)
                    feat = None
                else:
                    # Fallback: minimal feature
                    append_feature(layer, pid, lon, lat)

                matched += 1
                done_keys.add(pid)
            else:
                failed += 1
                remaining.append(row)
                done_keys.add(pid)

            ds.SyncToDisk()
            progress = (idx + 1) / total * 100
            print(f"  [{idx+1:,}/{total:,}] matched={matched:,} failed={failed:,} ({progress:.1f}%)")
            sys.stdout.flush()

            # Periodic progress save
            if (idx + 1) % 100 == 0 or idx == total - 1:
                save_progress(done_keys, matched, failed, total)

        # Write remaining failures
        if remaining:
            with open(REMAINING_CSV, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=remaining[0].keys())
                w.writeheader()
                w.writerows(remaining)

        save_progress(done_keys, matched, failed, total, done=True)
        print(f"\nDONE! Nominatim retry complete.")
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
