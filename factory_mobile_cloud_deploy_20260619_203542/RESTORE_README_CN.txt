Factory MIS - 恢复到 2026-08-06 14:16 备份版（EVENT_REFRESH_FIX 之前）

本包只包含代码/启动文件，不包含 data 目录，也不会覆盖任何生产数据 Excel。

本地恢复文件：
- app.py
- app_core.py
- sync_supabase_requests.py
- run_sync_worker.bat

云端恢复文件（如果需要）：
- mobile_cloud_app.py
- requirements.txt

建议：
1. 完全关闭本地 MIS 和 sync worker。
2. 备份当前同名文件。
3. 先只覆盖本地 4 个文件。
4. 重新启动 MIS。
5. 新建一个测试 Production Plan。
6. 检查 data\\ProductionSchedule.xlsx 修改时间是否立刻更新。
7. 如果修改时间恢复，再测试手动 publish/sync。

不要覆盖 data 目录，不要替换 ProductionSchedule.xlsx / Inventory.xlsx。
