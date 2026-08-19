Factory MIS - Change-Driven Refresh Fix

Modified files:
1. app.py
2. app_core.py
3. mobile_cloud_app.py
4. sync_supabase_requests.py
5. run_sync_worker.bat

How it works:
- The sync worker now performs a lightweight check every 5 seconds.
- When a new cloud Stock-In / production / mould request is detected, it runs sync immediately.
- When local ProductionSchedule / Inventory / product or mould files change, it publishes the cloud snapshot immediately.
- Local Streamlit watches Inventory.xlsx and ProductionSchedule.xlsx every 5 seconds and reruns only when those files actually change.
- Cloud Streamlit watches the latest production/machine snapshot timestamps every 5 seconds and reruns only when published data actually changes.
- A full sync still runs every 300 seconds as a fallback.
- No new third-party dependency and no Supabase schema change are required.

Install:
Copy these five files over the same-name files in the Factory MIS source/project folder, then restart:
- local Factory MIS / Control Center
- Supabase sync worker
- cloud Streamlit deployment (for mobile_cloud_app.py)

Important:
The local sync worker window must remain running. START_FACTORY_MIS.bat / Control Center already starts run_sync_worker.bat in the original project.
