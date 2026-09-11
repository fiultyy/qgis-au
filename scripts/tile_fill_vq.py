#!/usr/bin/env python3
"""
VIC + QLD 全州 z15 补全 + 新增城镇 z16-17 — 与 NSW 同级覆盖
幂等 resume：已存在(>500B)即跳过。引擎同 tile_fill.py（分批提交/限流退避/断点续传）。
"""
import sys, os, time, math, json, signal
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading
import urllib.request

ESRI_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
CACHE_DIR = Path.home() / "qgis-data" / "tile-cache"
STATE_FILE = Path.home() / "qgis-data" / "tile-fill-vq-progress.json"
LOCK_FILE = Path.home() / "qgis-data" / "tile-fill-vq.lock"
PROXY = os.environ.get("CACHE_WARM_PROXY", "http://127.0.0.1:7892")
MAX_WORKERS = int(os.environ.get("CACHE_WARM_WORKERS", "12"))

# 新增城镇 z16-17（旧 63 城镇已在缓存，exists() 自动跳过）
TOWNS = [
    # VIC
    ("horsham", 142.2, -36.7), ("swanhill", 143.6, -35.3), ("sale", 147.1, -38.1),
    ("bairnsdale", 147.6, -37.8), ("echuca", 144.7, -36.3), ("colac", 143.6, -38.3),
    ("hamilton", 142.0, -37.7), ("moe", 146.2, -38.2), ("seymour", 145.1, -37.0),
    ("cobram", 145.7, -35.9), ("stawell", 142.8, -37.1), ("kyabram", 145.0, -36.3),
    # QLD
    ("mtisa", 139.5, -20.7), ("emerald", 148.2, -23.5), ("roma", 148.8, -26.6),
    ("charterstowers", 146.3, -20.1), ("ingham", 146.2, -18.7), ("ayr", 147.4, -19.6),
    ("bowen", 148.2, -20.0), ("proserpine", 148.6, -20.4), ("kingaroy", 151.8, -26.5),
    ("dalby", 151.3, -27.2), ("warwick", 152.1, -28.2), ("goondiwindi", 150.3, -28.5),
    ("longreach", 145.2, -23.4), ("atherton", 145.5, -17.3),
]

# 全州 z15 兜底 bbox
VIC_STATE_Z15 = {"min_lon": 140.9, "max_lon": 150.05, "min_lat": -39.3, "max_lat": -33.95}
QLD_STATE_Z15 = {"min_lon": 137.9, "max_lon": 153.8, "min_lat": -29.1, "max_lat": -9.0}

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
    """城镇(z16-17) → VIC全州z15 → QLD全州z15。州内从南向北（人口优先）"""
    queue = []
    # 1. 新增城镇 z16-17 (~5km bbox)
    D = 0.025
    for name, lon, lat in TOWNS:
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
            print(f"town {name:16s} +{len(town_tiles):>6,}")
    # 2. 全州 z15（南→北，人口密度优先）
    for state, s in (("vic-z15", VIC_STATE_Z15), ("qld-z15", QLD_STATE_Z15)):
        x0, x1, y0, y1 = tile_range(s["min_lon"], s["min_lat"], s["max_lon"], s["max_lat"], 15)
        cnt = 0
        for y in range(y1, y0-1, -1):          # y1=南 → y0=北
            for x in range(x0, x1+1):
                p = CACHE_DIR/"15"/str(x)/f"{y}.png"
                if not (p.exists() and p.stat().st_size > 500):
                    queue.append((state, 15, x, y))
                    cnt += 1
        print(f"state {state:16s} +{cnt:>8,}")
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

        # 分批提交（同 tile_fill.py，避免 Future 全量驻留）
        import itertools
        from concurrent.futures import wait, FIRST_COMPLETED
        BATCH = 5000
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
