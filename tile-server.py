#!/usr/bin/env python3
"""Local tile server - cache-first with live-fetch fallback.

Request lifecycle (per tile GET):
- Cache hit  -> serve file immediately (~1ms)
- Cache miss -> enqueue a live-fetch task (UNBOUNDED FIFO queue, deduped
                at enqueue time) consumed by a SINGLE worker thread;
                the download completes inside this same request, saves into
                cache atomically and serves the real tile - no refresh needed
- ESRI no-data placeholder / fetch failure -> transparent PNG fallback,
                remembered in a negative cache so repeated panning over
                no-data areas does not hammer the upstream
"""
import hashlib
import json
import os
import queue
import sys
import time
import threading
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

CACHE_DIR = Path.home() / "qgis-data" / "tile-cache"
LOG_FILE = Path.home() / "qgis-data" / "tile-server.log"
QUEUE_FILE = Path.home() / "qgis-data" / "tile-queue.json"   # persistent queue state
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8088
TRANSPARENT_PNG = Path.home() / "qgis-data" / "transparent.png"

ESRI_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
PROXY = os.environ.get("CACHE_WARM_PROXY", "http://127.0.0.1:7892")
FETCH_TIMEOUT = 12          # seconds per tile request
MIN_VALID = 500             # bytes, same validity rule as tile_fill_vq.py
FETCH_Z_MIN, FETCH_Z_MAX = 0, 20   # live-fetch allowed zoom range

# ESRI "Map data not yet available" placeholder tiles — never cache these.
# Identified empirically: fixed 2521-byte JPEG served for any tile beyond
# the region's real imagery coverage.
PLACEHOLDER_MD5 = {
    "f27d9de7f80c13501f470595e327aa6d",   # ESRI World Imagery no-data placeholder
}

# Download task queue:
#  - PERSISTENT: pending tasks + negative-cache live in QUEUE_FILE and are
#    reloaded on startup, so a restart never loses queued work; the worker
#    just keeps downloading where it left off
#  - UNBOUNDED FIFO: any number of pending tasks may pile up while the
#    worker is busy; nothing is ever rejected
#  - DEDUPED on enqueue: a tile already queued/downloading is never
#    enqueued twice - later requests for it wait on the same task event
#  - SINGLE worker consumes the queue: exactly one download at a time,
#    running continuously in the background
NEG_TTL = 900          # seconds; placeholders stay "known empty" this long
NEG_TTL_FAIL = 300     # seconds; transient network failures retried sooner

_opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)
_task_q = queue.Queue()         # unbounded FIFO of pending download tasks
_queued = set()                 # rel -> currently queued or downloading (dedup)
_done_evt = {}                  # rel -> Event set when the task settles
_current = None                 # rel being downloaded by the worker right now
_q_lock = threading.Lock()
_neg = {}                       # rel -> expiry ts (placeholder / failed tiles)
_neg_lock = threading.Lock()


def _neg_put(rel: str, ttl: float) -> None:
    """Record a tile as known-empty; prune expired entries when large."""
    with _neg_lock:
        if len(_neg) > 20000:
            now = time.time()
            for k in [k for k, v in _neg.items() if v <= now]:
                _neg.pop(k, None)
        _neg[rel] = time.time() + ttl


def _save_state() -> None:
    """Persist pending tasks + negative cache to QUEUE_FILE (atomic)."""
    with _q_lock:
        pending = ([_current] if _current else []) + list(_task_q.queue)
    with _neg_lock:
        now = time.time()
        neg = {k: round(v, 1) for k, v in _neg.items() if v > now}
    try:
        tmp = QUEUE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"pending": pending, "neg": neg, "ts": now}))
        tmp.replace(QUEUE_FILE)
    except OSError:
        pass


def _load_state() -> None:
    """Reload persisted queue on startup; expired neg entries dropped."""
    try:
        data = json.loads(QUEUE_FILE.read_text())
    except (OSError, ValueError):
        return
    now = time.time()
    with _neg_lock:
        for rel, exp in (data.get("neg") or {}).items():
            if exp > now:
                _neg[rel] = exp
    restored = 0
    with _q_lock:
        for rel in data.get("pending") or []:
            if rel in _queued:
                continue
            _queued.add(rel)
            _done_evt[rel] = threading.Event()
            _task_q.put(rel)
            restored += 1
    if restored:
        log(f"restored {restored} pending task(s) from queue file")


def log(line: str) -> None:
    ts = time.strftime("%H:%M:%S")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{ts} {line}\n")
    except OSError:
        pass


def is_placeholder(data: bytes) -> bool:
    """True if tile bytes match a known upstream no-data placeholder."""
    if len(data) != 2521:            # cheap pre-filter, avoids md5 on every tile
        return False
    return hashlib.md5(data).hexdigest() in PLACEHOLDER_MD5


