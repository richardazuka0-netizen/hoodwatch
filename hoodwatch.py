#!/usr/bin/env python3
"""Hoodwatch v0.1 - beginner-friendly local launcher.

Runs the complete read-only pipeline:
  1. index public Robinhood Chain testnet logs
  2. calculate deterministic wallet tags
  3. build evidence-backed likely-related clusters
  4. start the local dashboard

No wallet, private key, signer, or transaction submission is used.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQ = ROOT / "requirements.txt"
DB = ROOT / "hoodwatch.db"


def python_bin() -> str:
    return sys.executable


def ensure_dependencies() -> None:
    try:
        import web3  # noqa: F401
    except ImportError:
        print("Hoodwatch needs one Python package that is not installed yet.")
        print("Installing the packages listed in requirements.txt...\n")
        subprocess.check_call([python_bin(), "-m", "pip", "install", "-r", str(REQ)])


def run(module: str, *args: str) -> None:
    cmd = [python_bin(), str(ROOT / module), *args]
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Hoodwatch v0.1")
    parser.add_argument("--no-index", action="store_true", help="skip live RPC indexing and open the existing dashboard database")
    parser.add_argument("--blocks", type=int, help="override the recent block window")
    parser.add_argument("--start", type=int, help="explicit starting block for a backfill")
    parser.add_argument("--end", type=int, help="explicit ending block for a backfill")
    parser.add_argument("--host", default=os.getenv("HOODWATCH_HOST", "127.0.0.1"), help="web host")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8787")), help="web port")
    parser.add_argument("--cloud", action="store_true", help="cloud mode: bind publicly and use the platform PORT")
    args = parser.parse_args()

    ensure_dependencies()

    if args.cloud:
        args.host = "0.0.0.0"
        args.port = int(os.getenv("PORT", str(args.port)))
        # Free cloud services can be restarted or put to sleep. Each fresh start
        # therefore indexes a small recent window instead of relying on local disk persistence.
        if args.blocks is None:
            args.blocks = int(os.getenv("HOODWATCH_RECENT_BLOCKS", "5000"))

    if not args.no_index:
        index_args: list[str] = []
        if args.blocks is not None:
            index_args += ["--blocks", str(args.blocks)]
        if args.start is not None:
            index_args += ["--start", str(args.start)]
        if args.end is not None:
            index_args += ["--end", str(args.end)]
        print("\n[1/3] Reading public chain logs (read-only)...")
        run("indexer.py", *index_args)
    else:
        print("\n[1/3] Skipping live indexing (--no-index).")

    if not DB.exists():
        raise SystemExit("No hoodwatch.db exists yet. Remove --no-index and run Hoodwatch once so the database can be created.")

    print("\n[2/3] Calculating deterministic wallet tags...")
    run("score.py")
    print("\n[3/3] Building evidence-backed likely-related clusters...")
    run("cluster.py")

    print(f"\nHoodwatch is ready: http://{args.host}:{args.port}")
    print("Keep this terminal open while using the dashboard. Press Ctrl+C to stop it.\n")
    run("web.py", "--host", args.host, "--port", str(args.port))


if __name__ == "__main__":
    main()
