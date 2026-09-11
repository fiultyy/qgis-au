#!/usr/bin/env python3
"""Set zmin/zmax on XYZ (wms-provider) tile layers via the official API.

Replaces the old raw-XML sed surgery on .qgs files.

Usage: python3 set_xyz_zoom.py --zmax 20 [--zmin 0] <project.qgs> [...]
"""
import os
import sys
import urllib.parse

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication, QgsProject


def set_zoom(project_path, zmin, zmax):
    proj = QgsProject()
    proj.read(project_path)
    changed = 0
    for lyr in list(proj.mapLayers().values()):
        if lyr.type() != 1 or lyr.providerType() != "wms":
            continue
        src = lyr.source()
        if "type=xyz" not in src:
            continue
        q = urllib.parse.parse_qs(src.split("?", 1)[1])
        cur_max = int(q.get("zmax", ["0"])[0])
        cur_min = int(q.get("zmin", ["0"])[0])
        if cur_max == zmax and cur_min == zmin:
            continue
        q["zmax"] = [str(zmax)]
        q["zmin"] = [str(zmin)]
        new_q = "&".join(f"{k}={v[0]}" for k, v in q.items())
        lyr.setDataSource(f"type=xyz&{new_q}", lyr.name(), "wms")
        changed += 1
        print(f"  {lyr.name()}: zmin={zmin} zmax={zmax}")
    if changed:
        proj.write(project_path)
    print(f"{project_path}: {changed} layer(s) updated, saved")


def main():
    args = sys.argv[1:]
    zmax, zmin = 20, 0
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--zmax":
            zmax = int(args[i + 1]); i += 2
        elif args[i] == "--zmin":
            zmin = int(args[i + 1]); i += 2
        else:
            rest.append(args[i]); i += 1
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    QgsApplication.initQgis()
    for p in rest:
        set_zoom(p, zmin, zmax)
    QgsApplication.exitQgis()
    sys.stdout.flush()
    os._exit(0)   # 跳过解释器退出阶段,规避 PyQGIS 已知的退出段崩(写盘已完成)


if __name__ == "__main__":
    main()
