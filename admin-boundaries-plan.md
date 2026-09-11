# 行政区划色块层实施计划

> ✅ **已于 2026-08-24 实施完成** — 数据 `au-admin/admin_boundaries.gpkg`(LGA 2025: 567 / SAL 2021: 15,353,join 全量成功,272 中心镇,19 离岛未匹配),脚本 `scripts/fetch_admin_boundaries.py` / `build_admin_layers.py` / `add_admin_layers.py`,已加入 au-property-master.qgs 与 nsw-final.qgs。渲染验证:Sydney 1:150k 22 个 LGA 色块 + 标注;Coffs 1:40k SAL 街区 + 11 个名称标注。
>
> 生成: 2026-08-24 | 针对 nsw-final.qgs / au-property-master.qgs
> 需求: 按官方行政区划划分色块,城市拆到区,城镇/郊区按行政中心镇归组,色块上带文字标注

---

## 一、现状摸底

| 项 | 现状 |
|---|---|
| 底图 | 本地瓦片 `http://127.0.0.1:8088/{z}/{x}/{y}.png`(ESRI World Imagery,缓存 13GB / 92.7 万片,z0-17),tile-server 已支持 miss 即时下载落盘 |
| nsw-final.qgs | Local Tiles 底图 + NSW Matched Final(parcel 级 1.9M 点)+ NSW Geocoded 兜底(50K 点) |
| au-property-master.qgs | 本地瓦片 + NSW/VIC 地块边界 + 成交 + Coffs 系列(含 ABS 邮区) |
| 图层构建方式 | 全部通过 PyQGIS headless 脚本生成(`scripts/make_final_project.py` 模式:QgsCategorizedSymbolRenderer 分类渲染),**尚无任何行政区划面层** |
| 已有官方数据 | NSW/VIC 地块 cadastre(GPKG)、ABS 邮区(仅 Coffs),未下载过 LGA/SAL |

## 二、官方数据源(均为免费、政府官方、可直接下载)

| 层级 | 数据集 | 直链(ABS ASGS Edition 3) | 用途 |
|---|---|---|---|
| **LGA 2025** | Local Government Areas(地方政府区,GeoPackage) | `https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/access-and-downloads/digital-boundary-files/LGA_2025_AUST_GDA2020.zip` | 城市→区 一级色块(如 Coffs Harbour、City of Sydney) |
| **SAL 2021** | Suburbs and Localities(郊区/城镇,Shapefile) | 同目录 `SAL_2021_AUST_GDA2020_SHP.zip` | 城镇/郊区二级色块 + 文字标注(全澳 ~1 万个 locality,最新版即 2021) |
| **UCL 2021** | Urban Centres and Localities | 同目录 `UCL_2021_AUST_GDA2020_SHP.zip` | (可选)识别"行政中心镇"城镇实体,给中心镇加粗标注 |
| 备选 | Digital Atlas of Australia | `https://digital.atlas.gov.au/`(托管 WMS/WFS,ABS 同源) | 不想落盘时在线引用 |

说明:
- LGA 是 ABS Mesh Block 对官方 Gazetteed 边界的近似,即"官方行政区划"的权威免费版本;需严格法定边界可另购 Geoscape Administrative Boundaries,本需求用 ABS 足够。
- 坐标系 GDA2020(EPSG:7844),QGIS 工程 EPSG:3857 动态投影,无需转换。

## 三、"城市拆到区 / 郊区按行政中心镇"的映射

官方层级: **State → LGA(区/市)→ SAL(郊区/城镇 locality)**

1. **LGA 层 = "城市拆到区"**:每个 LGA(Sydney、Coffs Harbour、Blacktown…)一个色块,颜色按 LGA_CODE 哈希取 12-16 色板,相邻不重色可后续优化。
2. **SAL 层 = "城镇/郊区色块"**:空间 join 落入的 LGA,继承其所属 LGA 的颜色 → **郊区按行政中心镇(LGA 驻地)归组着色**,即同一行政区内所有郊区同色系。
3. **中心镇高亮**(可选):SAL 名称与所属 LGA 名匹配(如 SAL "Coffs Harbour" ⊂ LGA "Coffs Harbour (A)")→ 标注加粗 + 描边加粗,视觉上即"行政中心镇"。
4. **文字标注**:LGA_NAME(低缩放级)+ SAL_NAME(高缩放级)双向标注,带白色 buffer 保证影像底图上可读。

## 四、实施步骤(全部脚本化,沿用现有 PyQGIS 模式)

### Step 1 — 下载数据 `scripts/fetch_admin_boundaries.py`
- 下载 LGA_2025_AUST_GDA2020.zip、SAL_2021_AUST_GDA2020_SHP.zip、UCL(可选)到 `au-admin/`
- 解压 → 统一转为 GeoPackage:`au-admin/admin_boundaries.gpkg`(layers: lga / sal / ucl)
- 全澳入库后按需裁剪(NSW 优先,保留全澳备用;SAL 全澳约 300MB 级,可承受)

### Step 2 — 空间 join 归组 `scripts/build_admin_layers.py`
- SAL ∩ LGA(质心落入法)→ SAL 表加字段 `lga_code`、`lga_name`、`is_centre`(中心镇判定)
- 生成色带字段 `color_key = lga_code`

### Step 3 — 加入 QGIS 工程 `scripts/add_admin_layers.py`(PyQGIS headless)
- 读入现有 .qgs → 追加两个面层(插到瓦片底图之上、地籍层之下,半透明 fill 35% + 1.2mm 描边)
- **LGA 层**:QgsCategorizedSymbolRenderer 按 LGA_NAME 分类,`Random colors` 色板;标注 QgsPalLayerSettings(field=LGA_NAME, size 11pt, buffer 2mm 白),`scaleVisibility` 设为 < 1:200,000 显示标注
- **SAL 层**:分类渲染按 `lga_code`(同组同色),标注 field=SAL_NAME(size 9pt),scaleVisibility > 1:50,000;`is_centre=true` 用 rule-based 加粗样式
- 保存为新工程或原工程(参数 `--project`)
- 渲染细节:fill 用 `color_hsv((hash(lga_code)%360), 60%, 70%, 35)` 保证一致且半透明,不遮影像

### Step 4 — 验证
- QGIS 打开工程:缩放到 Sydney(城市→LGA 多色区块+区名)→ 放大到 Coffs Harbour(郊区同色系块+SAL 名,中心镇加粗)
- 色块与瓦片底图叠加可读;缩放分级切换标注

## 五、工作量与风险

| 项 | 估计 |
|---|---|
| 下载+转换 | LGA ~50MB / SAL ~300MB,10-20 分钟 |
| join + 建层脚本 | 半天 |
| 风险 | ① SAL 2021 后无新版(郊区边界 5 年内变动极小,可接受);② 跨界 SAL 质心落错 LGA → 用最大重叠面积法兜底;③ ABS 站点限速 → 走现有代理 `http://127.0.0.1:7892` |
