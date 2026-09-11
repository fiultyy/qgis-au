#!/usr/bin/env python3
"""计算东南沿海 DEM 瓦片清单:阿德莱德→布里斯班海岸线,内陆 150km。

规则:1° 瓦片中心距海岸折线 ≤150km 且位于行进方向左侧(陆地侧,逆时针)。
输出:stdout 瓦片名列表(S{lat}_00_E{lon}_00 形式),stderr 统计。
"""
import math

# 海岸线折线(逆时针: 阿德莱德 → 维州南岸 → 新州南海岸 → 悉尼 → 布里斯班)
COAST = [
    (138.58, -34.93),  # Adelaide
    (138.20, -35.60),  # Fleurieu Peninsula
    (138.90, -35.55),  # Murray Mouth
    (139.70, -36.10),  # Coorong
    (139.87, -36.94),  # Kingston SE
    (141.60, -38.35),  # Portland
    (142.50, -38.38),  # Warrnambool
    (143.50, -38.85),  # Cape Otway
    (144.30, -38.35),  # Torquay
    (144.65, -38.30),  # Port Phillip Heads
    (145.00, -38.00),  # Melbourne
    (145.30, -38.50),  # Western Port
    (146.40, -39.05),  # Wilsons Prom
    (147.50, -38.30),  # Ninety Mile Beach
    (147.90, -37.87),  # Lakes Entrance
    (148.70, -37.80),  # Cape Conran
    (149.98, -37.50),  # Cape Howe
    (149.90, -37.07),  # Eden
    (150.18, -35.70),  # Batemans Bay
    (150.70, -35.10),  # Jervis Bay
    (150.90, -34.40),  # Wollongong
    (151.30, -33.90),  # Sydney
    (151.78, -32.93),  # Newcastle
    (152.90, -31.43),  # Port Macquarie
    (153.11, -30.30),  # Coffs Harbour
    (153.63, -28.65),  # Byron Bay
    (153.50, -28.20),  # Gold Coast
    (153.20, -27.45),  # Brisbane
]

INLAND_KM = 150.0


def km_xy(lon, lat):
    """把经纬度转成局部平面 km 坐标(以给定点为原点足够近的线段内使用)。"""
    return lon * 111.32 * math.cos(math.radians(lat)), lat * 110.574


def seg_dist_side(p, a, b):
    """点到线段距离(km)与方向侧(+1=行进方向左侧=陆地)。"""
    ax, ay = km_xy(a[0], a[1])
    bx, by = km_xy(b[0], b[1])
    px, py = km_xy(p[0], p[1])
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        d = math.hypot(px - ax, py - ay)
        return d, 1
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    cx, cy = ax + t * dx, ay + t * dy
    d = math.hypot(px - cx, py - cy)
    cross = dx * (py - cy) - dy * (px - cx)
    side = 1 if cross > 0 else -1
    return d, side


def coast_info(lon, lat):
    best_d, best_side = 1e18, -1
    for i in range(len(COAST) - 1):
        d, s = seg_dist_side((lon, lat), COAST[i], COAST[i + 1])
        if d < best_d:
            best_d, best_side = d, s
    return best_d, best_side


def main():
    tiles = []
    for lat0 in range(-40, -25):
        for lon0 in range(136, 156):
            cx, cy = lon0 + 0.5, lat0 + 0.5
            d, side = coast_info(cx, cy)
            if d <= INLAND_KM and side > 0:
                tiles.append((lat0, lon0, round(d)))
    tiles.sort(key=lambda t: (t[0], t[1]))
    for lat0, lon0, d in tiles:
        print(f"S{-lat0:02d}_00_E{lon0:03d}_00")
    import sys
    print(f"共 {len(tiles)} 块", file=sys.stderr)


if __name__ == "__main__":
    main()
