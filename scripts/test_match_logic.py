#!/usr/bin/env python3
"""Test the actual index building and matching logic."""
from osgeo import ogr
import re
import csv
import sys

# Enable exceptions to catch silent failures
ogr.UseExceptions()

CSV_PATH = "/home/yy/qgis-data/coffs-harbour/nsw-property-sales-data-updated20260721.csv"
GPKG_PATH = "/home/yy/qgis-data/cadastre/cadastre_COFFS_HARBOUR.gpkg"

# ── Build index for COFFS_HARBOUR ──
print("Building index for COFFS_HARBOUR...")
ds = ogr.Open(GPKG_PATH)
layer = ds.GetLayer()
print(f"  Layer: {layer.GetName()}, Features: {layer.GetFeatureCount()}")

lotidstring_idx = {}
lotplan_idx = {}
total_indexed = 0

for feat in layer:
    geom = feat.GetGeometryRef()
    if geom is None:
        continue
    try:
        point = geom.PointOnSurface()
    except Exception:
        try:
            point = geom.Centroid()
        except Exception:
            continue
    if point is None:
        continue
    
    px, py = point.GetX(), point.GetY()
    
    lotidstring = feat.GetField('lotidstring')
    if lotidstring and lotidstring.strip():
        key = lotidstring.strip().upper()
        if key not in lotidstring_idx:
            lotidstring_idx[key] = (px, py, 0, 0.0)
            total_indexed += 1
    
    lotnumber = feat.GetField('lotnumber')
    sectionnumber = feat.GetField('sectionnumber')
    plannumber = feat.GetField('plannumber')
    
    if lotnumber is not None and plannumber is not None:
        lot_str = str(lotnumber).strip()
        sec_str = str(sectionnumber).strip() if sectionnumber else ''
        plan_str = str(plannumber).strip()
        lp_key = (lot_str, sec_str, plan_str)
        if lp_key not in lotplan_idx:
            lotplan_idx[lp_key] = (px, py, 0, 0.0)

ds = None
print(f"  Indexed: {total_indexed} lotidstring entries, {len(lotplan_idx)} lotplan entries")

# Print some sample keys
print(f"\nSample lotidstring keys (first 20):")
for i, k in enumerate(sorted(lotidstring_idx.keys())):
    if i >= 20:
        break
    print(f"  '{k}' → {lotidstring_idx[k][:2]}")

print(f"\nSample lotplan keys (first 20):")
for i, k in enumerate(sorted(lotplan_idx.keys())):
    if i >= 20:
        break
    print(f"  {k} → {lotplan_idx[k][:2]}")

# ── Test matching with a few CSV records ──
print(f"\n--- Testing CSV matching ---")

def parse_legal_description(desc):
    if not desc or not desc.strip():
        return []
    desc = desc.strip()
    desc = re.sub(r'\bPT\s+', '', desc, flags=re.I)
    desc = re.sub(r',\s+', ',', desc)
    results = []
    parcels = desc.split()
    for parcel in parcels:
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

# Read first 20 CSV records and try matching
matched = 0
total = 0
with open(CSV_PATH, newline='', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    print(f"CSV columns: {reader.fieldnames}")
    for i, row in enumerate(reader):
        if i >= 20:
            break
        total += 1
        ld = str(row.get("Property legal description", "")).strip()
        locality = str(row.get("Property locality", "")).strip()
        
        parsed = parse_legal_description(ld)
        
        result = None
        for lot, section, plan_prefix, plan_num in parsed:
            keys_to_try = []
            if section:
                keys_to_try.append(f"{lot}/{section}//{plan_prefix}{plan_num}")
                keys_to_try.append(f"{lot}/{section}//{plan_num}")
            else:
                keys_to_try.append(f"{lot}//{plan_prefix}{plan_num}")
                keys_to_try.append(f"{lot}//{plan_num}")
            
            for key in keys_to_try:
                key_upper = key.upper()
                if key_upper in lotidstring_idx:
                    result = lotidstring_idx[key_upper]
                    print(f"  Row {i}: ld='{ld}' → MATCH via key='{key_upper}'")
                    break
            
            if not result:
                lp_keys = []
                if section:
                    lp_keys.append((lot, str(section), plan_num))
                lp_keys.append((lot, '', plan_num))
                for lp_key in lp_keys:
                    if lp_key in lotplan_idx:
                        result = lotplan_idx[lp_key]
                        print(f"  Row {i}: ld='{ld}' → MATCH via lotplan {lp_key}")
                        break
            if result:
                break
        
        if result:
            matched += 1
        else:
            print(f"  Row {i}: ld='{ld}' [locality={locality}] → NO MATCH")
            if parsed:
                print(f"    Parsed: {parsed}")
                for lot, section, plan_prefix, plan_num in parsed:
                    keys_to_try = []
                    if section:
                        keys_to_try.append(f"{lot}/{section}//{plan_prefix}{plan_num}")
                    else:
                        keys_to_try.append(f"{lot}//{plan_prefix}{plan_num}")
                    for key in keys_to_try:
                        key_upper = key.upper()
                        print(f"    Looking for key='{key_upper}' in index (found={key_upper in lotidstring_idx})")

print(f"\nResult: {matched}/{total} matched")
