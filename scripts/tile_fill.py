#!/usr/bin/env python3
"""
z15-17 Tile Cache 补全 — 按城市人口密度排序
缺口 70,561 tiles ≈ 1GB。幂等 resume：已存在即跳过。
"""
import sys, os, time, math, json, signal
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import urllib.request

ESRI_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
CACHE_DIR = Path.home() / "qgis-data" / "tile-cache"
STATE_FILE = Path.home() / "qgis-data" / "tile-fill-progress.json"
LOCK_FILE = Path.home() / "qgis-data" / "tile-fill.lock"
PROXY = os.environ.get("CACHE_WARM_PROXY", "http://127.0.0.1:7892")
MAX_WORKERS = int(os.environ.get("CACHE_WARM_WORKERS", "12"))

# 城市按人口降序 (2024 ERP)
CITIES = [
    ("sydney",     150.7, -34.0, 151.5, -33.5),
    ("melbourne",  144.6, -38.2, 145.5, -37.5),
    ("brisbane",   152.7, -27.7, 153.3, -27.0),
    ("perth",      115.6, -32.4, 116.0, -31.7),
    ("adelaide",   138.4, -35.2, 138.8, -34.7),
    ("goldcoast",  153.2, -28.2, 153.5, -27.8),
    ("canberra",   149.0, -35.5, 149.3, -35.1),
    ("newcastle",  151.5, -33.1, 151.9, -32.7),
    ("coffs",      152.8, -30.4, 153.3, -29.9),
    ("wollongong", 150.8, -34.6, 151.0, -34.2),
    ("darwin",     130.8, -12.9, 131.0, -12.3),
    ("hobart",     147.2, -42.9, 147.4, -42.8),
]

# 城市中心（tile 队列按距中心距离排序 = 人口密度代理）
CENTERS = {c[0]: ((c[1]+c[3])/2, (c[2]+c[4])/2) for c in CITIES}

# 区域城镇 (z16-17, ~4km bbox): name, lon, lat
REGIONAL_TOWNS = [
    # NSW
    ("albury", 146.9, -36.1), ("armidale", 151.7, -30.5), ("bathurst", 149.6, -33.4),
    ("brokenhill", 141.5, -31.9), ("dubbo", 148.6, -32.2), ("goulburn", 149.7, -34.8),
    ("grafton", 152.9, -29.7), ("griffith", 146.0, -34.3), ("kempsey", 152.8, -31.1),
    ("lismore", 153.3, -28.8), ("orange", 149.1, -33.3), ("parkes", 148.0, -33.1),
    ("portmacquarie", 152.9, -31.4), ("queanbeyan", 149.2, -35.4), ("tamworth", 150.9, -31.1),
    ("taree", 152.5, -31.9), ("wagga", 147.4, -35.1), ("bowral", 150.4, -34.5),
    ("byronbay", 153.6, -28.6), ("inverell", 151.1, -29.8), ("moree", 149.8, -29.5),
    ("singleton", 151.2, -32.6), ("muswellbrook", 150.9, -32.3), ("nelsonbay", 152.2, -32.7),
    ("forster", 152.5, -32.2), ("ballina", 153.6, -28.9), ("casino", 153.0, -28.9),
    ("cessnock", 151.4, -32.8), ("mudgee", 149.6, -32.6), ("young", 148.3, -34.3),
    ("sawtell", 153.1, -30.4), ("woolgoolga", 153.2, -30.1), ("bowraville", 152.8, -30.6),
    # VIC
    ("ballarat", 143.9, -37.6), ("bendigo", 144.3, -36.8), ("geelong", 144.4, -38.2),
    ("wodonga", 146.9, -36.1), ("mildura", 142.1, -34.2), ("shepparton", 145.4, -36.4),
    ("traralgon", 146.5, -38.2), ("wangaratta", 146.3, -36.4), ("warrnambool", 142.5, -38.4),
    # QLD
    ("toowoomba", 151.9, -27.6), ("townsville", 146.8, -19.3), ("cairns", 145.8, -16.9),
    ("mackay", 149.2, -21.1), ("rockhampton", 150.5, -23.4), ("bundaberg", 152.3, -24.9),
    ("herveybay", 152.9, -25.3), ("gladstone", 151.2, -23.8),
    # WA
    ("bunbury", 115.6, -33.3), ("geraldton", 114.6, -28.8), ("kalgoorlie", 121.5, -30.8),
    ("albany", 117.9, -35.0), ("busselton", 115.3, -33.6),
    # SA
    ("mountgambier", 140.8, -37.8), ("whyalla", 137.6, -33.0), ("murraybridge", 139.3, -35.1),
    ("portaugusta", 137.8, -32.5),
    # TAS / NT
    ("launceston", 147.1, -41.4), ("devonport", 146.3, -41.2), ("burnie", 145.9, -41.1),
    ("alice", 133.9, -23.7),
]

