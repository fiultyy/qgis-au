#!/usr/bin/env python3
"""Download ABS ASGS admin boundaries (LGA 2025 + SAL 2021) -> au-admin/.

Downloads official ABS digital boundary files, unzips them and converts to
a single GeoPackage au-admin/admin_boundaries.gpkg (layers: lga, sal).
SAL is lightly simplified (~20m) for fast rendering; LGA kept as-is.

Usage: python3 fetch_admin_boundaries.py
"""
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
import urllib.request

BASE = Path.home() / "qgis-data" / "au-admin"
BASE.mkdir(parents=True, exist_ok=True)
PROXY = os.environ.get("CACHE_WARM_PROXY", "http://127.0.0.1:7892")
URL_BASE = ("https://www.abs.gov.au/statistics/standards/"
            "australian-statistical-geography-standard-asgs/"
            "edition-3-july-2021-june-2026/access-and-downloads/"
            "digital-boundary-files")
FILES = {                      # zip -> (target layer, simplify tolerance deg)
    "LGA_2025_AUST_GDA2020.zip": ("lga", None),
    "SAL_2021_AUST_GDA2020_SHP.zip": ("sal", "0.0002"),
}
GPKG = BASE / "admin_boundaries.gpkg"

_opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def download(name: str) -> Path:
    dest = BASE / name
    if dest.exists() and dest.stat().st_size > 100_000:
        log(f"skip download {name} ({dest.stat().st_size/1e6:.0f} MB present)")
        return dest
    url = f"{URL_BASE}/{name}"
    tmp = dest.with_suffix(".part")
    log(f"downloading {name}")
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with _opener.open(req, timeout=120) as r, open(tmp, "wb") as f:
        total = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
            if total % (20 << 20) < (1 << 20):
                log(f"  {total/1e6:5.0f} MB ...")
    tmp.replace(dest)
    log(f"done {name}: {dest.stat().st_size/1e6:.1f} MB in {time.time()-t0:.0f}s")
    return dest


def unzip(fp: Path) -> Path:
    out = BASE / fp.stem
    if not any(out.rglob("*.shp")) and not any(out.rglob("*.gpkg")):
        out.mkdir(exist_ok=True)
        log(f"unzipping {fp.name} -> {out.name}/")
        with zipfile.ZipFile(fp) as z:
            z.extractall(out)
    return out


def convert(out_dir: Path, layer: str, simplify):
    src = None
    for cand in out_dir.rglob("*.gpkg"):
        src = cand
    if src is None:
        for cand in out_dir.rglob("*.shp"):
            src = cand
    if src is None:
        raise RuntimeError(f"no .shp/.gpkg found under {out_dir}")
    cmd = ["ogr2ogr", "-f", "GPKG", str(GPKG), str(src),
           "-nln", layer, "-nlt", "PROMOTE_TO_MULTI", "-update", "-overwrite"]
    if simplify:
        cmd += ["-simplify", simplify]
    log(f"ogr2ogr {layer} <- {src.name} {'simplify='+simplify if simplify else ''}")
    t0 = time.time()
    subprocess.run(cmd, check=True)
    n = subprocess.run(["ogrinfo", "-so", str(GPKG), layer, "-al"],
                       capture_output=True, text=True).stdout
    feats = [l for l in n.splitlines() if "Feature Count" in l]
    log(f"layer {layer} ready in {time.time()-t0:.0f}s | {feats[0].strip() if feats else '?'}")


def main():
    for zip_name, (layer, simplify) in FILES.items():
        fp = download(zip_name)
        out = unzip(fp)
        convert(out, layer, simplify)
    log(f"GPKG: {GPKG} ({GPKG.stat().st_size/1e6:.0f} MB)")


if __name__ == "__main__":
    main()
