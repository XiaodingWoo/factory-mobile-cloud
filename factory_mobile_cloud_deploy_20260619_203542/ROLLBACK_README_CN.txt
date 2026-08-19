Factory MIS 自动同步/自动刷新回退包
====================================

来源：你最初上传的 FactoryMIS_Company_Test_20260621.zip。
本包没有保留后续自动刷新、事件刷新、5秒 worker 修改。

需要恢复的本地文件：
1. app.py
2. app_core.py
3. sync_supabase_requests.py
4. run_sync_worker.bat

需要恢复的云端文件：
5. mobile_cloud_app.py
6. requirements.txt

建议操作顺序：
A. 先停止本地 MIS 和 sync worker。
B. 备份你当前同名文件。
C. 用本包文件覆盖同名文件。
D. 重新启动本地 MIS。
E. 先测试原来的“手动同步”是否恢复。
F. 云端 GitHub 只需要把 mobile_cloud_app.py 和 requirements.txt 恢复到本包版本并提交，等待重新部署。

注意：
- 不要再使用 FactoryMIS_EVENT_REFRESH_FIX 里的文件。
- 不要再使用 FactoryMIS_5MIN_AUTO_REFRESH_FIX / SAFE_FIX 里的文件。
- 这次目标只是回到你上传原始项目时的同步逻辑，不增加任何自动同步功能。