# NSW 全州 z15（偏远地区兜底覆盖）
NSW_STATE_Z15 = {"min_lon": 141.0, "max_lon": 154.0, "min_lat": -38.0, "max_lat": -28.0}

stats_lock = threading.Lock()
stats = {"done": 0, "skip": 0, "fail": 0, "total": 0}
rate_limited = threading.Event()
stop_flag = threading.Event()


def acquire_lock():
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip() or 0)
            os.kill(pid, 0)
            print(f"ALREADY_RUNNING pid={pid}")
            return False
        except (ProcessLookupError, ValueError):
            LOCK_FILE.unlink(missing_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def tile_range(mnlon, mnlat, mxlon, mxlat, z):
    n = 2**z
    x0 = int((mnlon+180)/360*n); x1 = int((mxlon+180)/360*n)
    y0 = int((1-math.asinh(math.tan(math.radians(mxlat)))/math.pi)/2*n)
    y1 = int((1-math.asinh(math.tan(math.radians(mnlat)))/math.pi)/2*n)
    return x0, x1, y0, y1


def build_queue():
    """大城市(z15-17) → 区域城镇(z16-17) → NSW全州 z15。城内按距中心距离排序"""
    queue = []
    # 1. 大城市
    for name, mnlon, mnlat, mxlon, mxlat in CITIES:
        clon, clat = CENTERS[name]
        city_tiles = []
        for z in (15, 16, 17):
            x0, x1, y0, y1 = tile_range(mnlon, mnlat, mxlon, mxlat, z)
            for x in range(x0, x1+1):
                for y in range(y0, y1+1):
                    p = CACHE_DIR/str(z)/str(x)/f"{y}.png"
                    if not (p.exists() and p.stat().st_size > 500):
                        d = (x - (clon+180)/360*2**z)**2 + (y - (1-math.asinh(math.tan(math.radians(clat)))/math.pi)/2*2**z)**2
                        city_tiles.append((d, z, x, y))
        city_tiles.sort()
        queue.extend((name, z, x, y) for _, z, x, y in city_tiles)
        print(f"city {name:14s} +{len(city_tiles):>6,}")
    # 2. 区域城镇 (~4km bbox)
    D = 0.025  # ~2.5km 半径 → bbox ~5km
    for name, lon, lat in REGIONAL_TOWNS:
        town_tiles = []
        for z in (16, 17):
            x0, x1, y0, y1 = tile_range(lon-D, lat-D, lon+D, lat+D, z)
            for x in range(x0, x1+1):
                for y in range(y0, y1+1):
                    p = CACHE_DIR/str(z)/str(x)/f"{y}.png"
                    if not (p.exists() and p.stat().st_size > 500):
                        town_tiles.append((z, x, y))
        queue.extend((name, z, x, y) for z, x, y in town_tiles)
        if town_tiles:
            print(f"town {name:14s} +{len(town_tiles):>6,}")
    # 3. NSW 全州 z15（偏远地区）
    s = NSW_STATE_Z15
    x0, x1, y0, y1 = tile_range(s["min_lon"], s["min_lat"], s["max_lon"], s["max_lat"], 15)
    nsw = sum(1 for x in range(x0, x1+1) for y in range(y0, y1+1)
              if not (CACHE_DIR/"15"/str(x)/f"{y}.png").exists()
              or (CACHE_DIR/"15"/str(x)/f"{y}.png").stat().st_size <= 500)
    print(f"state nsw-z15        +{nsw:>6,} (偏远地区兜底，仅计数实际入队见下)")
    for x in range(x0, x1+1):
        for y in range(y0, y1+1):
            p = CACHE_DIR/"15"/str(x)/f"{y}.png"
            if not (p.exists() and p.stat().st_size > 500):
                queue.append(("nsw-z15", 15, x, y))
    return queue


def fetch_tile(z, x, y):
    url = ESRI_URL.format(z=z, y=y, x=x)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 QGIS-cache"})
    handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    opener = urllib.request.build_opener(handler)
    with opener.open(req, timeout=30) as resp:
        return resp.read()


def save_state():
    with stats_lock:
        STATE_FILE.write_text(json.dumps({
            **stats, "running": not stop_flag.is_set(),
            "ts": datetime.now().isoformat()}, ensure_ascii=False))


def worker(task):
    name, z, x, y = task
    if stop_flag.is_set():
        return "skip"
    p = CACHE_DIR/str(z)/str(x)/f"{y}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = fetch_tile(z, x, y)
        if len(data) > 500:
            p.write_bytes(data)
            return "ok"
        return "skip"
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            rate_limited.set()
        return "fail"
    except Exception:
        return "fail"


def main():
    if not acquire_lock():
        sys.exit(0)
    try:
        queue = build_queue()
        stats["total"] = len(queue)
        print(f"\n总缺口: {len(queue):,} tiles, workers={MAX_WORKERS}")
        if not queue:
            print("NOTHING_TO_DO")
            LOCK_FILE.unlink(missing_ok=True)
            return

        t0 = time.time()
        def on_stop(sig, frame):
            stop_flag.set()
            print("\nSTOP requested, finishing in-flight...")
        signal.signal(signal.SIGTERM, on_stop)
        signal.signal(signal.SIGINT, on_stop)

        # 分批提交（避免 1.35M Future 全量驻留内存 — 旧版泄漏 13.8GB RSS）
        import itertools
        from concurrent.futures import wait, FIRST_COMPLETED
        BATCH = 5000  # inflight Future 上限 ≈ ~50MB
        ex = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        queue_iter = iter(queue)
        pending = set()
        for t in itertools.islice(queue_iter, BATCH):
            pending.add(ex.submit(worker, t))
        i = 0
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                r = fut.result()
                i += 1
                with stats_lock:
                    stats["done" if r == "ok" else ("skip" if r == "skip" else "fail")] += 1
                nxt = next(queue_iter, None)
                if nxt is not None and not stop_flag.is_set():
                    pending.add(ex.submit(worker, nxt))
            if i % 500 == 0 or i >= stats["total"]:
                el = time.time()-t0
                rate = stats["done"]/el if el > 0 else 0
                eta = (stats["total"]-i)/rate/60 if rate > 0 else -1
                print(f"[{i:,}/{stats['total']:,}] ok={stats['done']:,} skip={stats['skip']:,} fail={stats['fail']:,} "
                      f"{rate:.1f}t/s eta={eta:.0f}min{'  ⚠ RATE_LIMITED' if rate_limited.is_set() else ''}",
                      flush=True)
                save_state()
            if rate_limited.is_set() and i % 50 == 0:
                print("  rate-limited, pausing workers 60s...", flush=True)
                time.sleep(60)
                rate_limited.clear()

        save_state()
        print(f"\nDONE ok={stats['done']:,} fail={stats['fail']:,} elapsed={(time.time()-t0)/60:.0f}min")
    finally:
        try:
            ex.shutdown(wait=True)
        except NameError:
            pass
        LOCK_FILE.unlink(missing_ok=True)
        save_state()


if __name__ == "__main__":
    main()
