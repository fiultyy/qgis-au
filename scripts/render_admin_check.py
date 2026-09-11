#!/usr/bin/env python3
"""Render verification for admin layers: headless map renders from the real
project at two scales, saved as PNGs for visual inspection.

Usage: python3 render_admin_check.py <project.qgs>
Outputs: /tmp/admin-check-*.png
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import (QgsApplication, QgsProject, QgsMapSettings, QgsRectangle,
                       QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsMapRendererParallelJob)

CENTER_3857 = QgsCoordinateTransform(
    QgsCoordinateReferenceSystem("EPSG:4326"),
    QgsCoordinateReferenceSystem("EPSG:3857"),
    QgsProject.instance())

VIEWS = [
    # name, lon, lat, scale
    ("sydney-z150k", 151.205, -33.865, 150000),
    ("coffs-z40k", 153.114, -30.307, 40000),
]


def bbox(lon, lat, scale, w=1150, h=820):
    """Map extent for given scale & canvas px (3857 meters)."""
    mx, my = CENTER_3857.transform(lon, lat)
    half_w = 0.0002646 * scale * w / 2      # px(m) * scale / 2
    half_h = 0.0002646 * scale * h / 2
    return QgsRectangle(mx - half_w, my - half_h, mx + half_w, my + half_h)


def main(project_path):
    proj = QgsProject()
    proj.read(project_path)
    layers = {l.name(): l for l in proj.mapLayers().values()}
    admin = [v for k, v in layers.items() if k.startswith("行政区划")]
    terrain = [v for k, v in layers.items() if k.startswith("地形")]
    if not admin:
        sys.exit("no admin layers in project")
    tiles = [v for k, v in layers.items()
             if v.type() == 1 and not k.startswith("地形")]
    t_hs30 = [v for k, v in layers.items() if k.startswith("地形·山体阴影")]
    t_hs5m = sorted((v for k, v in layers.items()
                     if k.startswith("地形·精细·山体阴影")), key=lambda l: l.name())
    t_dem = [v for k, v in layers.items() if k.startswith("地形·高程")]
    t_con20 = [v for k, v in layers.items() if k.startswith("地形·等高线")]
    t_con5m = sorted((v for k, v in layers.items()
                      if k.startswith("地形·精细·等高线")), key=lambda l: l.name())
    print(f"admin:{len(admin)} hs30:{len(t_hs30)} hs5m:{len(t_hs5m)} "
          f"dem:{len(t_dem)} con20:{len(t_con20)} con5m:{len(t_con5m)} "
          f"raster:{len(tiles)}")

    for name, lon, lat, scale in VIEWS:
        ms = QgsMapSettings()
        ms.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        ms.setOutputSize(__import__("PyQt5.QtCore", fromlist=["QSize"]).QSize(1150, 820))
        ms.setOutputDpi(96)
        ms.setExtent(bbox(lon, lat, scale))
        ms.setLayers(tiles + t_hs30 + t_hs5m + t_dem + t_con20 + t_con5m + admin)
        job = QgsMapRendererParallelJob(ms)
        job.start()
        job.waitForFinished()
        out = f"/tmp/admin-check-{name}.png"
        job.renderedImage().save(out)
        print(f"saved {out} (errors: {job.errors()[:3]})")


if __name__ == "__main__":
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    QgsApplication.initQgis()
    main(sys.argv[1])
    QgsApplication.exitQgis()
