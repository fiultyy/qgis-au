#!/usr/bin/env python3
"""
NSW Property Sales → Cadastre Matching v3
=========================================
Fix: SP (strata) plans have empty lot numbers in cadastre.
v1/v2 failed because they searched (lot, plan) — lot="" matches nothing.
v3: For SP plans, match on plan_label only, use PointOnSurface of the polygon.

Also keeps v2 improvements: fuzzy lot matching.
"""
import csv, json, os, sys, time, glob, re, argparse
from osgeo import ogr, osr
from collections import defaultdict

CADASTRE_DIR = "/home/yy/qgis-data/cadastre"
UNMATCHED_INPUT = "/home/yy/qgis-data/nsw-property-unmatched-v2.gpkg"
MATCHED_OUTPUT = "/home/yy/qgis-data/nsw-property-matched-v3.gpkg"
REPORT_FILE = "/home/yy/qgis-data/nsw-property-match-v3-report.txt"

SRID = osr.SpatialReference()
SRID.ImportFromEPSG(3857)

def build_sp_plan_index(test_lga=None):
    """Build {plan_label: (x, y)} index for SP plans across all cadastre."""
    print("Phase 1a: Building SP plan index...", flush=True)
    index = {}
    file_list = sorted(glob.glob(os.path.join(CADASTRE_DIR, "cadastre_*.gpkg")))
    
    for file_idx, f in enumerate(file_list):
        lga = os.path.basename(f).replace("cadastre_", "").replace(".gpkg", "")
        if test_lga and lga != test_lga:
            continue
        ds = ogr.Open(f)
        if ds is None: continue
        layer = ds.GetLayer()
        for feat in layer:
            plan_label = feat.GetFieldAsString("planlabel") or ""
            if plan_label.startswith("SP"):
                geom = feat.GetGeometryRef()
                if geom:
                    pt = geom.PointOnSurface()
                    index[plan_label] = (pt.GetX(), pt.GetY())
        ds = None
        if (file_idx + 1) % 20 == 0:
            print(f"  Scanned {file_idx+1}/{len(file_list)}, {len(index)} SP plans", flush=True)
    
    print(f"  SP plans indexed: {len(index):,}", flush=True)
    return index

def build_full_index(test_lga=None):
    """Build {lotidstring: (x, y)} index for non-SP plans."""
    print("Phase 1b: Building full cadastre index (non-SP)...", flush=True)
    index = {}
    file_list = sorted(glob.glob(os.path.join(CADASTRE_DIR, "cadastre_*.gpkg")))
    
    for f in file_list:
        lga = os.path.basename(f).replace("cadastre_", "").replace(".gpkg", "")
        if test_lga and lga != test_lga:
            continue
        ds = ogr.Open(f)
        if ds is None: continue
        layer = ds.GetLayer()
        for feat in layer:
            plan_label = feat.GetFieldAsString("planlabel") or ""
            if not plan_label.startswith("SP"):
                lid = feat.GetFieldAsString("lotidstring") or ""
                if lid:
                    geom = feat.GetGeometryRef()
                    if geom:
                        pt = geom.PointOnSurface()
                        index[lid] = (pt.GetX(), pt.GetY())
        ds = None
    
    print(f"  Full index: {len(index):,}", flush=True)
    return index

