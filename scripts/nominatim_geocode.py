#!/usr/bin/env python3
"""
Nominatim batch geocoder for unmatched NSW properties.
Reads unmatched records from GPKG, geocodes via local Nominatim, writes results.
"""
import csv, json, os, sys, time, urllib.request, urllib.parse
from osgeo import ogr, osr
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Config ──────────────────────────────────────────────────────────────────
NOMINATIM_URL = "http://localhost:8088/search"
INPUT_GPKG = "/home/yy/qgis-data/nsw-property-unmatched-v2.gpkg"
OUTPUT_GPKG = "/home/yy/qgis-data/nsw-property-geocoded.gpkg"
FAILED_CSV = "/home/yy/qgis-data/nsw-property-geocoded-failed.csv"
RATE_LIMIT_S = 0.01  # 100ms for local instance (can go lower)
BATCH_SIZE = 10000
SRID_3857 = osr.SpatialReference()
SRID_3857.ImportFromEPSG(3857)
SRID_4326 = osr.SpatialReference()
SRID_4326.ImportFromEPSG(4326)
TRANSFORM = osr.CoordinateTransformation(SRID_4326, SRID_3857)

def build_address(row):
    """Build address string from property fields."""
    house = (row.get("Property house number") or "").strip()
    unit = (row.get("Property unit number") or "").strip()
    street = (row.get("Property street name") or "").strip()
    locality = (row.get("Property locality") or "").strip()
    postcode = (row.get("Property post code") or "").strip()
    
    parts = []
    if house:
        parts.append(house)
    if street:
        parts.append(f"{street},")
    if locality:
        parts.append(f"{locality}")
    if postcode:
        parts.append(postcode)
    parts.append("NSW, Australia")
    
    return " ".join(parts)

def geocode(address, retries=2):
    """Geocode address via Nominatim. Returns (lat, lon) or None."""
    params = urllib.parse.urlencode({
        "q": address,
        "format": "json",
        "limit": 1,
        "countrycodes": "au",
        "addressdetails": 0,
    })
    url = f"{NOMINATIM_URL}?{params}"
    
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NSW-Property-Geocoder/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
            return None
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
            else:
                return None
    return None

def read_unmatched(limit=None, coffs_only=False):
    """Read unmatched records from GPKG."""
    ds = ogr.Open(INPUT_GPKG)
    if ds is None:
        print(f"ERROR: Cannot open {INPUT_GPKG}")
        return
    layer = ds.GetLayer()
    
    records = []
    for i, feat in enumerate(layer):
        if limit and i >= limit:
            break
        
        row = {}
        # Read all fields
        feat_defn = layer.GetLayerDefn()
        for j in range(feat_defn.GetFieldCount()):
            field_name = feat_defn.GetFieldDefn(j).GetName()
            row[field_name] = feat.GetField(j)
        
        # Coffs filter
        if coffs_only:
            loc = str(row.get("locality", "") or "").lower()
            coffs_areas = ['coffs','woolgoolga','sawtell','toormina','sapphire','emerald',
                          'bonville','korora','moonee','urunga','boambee','macksville',
                          'bowraville','kororo','nana']
            if not any(x in loc for x in coffs_areas):
                continue
        
        records.append(row)
    
    ds = None
    return records

def write_output(matched, output_path):
    """Write geocoded results to GPKG."""
    if not matched:
        return
    
    driver = ogr.GetDriverByName("GPKG")
    ds = driver.CreateDataSource(output_path)
    
    # Create layer
    layer = ds.CreateLayer("property_geocoded", SRID_3857, ogr.wkbPoint)
    
    # Add fields from first record
    sample = matched[0]
    field_map = {}
    for key in sample:
        if key in ("_lat", "_lon"):
            continue
        field_type = ogr.OFTString
        if isinstance(sample[key], (int, float)):
            field_type = ogr.OFTReal
        field_name = key[:60] if key else "field"
        field_map[key] = field_name
        layer.CreateField(ogr.FieldDefn(field_name, field_type))
    
    layer.CreateField(ogr.FieldDefn("geocode_precision", ogr.OFTString))
    
    # Write features
    for rec in matched:
        lat = rec.pop("_lat")
        lon = rec.pop("_lon")
        
        feat = ogr.Feature(layer.GetLayerDefn())
        for key, field_name in field_map.items():
            val = rec.get(key)
            if val is not None:
                feat.SetField(field_name, str(val))
        
        feat.SetField("geocode_precision", "address")
        
        # Transform point
        point = ogr.Geometry(ogr.wkbPoint)
        point.AddPoint(float(lon), float(lat))
        point.Transform(TRANSFORM)
        feat.SetGeometry(point)
        
        layer.CreateFeature(feat)
    
    ds = None

def main():
    parser = argparse.ArgumentParser(description="Nominatim geocoder for unmatched NSW properties")
    parser.add_argument("--coffs-only", action="store_true", help="Only process Coffs Harbour area")
    parser.add_argument("--limit", type=int, default=None, help="Max records to process")
    parser.add_argument("--threads", type=int, default=4, help="Concurrent threads")
    args = parser.parse_args()
    
    print(f"Reading unmatched records{' (Coffs only)' if args.coffs_only else ''}...", flush=True)
    records = read_unmatched(limit=args.limit, coffs_only=args.coffs_only)
    print(f"  {len(records)} records to geocode", flush=True)
    
    if not records:
        print("No records to process.")
        return
    
    # Geocode in parallel
    matched = []
    failed = []
    processed = 0
    
    def process_one(rec):
        addr = build_address(rec)
        if not addr or len(addr) < 10:
            return rec, None
        result = geocode(addr)
        time.sleep(RATE_LIMIT_S)
        return rec, result
    
    print(f"Geocoding with {args.threads} threads...", flush=True)
    
    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        futures = {pool.submit(process_one, r): r for r in records}
        
        for future in as_completed(futures):
            rec, result = future.result()
            processed += 1
            
            if result:
                rec["_lat"], rec["_lon"] = result
                matched.append(rec)
            else:
                failed.append(rec)
            
            if processed % 100 == 0:
                ts = time.strftime("%H:%M:%S")
                rate = processed / (time.time() - start_time) if processed > 0 else 0
                print(f"  [{ts}] {processed}/{len(records)} | matched:{len(matched)} failed:{len(failed)} | {rate:.1f}/s", flush=True)
    
    elapsed = time.time() - start_time
    print(f"\n✅ Done in {elapsed:.0f}s", flush=True)
    print(f"  Matched: {len(matched)} ({len(matched)/len(records)*100:.1f}%)", flush=True)
    print(f"  Failed:  {len(failed)}", flush=True)
    
    # Write outputs
    if matched:
        suffix = "_coffs" if args.coffs_only else ""
        out = OUTPUT_GPKG.replace(".gpkg", f"{suffix}.gpkg")
        write_output(matched, out)
        print(f"  Output: {out}", flush=True)
    
    if failed:
        suffix = "_coffs" if args.coffs_only else ""
        fail_out = FAILED_CSV.replace(".csv", f"{suffix}.csv")
        with open(fail_out, "w", newline="") as f:
            if failed:
                w = csv.DictWriter(f, fieldnames=failed[0].keys())
                w.writeheader()
                w.writerows(failed)
        print(f"  Failed:  {fail_out}", flush=True)

if __name__ == "__main__":
    start_time = time.time()
    main()
