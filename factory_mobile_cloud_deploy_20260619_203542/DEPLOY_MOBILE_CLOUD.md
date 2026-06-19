# Deploy Factory Mobile Cloud

`mobile_cloud_app.py` and `mobile_cloud_config.py` form the cloud-only mobile application.

It does not import `data_manager.py`, does not read `data/*.xlsx`, and does not use the Supabase service role key.

It only:

- selects `mobile_public_machines`
- selects active `mobile_public_products`
- inserts pending rows into `stock_in_requests`

The local factory computer remains responsible for publishing snapshots and applying pending Stock-In requests to Excel.

## Required Cloud Environment Variables

Configure only:

```text
SUPABASE_URL
SUPABASE_ANON_KEY
MOBILE_PIN
```

Never configure these in the cloud Mobile App:

```text
SUPABASE_SERVICE_ROLE_KEY
```

The service role key remains only in the local factory computer `.env`.

## Apply the Supabase Migration

Before deploying, run this file once in Supabase SQL Editor:

```text
supabase_cloud_snapshot_migration.sql
```

This expands product codes to `text`, adds the extended machine snapshot fields, enforces `client_request_id` uniqueness, and applies RLS:

- anon can select active machine snapshots
- anon can select active products
- anon can insert pending positive Stock-In requests
- anon cannot select Stock-In requests
- anon cannot update or delete Stock-In requests

## Option A: Streamlit Community Cloud

1. Put the deployment files in a private GitHub repository.
2. Do not commit `.env`.
3. Sign in to Streamlit Community Cloud.
4. Click **Create app**.
5. Select the repository and branch.
6. Set the main file path:

```text
mobile_cloud_app.py
```

7. In **Advanced settings > Secrets**, enter:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "your-publishable-or-anon-key"
MOBILE_PIN = "your-mobile-pin"
```

8. Deploy the app.

Streamlit Community Cloud installs dependencies from `requirements.txt`. The cloud application does not import `openpyxl` or access local Excel, even though the full portable project includes Excel dependencies for the local MIS.

After deployment, the fixed URL will look like:

```text
https://factory-mobile.streamlit.app
```

Official Streamlit documentation:

- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management

## Option B: Render

This project includes `render.yaml` and `requirements-cloud.txt`.

1. Push the deployment files to GitHub.
2. In Render, choose **New > Web Service**.
3. Connect the repository.
4. Use:

```text
Build command:
pip install -r requirements-cloud.txt
```

```text
Start command:
streamlit run mobile_cloud_app.py --server.port $PORT --server.address 0.0.0.0
```

5. Add environment variables:

```text
SUPABASE_URL
SUPABASE_ANON_KEY
MOBILE_PIN
```

6. Do not add `SUPABASE_SERVICE_ROLE_KEY`.
7. Deploy.

Render provides `PORT`. If another platform does not support `$PORT`, set a fixed port such as:

```text
streamlit run mobile_cloud_app.py --server.port 8502 --server.address 0.0.0.0
```

Render web services must bind to `0.0.0.0` and should use the platform `PORT` environment variable.

Official Render documentation:

- https://render.com/docs/web-services

## Fixed Mobile URLs

Assume the deployed URL is:

```text
https://factory-mobile.example.com
```

Machine status:

```text
https://factory-mobile.example.com/?page=machine_status
```

Stock-In request:

```text
https://factory-mobile.example.com/?page=stock_in
```

Machine-specific status:

```text
https://factory-mobile.example.com/?page=machine_status&machine_id=800
```

## Local Factory Workflow

Publish the latest Excel snapshot:

```text
publish_supabase_snapshot.bat
```

Or:

```powershell
python sync_supabase_requests.py --publish-only
```

Process pending cloud Stock-In requests:

```text
sync_stock_in_requests.bat
```

Or:

```powershell
python sync_supabase_requests.py
```

When the local computer is off:

- the cloud Machine Status page still shows the last Supabase snapshot
- Stock-In requests can still be submitted as pending
- local Excel is updated after the factory computer starts and runs the sync script

## Generate Production QR Codes

After deployment, set the fixed cloud URL in the local `.env`:

```text
MOBILE_BASE_URL=https://factory-mobile.example.com
```

Then run:

```powershell
python generate_mobile_qr.py
```

Or use the full MIS Admin QR Generator and enter the same value under:

```text
Production Mobile Cloud URL
```

Do not use a temporary `trycloudflare.com` address for production QR codes.

## Cloudflare Tunnel

Cloudflare Tunnel is deprecated as the primary deployment path.

It may still be used for temporary local testing, but production QR codes should point to the fixed cloud deployment URL.
