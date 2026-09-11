#!/usr/bin/env python3
"""Add terrain layers (hillshade + hypsometric DEM + contours) to projects.

Stack (panel top->bottom): ...admin/vectors, contours, DEM(multiply over
hillshade), hillshade, raster basemap.

Usage: python3 add_terrain_layers.py <project.qgs> [more.qgs ...]
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPainter
from qgis.core import (
    QgsApplication, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFillSymbol,
    QgsSingleSymbolRenderer, QgsRasterShader, QgsColorRampShader,
    QgsSingleBandPseudoColorRenderer, QgsSingleBandGrayRenderer,
    QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
    QgsVectorLayerSimpleLabeling, QgsUnitTypes, QgsLineSymbol,
    QgsSingleSymbolRenderer as _LSR, QgsLayerTreeLayer)

BASE = os.path.expanduser("~/qgis-data/au-terrain")
DEM = f"{BASE}/copdem_30m_mosaic.tif"
HS = f"{BASE}/hillshade_30m.tif"
CONTOURS = f"{BASE}/contours_20m.gpkg|layername=contour"

# 热度图色带:海拔 R-G 渐变(低=绿 -> 黄 -> 高=红),连续插值
RAMP = [
    (0, "#00b050"), (200, "#68c830"), (450, "#c8dc28"),
    (750, "#f0b028"), (1100, "#f06018"), (1500, "#e01010"),
]


def style_dem(layer):
    shader_fn = QgsColorRampShader()
    shader_fn.setColorRampType(QgsColorRampShader.Interpolated)
    shader_fn.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(v, QColor(c)) for v, c in RAMP])
    shader_fn.setMinimumValue(RAMP[0][0])     # 必须显式设边界,否则保存为 NaN
    shader_fn.setMaximumValue(RAMP[-1][0])    # NaN 会让颜色映射错乱(反色假象)
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(shader_fn)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))
    layer.setOpacity(0.75)
    layer.setBlendMode(QPainter.CompositionMode_Multiply)  # over hillshade


def style_hillshade(layer):
    layer.setRenderer(QgsSingleBandGrayRenderer(layer.dataProvider(), 1))
    layer.setOpacity(1.0)


def style_contours(layer):
    sym = QgsLineSymbol.createSimple({
        "line_color": "#7a5230", "line_width": "0.15"})
    layer.setRenderer(_LSR(sym))
    s = QgsPalLayerSettings()
    s.fieldName = "ELEV"
    s.placement = QgsPalLayerSettings.Line
    fmt = QgsTextFormat()
    fmt.setFont(QFont("DejaVu Sans"))
    fmt.setSize(7)
    fmt.setSizeUnit(QgsUnitTypes.RenderPoints)
    fmt.setColor(QColor("#5a3d22"))
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(1.2)
    buf.setSizeUnit(QgsUnitTypes.RenderPoints)
    buf.setColor(QColor("#ffffff"))
    fmt.setBuffer(buf)
    s.setFormat(fmt)
    s.scaleVisibility = True
    s.minimumScale = 60000            # visible when zoomed in past 1:60k
    s.maximumScale = 0
    s.setDataDefinedProperties(s.dataDefinedProperties())
    layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
    layer.setLabelsEnabled(True)
    layer.setScaleBasedVisibility(True)
    layer.setMinimumScale(100000)     # layer visible when scale <= 1:100k
    layer.setMaximumScale(0)


def add_to_project(path):
    proj = QgsProject()
    proj.read(path)
    print(f"loaded {path} ({len(proj.mapLayers())} layers)")

    for lid, lyr in list(proj.mapLayers().items()):
        name = lyr.name()
        if name.startswith("地形·"):
            proj.removeMapLayer(lid)
            print(f"removed previous {name}")

    hs = QgsRasterLayer(HS, "地形·山体阴影(Copernicus 30m)", "gdal")
    dem = QgsRasterLayer(DEM, "地形·高程(Copernicus 30m)", "gdal")
    con = QgsVectorLayer(CONTOURS, "地形·等高线(20m)", "ogr")
    for lyr in (hs, dem, con):
        if not lyr.isValid():
            sys.exit(f"invalid: {lyr.name()}")
    style_hillshade(hs)
    style_dem(dem)
    style_contours(con)
    for lyr in (hs, dem, con):
        proj.addMapLayer(lyr, False)

    root = proj.layerTreeRoot()
    node = None
    for rl in root.findLayers():
        try:
            if rl.layer() and rl.layer().type() == 1 \
                    and not rl.layer().name().startswith("地形"):
                node = rl      # the XYZ basemap, not terrain rasters
                break
        except RuntimeError:
            continue
    if node is None:           # 底图层读取瞬间失效时,按节点名兜底
        for rl in root.findLayers():
            try:
                if rl.name().startswith(("本地瓦片底图", "Local Tiles")):
                    node = rl
                    break
            except RuntimeError:
                continue
    if node is None:
        sys.exit("no raster basemap found")
    parent = node.parent()
    i = parent.children().index(node)
    parent.insertChildNode(i, QgsLayerTreeLayer(con))     # contours above DEM
    parent.insertChildNode(i + 1, QgsLayerTreeLayer(dem))
    parent.insertChildNode(i + 2, QgsLayerTreeLayer(hs))  # hillshade above raster
    print(f"inserted 3 terrain layers above '{node.name()}' at idx {i}")

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
