#!/usr/bin/env python3
"""Add 5m LiDAR-derived terrain detail layers (NSW Spatial Portal DEM-AHD).

  地形·精细·山体阴影(Coffs/Sydney 5m)  visible <= 1:100k, covers the 30m HS
  地形·精细·等高线(5m)                 visible <= 1:40k, elev labels <= 1:20k

Usage: python3 add_terrain_5m.py <project.qgs> [more.qgs ...]
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtGui import QColor, QFont
from qgis.core import (
    QgsApplication, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsLineSymbol,
    QgsSingleSymbolRenderer, QgsPalLayerSettings, QgsTextFormat,
    QgsTextBufferSettings, QgsVectorLayerSimpleLabeling, QgsUnitTypes,
    QgsLayerTreeLayer)

BASE = os.path.expanduser("~/qgis-data/au-terrain/nsw5m")
AREAS = [
    ("Coffs", f"{BASE}/coffs_hs5m.tif", f"{BASE}/contours_5m_coffs_s.gpkg"),
    ("Sydney", f"{BASE}/sydney_hs5m.tif", f"{BASE}/contours_5m_syd_s.gpkg"),
]


def style_hs(layer):
    from qgis.core import QgsSingleBandGrayRenderer
    layer.setRenderer(QgsSingleBandGrayRenderer(layer.dataProvider(), 1))


def style_contours(layer):
    sym = QgsLineSymbol.createSimple({
        "line_color": "#8a5a2a", "line_width": "0.12"})
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    s = QgsPalLayerSettings()
    s.fieldName = "elev"
    s.placement = QgsPalLayerSettings.Line
    fmt = QgsTextFormat()
    fmt.setFont(QFont("DejaVu Sans"))
    fmt.setSize(6.5)
    fmt.setSizeUnit(QgsUnitTypes.RenderPoints)
    fmt.setColor(QColor("#5a3d22"))
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(1.0)
    buf.setSizeUnit(QgsUnitTypes.RenderPoints)
    buf.setColor(QColor("#ffffff"))
    fmt.setBuffer(buf)
    s.setFormat(fmt)
    s.scaleVisibility = True
    s.minimumScale = 20000            # visible when zoomed in past 1:20k
    s.maximumScale = 0
    layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
    layer.setLabelsEnabled(True)
    layer.setScaleBasedVisibility(True)
    layer.setMinimumScale(40000)      # visible when scale <= 1:40k
    layer.setMaximumScale(0)


def add_to_project(path):
    proj = QgsProject()
    proj.read(path)
    print(f"loaded {path}")
    root = proj.layerTreeRoot()

    for lid, lyr in list(proj.mapLayers().items()):
        name = lyr.name()
        if name.startswith("地形·精细"):
            proj.removeMapLayer(lid)
            print(f"removed previous {name}")
    for rl in list(root.findLayers()):
        try:
            if rl.layer() is None and rl.name().startswith("地形·精细"):
                rl.parent().removeChildNode(rl)  # 清理历史 null 节点
                print("removed orphan node")
        except RuntimeError:
            pass                                 # 节点已随层移除,跳过

    hs_layers, con_layers = [], []
    for area, hs_path, con_path in AREAS:
        hs = QgsRasterLayer(hs_path, f"地形·精细·山体阴影({area} 5m)", "gdal")
        con = QgsVectorLayer(f"{con_path}|layername=contour",
                             f"地形·精细·等高线(5m·{area})", "ogr")
        for lyr in (hs, con):
            if not lyr.isValid():
                sys.exit(f"invalid: {lyr.name()}")
        style_hs(hs)
        style_contours(con)
        hs_layers.append(hs)
        con_layers.append(con)
        proj.addMapLayer(hs, False)
        proj.addMapLayer(con, False)

    dem30 = hs30 = None
    for rl in root.findLayers():
        if not rl.layer():
            continue
        if rl.layer().name().startswith("地形·高程"):
            dem30 = rl
        elif rl.layer().name().startswith("地形·山体阴影"):
            hs30 = rl
    if dem30 is None or hs30 is None:
        sys.exit("30m terrain layers not found; run add_terrain_layers.py first")

    parent = dem30.parent()
    i = parent.children().index(dem30)
    parent.insertChildNode(i, QgsLayerTreeLayer(con_layers[0]))
    parent.insertChildNode(i + 1, QgsLayerTreeLayer(con_layers[1]))
    j = parent.children().index(hs30)
    parent.insertChildNode(j, QgsLayerTreeLayer(hs_layers[0]))
    parent.insertChildNode(j + 1, QgsLayerTreeLayer(hs_layers[1]))
    print("inserted: 2x contours5m above DEM30, 2x hillshade5m above HS30")

    for rl in list(root.findLayers()):
        try:
            if rl.layer() is None and rl.name().startswith("地形·精细"):
                rl.parent().removeChildNode(rl)   # 历史 null 节点
                print(f"removed orphan node {rl.name()}")
        except RuntimeError:
            pass                                   # 节点已随层移除,跳过
    proj.write(path)
    print(f"saved {path}")


def main():
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    QgsApplication.initQgis()
    for p in sys.argv[1:]:
        add_to_project(p)
    QgsApplication.exitQgis()
    sys.stdout.flush()
    os._exit(0)   # 跳过解释器退出阶段,规避 PyQGIS 已知的退出段崩(写盘已完成)


if __name__ == "__main__":
    main()