def read_valid(fp: Path):
    """Return file bytes if file exists and looks like a real tile."""
    try:
        data = fp.read_bytes()
        if is_placeholder(data):
            return None
        return data if len(data) > MIN_VALID else None
    except OSError:
        return None


def fetch_and_cache(rel: str):
    """Queue a download task for `z/x/y.ext` (unbounded, deduped), wait for
    the single worker to process it, then return bytes from cache or None.
    The tile lands in cache during this same request when it succeeds."""
    fp = CACHE_DIR / rel
    cached = read_valid(fp)
    if cached:
        return cached

    parts = rel.split("/")
    if len(parts) != 3:
        return None
    try:
        z = int(parts[0])
    except ValueError:
        return None
    if not (FETCH_Z_MIN <= z <= FETCH_Z_MAX):
        return None

    # recently known no-data / failed -> transparent immediately, no enqueue
    with _neg_lock:
        exp = _neg.get(rel)
        if exp is not None:
            if time.time() < exp:
                log(f"neg          {rel}")
                return None
            _neg.pop(rel, None)

    # enqueue once; duplicate requests share the same task event
    with _q_lock:
        ev = _done_evt.get(rel)
        if ev is None:
            ev = threading.Event()
            _done_evt[rel] = ev
            _queued.add(rel)
            _task_q.put(rel)
            new = True
        else:
            new = False
    if new:
        _save_state()                  # persist the newly queued task
        if _task_q.qsize() > 1:
            log(f"queued depth={_task_q.qsize()}  {rel}")

    ev.wait(FETCH_TIMEOUT + 15)      # queue may be long; wait our turn
    return read_valid(fp)


def _download_one(rel: str) -> None:
    """Download a single tile (runs ONLY in the single worker thread)."""
    fp = CACHE_DIR / rel
    parts = rel.split("/")
    if len(parts) != 3:
        return
    z_s, x_s, name = parts
    y_s = name.split(".")[0]
    try:
        z, x, y = int(z_s), int(x_s), int(y_s)
    except ValueError:
        return
    if not (FETCH_Z_MIN <= z <= FETCH_Z_MAX):
        return
    if read_valid(fp):                # filled by an earlier task
        return

    try:
        url = ESRI_URL.format(z=z, y=y, x=x)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 QGIS-cache"})
        with _opener.open(req, timeout=FETCH_TIMEOUT) as resp:
            data = resp.read()
        if len(data) > MIN_VALID and not is_placeholder(data):
            fp.parent.mkdir(parents=True, exist_ok=True)
            tmp = fp.with_name(fp.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(fp)          # atomic
            log(f"live {len(data):>7}B  {rel}")
        else:
            log(f"placeholder  {rel}")
            _neg_put(rel, NEG_TTL)
    except Exception:
        _neg_put(rel, NEG_TTL_FAIL)


def _download_worker() -> None:
    """Single consumer of the unbounded deduped persistent task queue.
    Runs continuously in the background; survives restarts via QUEUE_FILE."""
    global _current
    while True:
        rel = _task_q.get()
        with _q_lock:
            _current = rel
        try:
            _download_one(rel)
        except Exception:
            pass
        finally:
            with _q_lock:
                _current = None
                _queued.discard(rel)
                ev = _done_evt.pop(rel, None)
            if ev:
                ev.set()             # wake all requesters waiting on this tile
            _save_state()            # persist progress (task removed)
            _task_q.task_done()


def detect_mime(data: bytes) -> str:
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "application/octet-stream"


def serve_bytes(self, data: bytes, status=200, cache_hdr=None):
    self.send_response(status)
    self.send_header("Content-Type", detect_mime(data))
    self.send_header("Content-Length", str(len(data)))
    self.send_header("Cache-Control", cache_hdr or "public, max-age=86400")
    self.end_headers()
    self.wfile.write(data)


class TileHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        clean = self.path.split("?")[0].strip("/")
        file_path = CACHE_DIR / clean

        # 1) cache hit
        data = read_valid(file_path)
        if data:
            serve_bytes(self, data, cache_hdr="public, max-age=31536000, immutable")
            log(f"200 {len(data):>7}B  {self.path}")
            return

        # 2) cache miss -> queue live-fetch task, wait for the single worker
        fetched = fetch_and_cache(clean)
        if fetched:
            serve_bytes(self, fetched)   # download already logged by worker
            return

        # 3) fallback: transparent PNG
        try:
            data = TRANSPARENT_PNG.read_bytes()
        except OSError:
            data = b""
        serve_bytes(self, data)
        log(f"--- transparent  {self.path}")

    def log_message(self, *a):   # silence default stderr logging
        pass


def main():
    _load_state()                    # restore pending tasks from QUEUE_FILE
    threading.Thread(target=_download_worker, daemon=True, name="tile-dl").start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), TileHandler)
    print(f"🗺️  Tile server (persistent queue) on http://127.0.0.1:{PORT}")
    log(f"--- Started {time.strftime('%Y-%m-%d %H:%M:%S')} (persistent unbounded deduped queue, single worker) ---")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
