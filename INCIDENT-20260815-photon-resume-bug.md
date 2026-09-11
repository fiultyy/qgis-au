# INCIDENT 2026-08-15: Photon geocode resume bug（已修复）

## 发现
cron 自动续跑（04:36 触发）探测到 Photon API 恢复，按 `--start 37005` 重启脚本后，
日志显示 `Processing 73,091 records`（应为 36,086）→ resume 未生效。

## 根因
`photon_geocode_v2.py` 的 `load_all_records()` 依赖 `layer.SetNextByIndex(start_idx)` 跳过
已处理记录，但该调用在本环境（GDAL GPKG + Python 迭代）是**静默 no-op**（已实证：设
37005 后迭代仍返回全部 73,091 条）。

后果（历史累积，非仅本次）：
- 每次 resume 都从 idx 0 重跑 → 输出 GPKG 重复追加（26,255 行 vs 真实 6,707 distinct keys）
- failed CSV 反复重写（46,247 行 vs 计数器 18,224）
- progress.json 的 `processed: 37005` 为虚增（多次 run 的 delta 累加），真实覆盖仅 idx 0~约 17,000
- 旧 cron 消息的完成判定 `processed >= 73091` 永远无法正确触发

## 处置（本次会话完成）
1. kill 运行中的重跑进程（PID 892124，运行约 7 分钟，追加了 ~7,474 重复行）
2. 备份全部工件 → `backup-20260815/`（GPKG/failed CSV/progress/脚本）
3. 输出 GPKG 按 `(property_id, sale_counter)` 去重：26,255 → **6,707 行**（唯一身份键；
   输入表 73,091 行仅 49,826 distinct keys，最大重复 75 次 —— key 去重同时消除了输入噪声）
4. 脚本修复（已通过隔离端到端测试，见下）：
   - `load_all_records`: enumerate + 手动跳过，弃用 SetNextByIndex
   - resume 改为 **key-skip 幂等**：启动时从输出 GPKG 加载 matched keys，跳过对应输入行
   - `--start` 废弃（打印提示并忽略），任何旧指令调用都安全
   - `processed` 语义 = 输入行覆盖数（matched keys 覆盖行 + 本次尝试行），完成时 = 73,091，
     兼容旧完成判定
   - 完成时 progress.json 写入 `done: true` + `finished_at`
   - failed CSV 每 run 重写（失败 key 在下次 resume 自动重试）
   - matched 计数自校验（以输出 GPKG 内容为唯一真值）
5. progress.json 重置为真实值 `{"processed": 6707, "matched": 6707, "failed": 0}`

## 测试证据
- 切片：`load_all_records(6707)` → 66,384 条，首 idx=6707 ✓
- key-skip：6,707 keys 覆盖 17,699 输入行，余 55,392 待处理（17,699+55,392=73,091）✓
- mock 端到端（临时文件）：匹配追加 / 失败记录 / done 标志 / 进度算术 全部正确 ✓

## 当前状态与预期
- Photon 在修复期间再度限流（preflight 0/5），未启动正式跑；cron（30 分钟间隔）会在
  API 恢复后自动重启 `--start 0`（全扫描 + key-skip，跳过部分零 API 消耗）
- 剩余 43,119 个未匹配 key（55,392 行），约 3/s → 预计 ~5 小时
- 已通知主会话更新 cron job 消息（隔离会话无权限直接 patch cron）

## 脚本行为速查（v3）
- 单实例：photon.lock（PID 存活检测，陈锁自动回收）
- preflight <3/5 → 干净退出不动数据
- 批 1000 写 progress；批命中率 <5% → RATE_LIMITED_SUSPECTED 批边界安全停止
- 完成判定：progress.json `done: true`

## 后记（2026-08-16 01:06 终跑完成时发现）

终跑 PASS_COMPLETE（attempted 16,120/16,120，processed=73,091 全覆盖）后校验发现
**v3 残留缺陷**：key-skip 只在启动时从输出 GPKG 加载 `done_keys`，运行中不更新、
不检查。队列内同 key 多行输入（73,091 行 / 49,826 distinct keys）在单次 run 内被
重复 geocode + append → 输出累计 4,557 行重复（3,887 组，其中 142 组坐标不一致，
系同 key 不同地址变体）。

处置：按既定 key 去重程序（保留每组最早 fid），52,916 → **48,359 行**，0 重复。
去重前备份 `backup-20260815/nsw-property-photon-geocoded.gpkg.prededup-20260816`。
progress.json 已按 distinct-key 口径修正（matched=48,359 / failed=1,467）。

最终统计（distinct-key 口径）：
- 输入：73,091 行 / 49,826 keys
- 匹配：48,359 keys（**97.05%**）
- 未匹配：1,467 keys（failed CSV 本 run 行级失败 1,688 行）

后续如再跑批量 geocode：done_keys 需随每次 append 即时更新（in-run 幂等），
或队列构建时先按 key 去重。
