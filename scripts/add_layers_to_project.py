#!/usr/bin/env python3
"""
Add data layers to AU-QGSI.qgz project via PyQGIS.
Imports all spatial data: property listings, NSW cadastre/matched, VIC cadastre, Coffs Harbour layers.
"""
import os, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRasterLayer,
    QgsLayerTreeGroup, QgsCoordinateReferenceSystem,
    QgsField, QgsSingleSymbolRenderer, QgsMarkerSymbol,
    QgsFillSymbol, QgsCategorizedSymbolRenderer, QgsRendererCategory
)
from PyQt5.QtGui import QColor

PROJECT_PATH = '/home/yy/文档/AU-QGSI.qgz'
QGIS_DATA = '/home/yy/qgis-data'

def add_vector(path, name, group=None):
    """Add a vector layer to the project."""
    if not os.path.exists(path):
        print(f'  SKIP (not found): {name}')
        return None
    layer = QgsVectorLayer(path, name, 'ogr')
    if not layer.isValid():
        print(f'  SKIP (invalid): {name}')
        return None
    QgsProject.instance().addMapLayer(layer, False)
    if group:
        group.addLayer(layer)
    else:
        QgsProject.instance().addMapLayer(layer)
    print(f'  ✅ {name} ({layer.featureCount()} features)')
    return layer

def style_property_listings(layer):
    """Categorized renderer by property_type for listings."""
    if not layer or not layer.isValid():
        return
    # Simple marker style
    symbol = QgsMarkerSymbol.createSimple({
        'name': 'circle', 'size': '2.5', 'color': '#e31a1c',
        'outline_color': '#ffffff', 'outline_width': '0.3'
    })
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))

def style_cadastre(layer, color='#a6cee3'):
    """Simple fill for cadastre."""
    if not layer or not layer.isValid():
        return
    symbol = QgsFillSymbol.createSimple({
        'color': color, 'outline_color': '#333333', 'outline_width': '0.2'
    })
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))

def style_matched(layer, color='#1b9e77'):
    """Green fill for matched parcels."""
    if not layer or not layer.isValid():
        return
    symbol = QgsFillSymbol.createSimple({
        'color': color, 'outline_color': '#225522', 'outline_width': '0.3'
    })
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))

def main():
    # Load existing project
    project = QgsProject.instance()
    project.read(PROJECT_PATH)
    print(f'Loaded project: {project.fileName()}')
    
    root = project.layerTreeRoot()
    
    # Remove existing layers (fresh start, we have backup)
    # Keep au-tiles-local basemap
    
    # ── Group: Property Listings ──────────────────────────────
    g_listings = root.insertGroup(0, '🏠 在售房源')
    g_listings.setExpanded(False)
    
    # REA listings from SQLite/SpatiaLite
    rea = QgsVectorLayer(
        f'dbname=\'{QGIS_DATA}/property_listings.db\' table="listings" (geom) sql=',
        'REA Sydney 500', 'spatialite'
    )
    if rea.isValid():
        QgsProject.instance().addMapLayer(rea, False)
        g_listings.addLayer(rea)
        style_property_listings(rea)
        print(f'  ✅ REA Sydney 500 ({rea.featureCount()} features)')
    else:
        print(f'  ❌ REA listings failed to load')
    
    # ── Group: NSW Property Data ──────────────────────────────
    g_nsw = root.insertGroup(1, '🏡 NSW 房产数据')
    g_nsw.setExpanded(False)
    
    # NSW matched parcels (1.39M)
    matched = add_vector(
        f'{QGIS_DATA}/nsw-property-matched.gpkg',
        'NSW Matched (1.39M)',
        g_nsw
    )
    style_matched(matched, '#1b9e77')
    
    # NSW unmatched parcels
    unmatched = add_vector(
        f'{QGIS_DATA}/nsw-property-unmatched.gpkg',
        'NSW Unmatched',
        g_nsw
    )
    style_cadastre(unmatched, '#d9d9d9')
    
    # ── Group: Coffs Harbour ──────────────────────────────────
    g_coffs = root.insertGroup(2, '📍 Coffs Harbour')
    g_coffs.setExpanded(False)
    
    # Coffs property sales (v2 with coords)
    coffs_sales = add_vector(
        f'{QGIS_DATA}/coffs-harbour/coffs-property-sales-fixed.geojson',
        'Coffs Sales',
        g_coffs
    )
    if coffs_sales:
        symbol = QgsMarkerSymbol.createSimple({
            'name': 'circle', 'size': '2', 'color': '#ff7f00',
            'outline_color': '#ffffff', 'outline_width': '0.2'
        })
        coffs_sales.setRenderer(QgsSingleSymbolRenderer(symbol))
    
    # Coffs cadastre
    add_vector(
        f'{QGIS_DATA}/coffs-harbour/coffs-cadastre-fixed.geojson',
        'Coffs Cadastre',
        g_coffs
    )
    
    # Coffs ABS POA
    add_vector(
        f'{QGIS_DATA}/coffs-harbour/coffs-abs-poa-fixed.geojson',
        'Coffs ABS POA',
        g_coffs
    )
    
    # Coffs imagery (raster)
    coffs_img_path = f'{QGIS_DATA}/coffs-harbour/Coffs高清影像2m.tif'
    if os.path.exists(coffs_img_path):
        img = QgsRasterLayer(coffs_img_path, 'Coffs Imagery 2m')
        if img.isValid():
            QgsProject.instance().addMapLayer(img, False)
            g_coffs.addLayer(img)
            print(f'  ✅ Coffs Imagery 2m')
        else:
            print(f'  ❌ Coffs Imagery invalid')
    
    # ── Group: Cadastre ───────────────────────────────────────
    g_cad = root.insertGroup(3, '🗺️ 地块数据')
    g_cad.setExpanded(False)
    
    # Sydney CBD cadastre
    syd_cad = add_vector(
        f'{QGIS_DATA}/cadastre/cadastre_SYDNEY.gpkg',
        'Sydney CBD Cadastre',
        g_cad
    )
    style_cadastre(syd_cad, '#bdd7e7')
    
    # VIC cadastre
    vic_cad = add_vector(
        f'{QGIS_DATA}/vic-cadastre/vic_cadastre_all.gpkg',
        'VIC Cadastre (4.3M)',
        g_cad
    )
    style_cadastre(vic_cad, '#bcbddc')
    
    # ── Set CRS ───────────────────────────────────────────────
    project.setCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
    
    # ── Save ──────────────────────────────────────────────────
    project.write(PROJECT_PATH)
    print(f'\n✅ Project saved: {PROJECT_PATH}')
    
    # Summary
    layers = project.mapLayers()
    print(f'Total layers: {len(layers)}')
    for lid, layer in layers.items():
        print(f'  - {layer.name()} ({layer.type()})')

if __name__ == '__main__':
    main()
