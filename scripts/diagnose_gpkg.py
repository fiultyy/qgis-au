#!/usr/bin/env python3
"""Diagnose why cadastre GPKG features aren't being indexed."""
from osgeo import ogr, osr
import sys
import traceback

gpkg_path = "/home/yy/qgis-data/cadastre/cadastre_COFFS_HARBOUR.gpkg"

print(f"Opening: {gpkg_path}")
ds = ogr.Open(gpkg_path)
if ds is None:
    print("ERROR: Cannot open file!")
    sys.exit(1)

print(f"Layer count: {ds.GetLayerCount()}")
for i in range(ds.GetLayerCount()):
    lyr = ds.GetLayer(i)
    print(f"  Layer {i}: name='{lyr.GetName()}', type={lyr.GetGeomType()}, features={lyr.GetFeatureCount()}")

layer = ds.GetLayer(0)
print(f"\nUsing layer: '{layer.GetName()}'")
print(f"  Geometry type (wkb): {layer.GetGeomType()}")
print(f"  Feature count: {layer.GetFeatureCount()}")
print(f"  SpatialRef: {layer.GetSpatialRef()}")

# Print field definitions
print(f"\nField definitions:")
feat_defn = layer.GetLayerDefn()
for i in range(feat_defn.GetFieldCount()):
    fd = feat_defn.GetFieldDefn(i)
    print(f"  [{i}] name='{fd.GetName()}', type={fd.GetTypeName()}, width={fd.GetWidth()}")

# Test first 10 features
print(f"\n--- Testing first 10 features ---")
layer.ResetReading()
for i, feat in enumerate(layer):
    if i >= 10:
        break
    
    print(f"\nFeature {i}: FID={feat.GetFID()}")
    
    # Check fields
    lotidstring = feat.GetField('lotidstring')
    lotnumber = feat.GetField('lotnumber')
    plannumber = feat.GetField('plannumber')
    planlabel = feat.GetField('planlabel')
    sectionnumber = feat.GetField('sectionnumber')
    planlotarea = feat.GetField('planlotarea')
    
    print(f"  lotidstring = {repr(lotidstring)}")
    print(f"  lotnumber   = {repr(lotnumber)}")
    print(f"  plannumber  = {repr(plannumber)}")
    print(f"  planlabel   = {repr(planlabel)}")
    print(f"  sectionnumber= {repr(sectionnumber)}")
    print(f"  planlotarea = {repr(planlotarea)}")
    
    # Check geometry
    geom = feat.GetGeometryRef()
    print(f"  GetGeometryRef() = {geom}")
    if geom is not None:
        print(f"  geometry type = {geom.GetGeometryType()} ({ogr.GeometryTypeToName(geom.GetGeometryType())})")
        print(f"  geometry name = {geom.GetGeometryName()}")
        try:
            wkt = geom.ExportToWkt()
            print(f"  WKT length = {len(wkt)} chars")
            print(f"  WKT prefix = {wkt[:100]}...")
        except Exception as e:
            print(f"  ExportToWkt FAILED: {e}")
        
        try:
            point = geom.PointOnSurface()
            if point:
                print(f"  PointOnSurface OK: ({point.GetX():.4f}, {point.GetY():.4f})")
            else:
                print(f"  PointOnSurface returned None!")
        except Exception as e:
            print(f"  PointOnSurface FAILED: {e}")
            traceback.print_exc()
        
        try:
            centroid = geom.Centroid()
            if centroid:
                print(f"  Centroid OK: ({centroid.GetX():.4f}, {centroid.GetY():.4f})")
            else:
                print(f"  Centroid returned None!")
        except Exception as e:
            print(f"  Centroid FAILED: {e}")
            traceback.print_exc()
    else:
        print(f"  GEOMETRY IS None!")
    
    # Also try GetGeometryRef on the feature directly using different approach
    try:
        geom2 = feat.GetGeomFieldRef(0)
        print(f"  GetGeomFieldRef(0) = {geom2}")
    except Exception as e:
        print(f"  GetGeomFieldRef(0) FAILED: {e}")

# Now test with a larger sample
print(f"\n--- Testing 1000 features for stats ---")
layer.ResetReading()
stats = {'no_geom': 0, 'point_ok': 0, 'point_fail': 0, 'no_lotid': 0, 'has_lotid': 0,
         'geom_types': {}}

for i, feat in enumerate(layer):
    if i >= 1000:
        break
    
    geom = feat.GetGeometryRef()
    if geom is None:
        stats['no_geom'] += 1
        continue
    
    gt = geom.GetGeometryType()
    stats['geom_types'][gt] = stats['geom_types'].get(gt, 0) + 1
    
    try:
        point = geom.PointOnSurface()
        if point:
            stats['point_ok'] += 1
        else:
            stats['point_fail'] += 1
    except Exception:
        stats['point_fail'] += 1
    
    lotid = feat.GetField('lotidstring')
    if lotid and lotid.strip():
        stats['has_lotid'] += 1
    else:
        stats['no_lotid'] += 1

print(f"\nStats from 1000 features:")
for k, v in stats.items():
    print(f"  {k}: {v}")

ds = None
print("\nDone.")
