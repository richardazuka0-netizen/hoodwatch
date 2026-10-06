# Deploy Hoodwatch from Android — free v0.1

You do not need a computer.

## What you need

- An Android phone
- A GitHub account
- A Render account
- This Hoodwatch folder

## 1. Create GitHub repository

Open GitHub in Chrome and create a new repository named `hoodwatch`.
Keep it private if you prefer.

## 2. Upload Hoodwatch

Open the new repository → **Add file** → **Upload files**.
Upload the files from this folder (not the ZIP itself):

- `hoodwatch.py`
- `indexer.py`
- `score.py`
- `cluster.py`
- `web.py`
- `schema.sql`
- `config.toml`
- `requirements.txt`
- `render.yaml`
- `.gitignore`
- `README.md`

Commit the upload.

## 3. Deploy on Render

Open Render and sign up/login with GitHub.

Choose **New → Web Service**, connect the `hoodwatch` repository, and choose the **Free** plan.

If Render reads `render.yaml`, it will use:

- Build: `pip install -r requirements.txt`
- Start: `python hoodwatch.py --cloud`
- Health check: `/health`

If Render asks manually, enter those exact values.

## 4. Wait for the first deploy

Render gives the service a URL ending in `onrender.com`.
Open that URL from your Android browser.

The first start indexes a recent block window, calculates tags, builds clusters, and then shows the dashboard.

## Free-tier behavior

This is deliberately a prototype deployment.

Render free web services can sleep after inactivity. Their local filesystem is also ephemeral, so SQLite data is not permanent. Hoodwatch therefore re-indexes a recent window after a fresh start instead of pretending the database is durable.

This is fine for v0.1 testing. A later production version should move the database to persistent Postgres and run indexing as a separate worker/cron process.

## Read-only guarantee

Hoodwatch never imports or asks for:

- private keys
- seed phrases
- session keys
- wallet signatures

It only reads public Robinhood Chain testnet RPC data. It never submits transactions.