def parse_legal_description(desc):
    if not desc or not desc.strip():
        return []
    desc = desc.strip()
    desc = re.sub(r'\bPT\s+', '', desc, flags=re.I)
    desc = re.sub(r',\s+', ',', desc)
    results = []
    for parcel in desc.split():
        parcel = parcel.strip().strip(',')
        if not parcel: continue
        sc = parcel.count('/')
        if sc == 1:
            m = re.match(r'^(.+?)/([A-Za-z]*\d+)$', parcel)
            if not m: continue
            lot_str, plan_str = m.group(1).strip(), m.group(2).strip()
            pm = re.match(r'^([A-Za-z]*)(\d+)$', plan_str)
            if not pm: continue
            for lot in lot_str.split(','):
                lot = lot.strip()
                if lot: results.append((lot, None, pm.group(1), pm.group(2)))
        elif sc == 2:
            parts = parcel.split('/')
            if len(parts) != 3: continue
            lot_str, section, plan_str = parts[0].strip(), parts[1].strip(), parts[2].strip()
            pm = re.match(r'^([A-Za-z]*)(\d+)$', plan_str)
            if not pm: continue
            for lot in lot_str.split(','):
                lot = lot.strip()
                if lot: results.append((lot, section, pm.group(1), pm.group(2)))
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-lga", default=None)
    args = parser.parse_args()
    start = time.time()
    
    sp_index = build_sp_plan_index(test_lga=args.test_lga)
    full_index = build_full_index(test_lga=args.test_lga)
    
    print(f"\nPhase 2: Processing unmatched...", flush=True)
    ds_in = ogr.Open(UNMATCHED_INPUT)
    if not ds_in:
        print(f"ERROR: Cannot open {UNMATCHED_INPUT}"); return
    layer_in = ds_in.GetLayer()
    defn = layer_in.GetLayerDefn()
    fields = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]
    
    # Find legal description field
    ld_field = None
    for f in fields:
        if "legal" in f.lower():
            ld_field = f; break
    
    driver = ogr.GetDriverByName("GPKG")
    out_path = MATCHED_OUTPUT.replace(".gpkg", f"_{args.test_lga}.gpkg") if args.test_lga else MATCHED_OUTPUT
    ds_out = driver.CreateDataSource(out_path)
    layer_out = ds_out.CreateLayer("matched_v3", SRID, ogr.wkbPoint)
    for i in range(defn.GetFieldCount()):
        layer_out.CreateField(defn.GetFieldDefn(i))
    layer_out.CreateField(ogr.FieldDefn("match_method", ogr.OFTString))
    
    stats = {"matched": 0, "unmatched": 0, "sp_plan_only": 0, "lot_plan_exact": 0}
    
    for feat in layer_in:
        ld = feat.GetFieldAsString(ld_field) if ld_field else ""
        parsed = parse_legal_description(ld)
        matched = False
        
        for lot, section, prefix, num in parsed:
            plan_label = f"{prefix}{num}"
            
            if prefix.upper() == "SP":
                if plan_label in sp_index:
                    x, y = sp_index[plan_label]
                    of = ogr.Feature(layer_out.GetLayerDefn())
                    for i in range(defn.GetFieldCount()):
                        of.SetField(i, feat.GetField(i))
                    of.SetField("match_method", "sp_plan_only")
                    pt = ogr.Geometry(ogr.wkbPoint); pt.AddPoint(x, y)
                    of.SetGeometry(pt)
                    layer_out.CreateFeature(of)
                    stats["matched"] += 1; stats["sp_plan_only"] += 1
                    matched = True; break
            else:
                sec = f"/{section}" if section else ""
                lid = f"{lot}{sec}//{plan_label}"
                if lid in full_index:
                    x, y = full_index[lid]
                    of = ogr.Feature(layer_out.GetLayerDefn())
                    for i in range(defn.GetFieldCount()):
                        of.SetField(i, feat.GetField(i))
                    of.SetField("match_method", "lot_plan_exact")
                    pt = ogr.Geometry(ogr.wkbPoint); pt.AddPoint(x, y)
                    of.SetGeometry(pt)
                    layer_out.CreateFeature(of)
                    stats["matched"] += 1; stats["lot_plan_exact"] += 1
                    matched = True; break
        
        if not matched:
            stats["unmatched"] += 1
        
        total = stats["matched"] + stats["unmatched"]
        if total % 50000 == 0:
            print(f"  [{time.strftime('%H:%M:%S')}] {total:,} | matched:{stats['matched']:,} ({stats['matched']/total*100:.1f}%)", flush=True)
    
    ds_out = None; ds_in = None
    elapsed = time.time() - start
    total = stats["matched"] + stats["unmatched"]
    
    report = f"""============================================================
NSW Property Matching v3 Report
============================================================
LGA filter: {args.test_lga or 'ALL'}
Time: {elapsed:.1f}s
Total unmatched (v2):   {total:,}
Matched (v3):           {stats['matched']:,}  ({stats['matched']/total*100:.1f}%)
Still unmatched:        {stats['unmatched']:,}
Methods: sp_plan_only={stats['sp_plan_only']:,} lot_plan_exact={stats['lot_plan_exact']:,}
Output: {out_path}
"""
    print(report)
    rpt = REPORT_FILE.replace(".txt", f"_{args.test_lga}.txt") if args.test_lga else REPORT_FILE
    with open(rpt, "w") as f: f.write(report)

if __name__ == "__main__":
    main()
