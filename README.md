# Hoodwatch v0.1

**Hoodwatch** is a local, read-only wallet-behavior dashboard for Vibe/Vibe on Robinhood Chain testnet.

It watches bonding-curve activity and gives deterministic labels such as **Sniper**, **Early nuke**, **Holder**, and **Rugger**. It also shows evidence for every label and builds **likely related** wallet clusters from explicit on-chain relationships.

> **Testnet warning:** this is a prototype. Testnet ETH is free. Hoodwatch does **not** rank wallets by profit, win rate, or volume.

## The easiest way to run it

You only need:

- Python 3.12
- an internet connection
- this Hoodwatch folder

You do **not** need a wallet, private key, seed phrase, database server, hosting account, or domain.

### Windows

1. Install Python 3.12 from the official Python website. During installation, enable **Add Python to PATH**.
2. Unzip Hoodwatch.
3. Open the Hoodwatch folder.
4. Double-click `start.bat`.
5. Leave the black terminal window open.
6. Open your browser and go to:

   **http://127.0.0.1:8787**

### macOS / Linux

Open Terminal, move into the Hoodwatch folder, then run:

```bash
python3.12 hoodwatch.py
```

If the packages are missing, Hoodwatch installs the packages from `requirements.txt` automatically.

Then open:

**http://127.0.0.1:8787**

### What happens when you start it?

Hoodwatch automatically does four things:

1. reads a recent window of public Robinhood Chain testnet logs;
2. stores launches and curve trades in a local SQLite database;
3. calculates the deterministic wallet tags;
4. starts the dashboard.

The default first run is deliberately small: `10,000` recent blocks.

## If you see an error

If the RPC is temporarily unavailable or rate-limited, don't panic. The app is read-only and will not send anything to the chain.

Try running Hoodwatch again later.

If you already have a database and only want to open the dashboard without indexing:

```bash
python3.12 hoodwatch.py --no-index
```

## Project files

You don't need to edit these to use Hoodwatch, but this is what they do:

| File | Purpose |
|---|---|
| `hoodwatch.py` | One-command launcher |
| `indexer.py` | Reads public chain logs |
| `score.py` | Calculates deterministic wallet tags |
| `cluster.py` | Builds likely-related clusters |
| `web.py` | Local dashboard |
| `schema.sql` | SQLite database structure |
| `config.toml` | RPC, factories and thresholds |
| `requirements.txt` | Python dependencies |
| `hoodwatch.db` | Your local indexed data; created automatically |
| `start.bat` | Windows double-click launcher |
| `start.sh` | macOS/Linux launcher |

## Chain configuration

- Chain ID: `46630`
- RPC: `https://rpc.testnet.chain.robinhood.com`
- Explorer: `https://explorer.testnet.chain.robinhood.com`
- Launchpad reference: `https://testnet.vibevibe.fun`
- Reference indexer: `https://github.com/itstorvian/vibevibe-testnet-indexer`

Configured factory generations:

- retired gen1: `0x4FEbC267e0C24440bcDEF72B5DBC5FE7BED091dF`, deployment block `95916239`, ~100 bps, ~0.005 ETH target
- legacy gen2: `0xB5B7A2f6c4EAFa2D73918fcA32d50e2126339eb9`, deployment block `108435450`, ~125 bps; graduation target intentionally unknown
- current gen3: `0x40f1be6faf8DAB9C143cce1a0A04c2075Fb2DF59`, deployment block `115025604`, ~125 bps, 5 ETH target

The implementation only accepts launches from configured factories and then only accepts curve events from curves created by those launches. It does not topic-match arbitrary foreign contracts.

## Exact tag rules

All thresholds are configurable in `config.toml`.

### Rugger

A wallet must be on the creator side of at least **3 launches**. Creator side means the launch's:

- creator,
- creator fee recipient, or
- creator vault.

On at least 60% of those launches, it must sell at least **70% of its initial buy** within **120 seconds**, or before the reconstructed curve quote reserve rises **25%**.

### Early nuke

The wallet must enter either:

- within the first **10 distinct buyers**, or
- while curve progress is below **20%** of that generation's graduation target.

It must then sell at least **70%** of that position after at least **3 later distinct buyers**.

Minimum: **3 qualifying tokens**.

Gen2's graduation target is unknown, so Hoodwatch does not invent one. First-10-buyer evidence still works.

### Holder

Only launches that have **not graduated** qualify.

The wallet must retain at least **80%** of its bought token amount after the curve quote reserve has risen at least **50%** from its entry reserve.

A creator-side wallet with zero creator-side sells after the same move also qualifies.

Minimum: **2 qualifying tokens**.

Hoodwatch does not call a wallet a holder from curve data after graduation.

### Sniper

The wallet buys in the **same block as TokenLaunched**.

Minimum: **5 qualifying tokens**.

## Evidence

Every emitted tag stores:

- rate;
- sample size;
- token;
- transaction;
- deterministic reason code.

Click a wallet to see the evidence behind its tags.

## Clusters

Hoodwatch can create edges from:

1. **Funding** — wallet A sent native test ETH to wallet B and B later traded. Faucet addresses are excluded before this relationship is used.
2. **Co-trade** — two wallets bought/sold the same token in the same block on at least 3 different tokens.

Clusters are always described as **likely related**. They are never described as a confirmed identity.

The default faucet denylist is empty because the public faucet address was not independently established for this prototype. Add verified faucet addresses to `config.toml` before relying on funding relationships.

Two wallets funded only by a denylisted faucet must not become a cluster because of that faucet.

## Backfilling later

Do not start with a full historical backfill.

Once the prototype is working, you can explicitly choose a block range:

```bash
python3.12 hoodwatch.py --start 115025604 --end 118000000
```

Or a recent-window size:

```bash
python3.12 hoodwatch.py --blocks 50000
```

The indexer commits each chunk before advancing its cursor, and rerunning a window does not duplicate the same log/trade identity.

## What Hoodwatch deliberately does NOT do

- No private keys.
- No seed phrases.
- No session keys.
- No transaction signing.
- No transaction submission.
- No copy-trading API.
- No automatic trade preparation.
- No testnet PnL ranking.
- No win-rate ranking.
- No volume ranking.
- No LLM scoring, ingestion, or clustering.
- No confirmed wallet identity claims.
- No scraping the Vibe/Vibe website for trades.
- No post-graduation Uniswap v4 trades.
- No calling a wallet a holder from curve data after graduation.

## Does it need a domain?

**No.** Not for v0.1.

`127.0.0.1` means the website is running on your own computer. This is the safest and simplest way to learn the product first.

Later, if you want other people to use Hoodwatch, we can deploy the same application to a cloud server and connect a domain such as `hoodwatch.xyz` (if available). That is a separate deployment step and is not required for the prototype.

## Live-run evidence

This package intentionally does not invent a wallet or transaction as an example. The build environment used to create the prototype could inspect the reference repository, but its outbound DNS/RPC access was unavailable, so a genuine live RPC run could not be completed there.

When you run Hoodwatch locally, the dashboard will populate from the public RPC. Only then should a real wallet and evidence transaction be added to product documentation.

## Deploy from Android for free

If you do not have a computer, use the included `DEPLOY_FROM_ANDROID.md` guide. Hoodwatch v0.1 is prepared for a free Render web service and receives its public URL from Render.

Free hosting is intentionally treated as a prototype environment: the service can sleep after inactivity and its local SQLite filesystem is ephemeral. A fresh service start therefore re-indexes a recent window. For durable production data, move the database to persistent Postgres and split indexing into a worker/cron process.
