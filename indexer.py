from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from web3 import Web3
from web3._utils.events import get_event_data
from web3.providers.rpc import HTTPProvider

ROOT = Path(__file__).resolve().parent
DB = ROOT / "hoodwatch.db"
SCHEMA = ROOT / "schema.sql"
CONFIG = ROOT / "config.toml"

FACTORY_ABI = [
    {"anonymous": False, "inputs": [
        {"indexed": True, "internalType": "uint256", "name": "launchId", "type": "uint256"},
        {"indexed": True, "internalType": "address", "name": "token", "type": "address"},
        {"indexed": True, "internalType": "address", "name": "curve", "type": "address"},
        {"indexed": False, "internalType": "address", "name": "creator", "type": "address"},
        {"indexed": False, "internalType": "address", "name": "creatorFeeRecipient", "type": "address"},
        {"indexed": False, "internalType": "address", "name": "creatorVault", "type": "address"},
        {"indexed": False, "internalType": "uint256", "name": "initialBuy", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "initialTokensBought", "type": "uint256"},
        {"indexed": False, "internalType": "uint16", "name": "metadataSchemaVersion", "type": "uint16"},
        {"indexed": False, "internalType": "bytes32", "name": "metadataDigest", "type": "bytes32"},
        {"indexed": False, "internalType": "string", "name": "metadataURI", "type": "string"},
    ], "name": "TokenLaunched", "type": "event"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "internalType": "uint256", "name": "launchId", "type": "uint256"},
        {"indexed": True, "internalType": "address", "name": "token", "type": "address"},
        {"indexed": True, "internalType": "address", "name": "curve", "type": "address"},
        {"indexed": False, "internalType": "address", "name": "creator", "type": "address"},
        {"indexed": False, "internalType": "address", "name": "creatorFeeRecipient", "type": "address"},
        {"indexed": False, "internalType": "address", "name": "creatorVault", "type": "address"},
        {"indexed": False, "internalType": "address", "name": "quoteCurrency", "type": "address"},
        {"indexed": False, "internalType": "uint256", "name": "initialBuy", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "initialTokensBought", "type": "uint256"},
        {"indexed": False, "internalType": "uint16", "name": "metadataSchemaVersion", "type": "uint16"},
        {"indexed": False, "internalType": "bytes32", "name": "metadataDigest", "type": "bytes32"},
        {"indexed": False, "internalType": "string", "name": "metadataURI", "type": "string"},
    ], "name": "TokenLaunchedQuoted", "type": "event"},
]
CURVE_ABI = [
    {"anonymous": False, "inputs": [
        {"indexed": True, "internalType": "address", "name": "buyer", "type": "address"},
        {"indexed": True, "internalType": "address", "name": "recipient", "type": "address"},
        {"indexed": False, "internalType": "uint256", "name": "grossEthUsed", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "curveQuote", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "tokenAmount", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "creatorFee", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "protocolFee", "type": "uint256"},
    ], "name": "Bought", "type": "event"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "internalType": "address", "name": "seller", "type": "address"},
        {"indexed": False, "internalType": "uint256", "name": "tokenAmount", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "grossCurveQuote", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "ethReceived", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "creatorFee", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "protocolFee", "type": "uint256"},
    ], "name": "Sold", "type": "event"},
    {"anonymous": False, "inputs": [
        {"indexed": False, "internalType": "uint256", "name": "netEthReserve", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
    ], "name": "CurveCompleted", "type": "event"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "internalType": "bytes32", "name": "poolId", "type": "bytes32"},
        {"indexed": False, "internalType": "uint256", "name": "ethAmount", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "tokenAmount", "type": "uint256"},
    ], "name": "Graduated", "type": "event"},
]

EVENTS = {e["name"]: e for e in FACTORY_ABI + CURVE_ABI}


def load_config() -> dict[str, Any]:
    import tomllib
    with CONFIG.open("rb") as f:
        return tomllib.load(f)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_connect(path: Path = DB) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA.read_text())
    return c


def hexify(x: Any) -> str:
    return Web3.to_hex(x) if isinstance(x, (bytes, bytearray)) else str(x)


@dataclass
class RunStats:
    blocks: int = 0
    launches: int = 0
    buys: int = 0
    sells: int = 0
    wallets: int = 0
    errors: int = 0


class ReadOnlyIndexer:
    def __init__(self, cfg: dict[str, Any], conn: sqlite3.Connection):
        self.cfg = cfg
        self.conn = conn
        self.w3 = Web3(HTTPProvider(cfg["chain"]["rpc"], request_kwargs={"timeout": 30}))
        self.chain_id = int(cfg["chain"]["chain_id"])
        self.factories = {v["address"].lower(): v for v in cfg["factories"].values()}
        self.factory_addresses = list(self.factories)
        self.factory_topics = [self._topic(EVENTS["TokenLaunched"]), self._topic(EVENTS["TokenLaunchedQuoted"])]
        self.curve_topics = [self._topic(EVENTS[n]) for n in ("Bought", "Sold", "CurveCompleted", "Graduated")]
        self.stats = RunStats()
        self.block_timestamps: dict[int, int] = {}

    def _topic(self, abi: dict[str, Any]) -> str:
        return Web3.keccak(text=self._signature(abi)).hex()

    @staticmethod
    def _signature(abi: dict[str, Any]) -> str:
        types = ",".join(i["type"] for i in abi["inputs"])
        return f'{abi["name"]}({types})'

    def rpc_logs(self, from_block: int, to_block: int, addresses: list[str] | None = None, topics: list[str] | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"fromBlock": from_block, "toBlock": to_block}
        if addresses:
            params["address"] = addresses
        if topics:
            params["topics"] = [topics]
        delay = float(self.cfg["chain"]["retry_base_seconds"])
        retries = int(self.cfg["chain"]["max_retries"])
        for attempt in range(retries + 1):
            try:
                return self.w3.eth.get_logs(params)
            except Exception as exc:
                if attempt >= retries:
                    raise
                time.sleep(delay * (2 ** attempt))
                logging.warning("getLogs retry %s/%s: %s", attempt + 1, retries, exc)
        return []

    def timestamp(self, block: int) -> int:
        if block not in self.block_timestamps:
            self.block_timestamps[block] = int(self.w3.eth.get_block(block)["timestamp"])
        return self.block_timestamps[block]

    def decode(self, abi: dict[str, Any], log: dict[str, Any]) -> dict[str, Any]:
        return dict(get_event_data(self.w3.codec, abi, log)["args"])

    def upsert_raw(self, log: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO raw_logs VALUES (?,?,?,?,?,?,?,?)",
            (self.chain_id, hexify(log["transactionHash"]).lower(), int(log["logIndex"]),
             log["address"].lower(), int(log["blockNumber"]), log["topics"][0].hex() if isinstance(log["topics"][0], bytes) else str(log["topics"][0]),
             hexify(log["data"]), json.dumps([hexify(t) for t in log["topics"]])),
        )

    def scan(self, start: int, end: int) -> None:
        chunk = int(self.cfg["chain"]["chunk_blocks"])
        self.stats.blocks = max(0, end - start + 1)
        # Stage 1: factories only. This is the authoritative curve address map.
        for a in range(start, end + 1, chunk):
            b = min(end, a + chunk - 1)
            logs = self.rpc_logs(a, b, self.factory_addresses, self.factory_topics)
            for log in logs:
                self.upsert_raw(log)
                topic = log["topics"][0].hex() if isinstance(log["topics"][0], bytes) else str(log["topics"][0])
                abi = next((x for x in FACTORY_ABI if self._topic(x).lower() == topic.lower()), None)
                if not abi:
                    continue
                args = self.decode(abi, log)
                gen = self.factories[log["address"].lower()]
                launch_key = f'{gen["generation"]}:{int(args["launchId"])}'
                target = gen.get("graduation_target_wei") or None
                ts = self.timestamp(int(log["blockNumber"]))
                self.conn.execute(
                    """INSERT OR IGNORE INTO launches
                    (id,generation,factory,launch_id,token,curve,creator,creator_fee_recipient,creator_vault,
                     quote_currency,block,tx,log_index,timestamp,graduation_target_wei,initial_buy_wei,initial_tokens_bought)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (launch_key, gen["generation"], log["address"].lower(), str(int(args["launchId"])),
                     args["token"].lower(), args["curve"].lower(), args["creator"].lower(), args["creatorFeeRecipient"].lower(),
                     args["creatorVault"].lower(), args.get("quoteCurrency", None) and args["quoteCurrency"].lower(),
                     int(log["blockNumber"]), hexify(log["transactionHash"]).lower(), int(log["logIndex"]), ts, target,
                     str(args.get("initialBuy", 0)), str(args.get("initialTokensBought", 0)))
                )
                self.stats.launches += 1
            self.conn.commit()
            self._set_cursor("launch_scan", b)

        curves = {r["curve"].lower(): r["id"] for r in self.conn.execute("SELECT id,curve FROM launches")}
        if not curves:
            return
        # Stage 2: topic-only curve scan, then strict curve-address attribution.
        for a in range(start, end + 1, chunk):
            b = min(end, a + chunk - 1)
            logs = self.rpc_logs(a, b, None, self.curve_topics)
            for log in logs:
                if log["address"].lower() not in curves:
                    continue
                self.upsert_raw(log)
                topic = log["topics"][0].hex() if isinstance(log["topics"][0], bytes) else str(log["topics"][0])
                abi = next((x for x in CURVE_ABI if self._topic(x).lower() == topic.lower()), None)
                if not abi:
                    continue
                args = self.decode(abi, log)
                launch_id = curves[log["address"].lower()]
                launch = self.conn.execute("SELECT * FROM launches WHERE id=?", (launch_id,)).fetchone()
                if not launch:
                    continue
                block = int(log["blockNumber"]); ts = self.timestamp(block); tx = hexify(log["transactionHash"]).lower(); li = int(log["logIndex"])
                if abi["name"] == "Bought":
                    self._insert_buy(launch, args, block, ts, tx, li)
                    self.stats.buys += 1
                elif abi["name"] == "Sold":
                    self._insert_sell(launch, args, block, ts, tx, li)
                    self.stats.sells += 1
                elif abi["name"] == "Graduated":
                    self.conn.execute("UPDATE launches SET graduated=1,graduation_block=?,graduation_tx=? WHERE id=?", (block, tx, launch_id))
            self.conn.commit()
            self._set_cursor("trade_scan", b)

        self.stats.wallets = int(self.conn.execute("SELECT COUNT(DISTINCT wallet) FROM trades").fetchone()[0])

    def _insert_buy(self, launch: sqlite3.Row, a: dict[str, Any], block: int, ts: int, tx: str, li: int) -> None:
        # wallet is the recipient because the position belongs to recipient.
        self.conn.execute(
            """INSERT OR IGNORE INTO trades
            (launch_id,token,curve,wallet,role,side,buyer,recipient,token_amount,quote_amount,gross_amount,block,tx,timestamp,log_index)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (launch["id"], launch["token"], launch["curve"], a["recipient"].lower(), "recipient", "buy",
             a["buyer"].lower(), a["recipient"].lower(), str(a["tokenAmount"]), str(a["curveQuote"]), str(a["grossEthUsed"]),
             block, tx, ts, li))
        # If buyer and recipient differ, retain the buyer's action as a separate row.
        if a["buyer"].lower() != a["recipient"].lower():
            self.conn.execute(
                """INSERT OR IGNORE INTO trades
                (launch_id,token,curve,wallet,role,side,buyer,recipient,token_amount,quote_amount,gross_amount,block,tx,timestamp,log_index)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (launch["id"], launch["token"], launch["curve"], a["buyer"].lower(), "buyer", "buy",
                 a["buyer"].lower(), a["recipient"].lower(), str(a["tokenAmount"]), str(a["curveQuote"]), str(a["grossEthUsed"]),
                 block, tx, ts, li))

    def _insert_sell(self, launch: sqlite3.Row, a: dict[str, Any], block: int, ts: int, tx: str, li: int) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO trades
            (launch_id,token,curve,wallet,role,side,buyer,recipient,token_amount,quote_amount,gross_amount,block,tx,timestamp,log_index)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (launch["id"], launch["token"], launch["curve"], a["seller"].lower(), "seller", "sell", None, None,
             str(a["tokenAmount"]), str(a["grossCurveQuote"]), str(a["ethReceived"]), block, tx, ts, li))

    def _set_cursor(self, generation: str, block: int) -> None:
        self.conn.execute("INSERT INTO scan_cursor(generation,last_block) VALUES (?,?) ON CONFLICT(generation) DO UPDATE SET last_block=excluded.last_block", (generation, block))


    def scan_funding(self, start: int, end: int) -> None:
        """Persist top-level native ETH transfers seen in the requested window.

        Standard eth_getLogs cannot expose native transfers. Internal traces require
        a trace-capable RPC, so v1 records direct transaction-value transfers here.
        This is intentionally conservative: missing internal transfers are never
        inferred or fabricated.
        """
        for block in range(start, end + 1):
            try:
                b = self.w3.eth.get_block(block, full_transactions=True)
            except Exception as exc:
                logging.warning("funding block %s unavailable: %s", block, exc)
                continue
            for tx in b["transactions"]:
                value = int(tx.get("value", 0))
                to = tx.get("to")
                sender = tx.get("from")
                if value <= 0 or not to or not sender:
                    continue
                txh = hexify(tx["hash"]).lower()
                self.conn.execute(
                    "INSERT OR IGNORE INTO funding(from_wallet,to_wallet,value_wei,block,tx,log_index) VALUES(?,?,?,?,?,?)",
                    (sender.lower(), to.lower(), str(value), block, txh, -1),
                )
            if block % 250 == 0:
                self.conn.commit()
        self.conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description="Hoodwatch read-only Vibe/Vibe testnet indexer")
    ap.add_argument("--start", type=int, help="explicit start block")
    ap.add_argument("--end", type=int, help="explicit end block")
    ap.add_argument("--blocks", type=int, help="override recent window size")
    ap.add_argument("--db", default=str(DB))
    ap.add_argument("--funding", action="store_true", help="also persist direct native ETH transfers; internal traces require a trace-capable RPC")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()
    conn = db_connect(Path(args.db))
    idx = ReadOnlyIndexer(cfg, conn)
    if idx.w3.eth.chain_id != idx.chain_id:
        raise RuntimeError(f"Wrong chain: RPC returned {idx.w3.eth.chain_id}, expected {idx.chain_id}")
    head = int(idx.w3.eth.block_number) if args.end is None else args.end
    window = args.blocks or int(cfg["chain"]["recent_blocks"])
    start = args.start if args.start is not None else max(0, head - window + 1)
    end = args.end if args.end is not None else head
    print(f"Hoodwatch read-only index: chain={idx.chain_id} blocks={start}..{end}")
    try:
        idx.scan(start, end)
        if args.funding:
            idx.scan_funding(start, end)
        print(f"blocks scanned: {idx.stats.blocks}")
        print(f"launches: {idx.stats.launches}")
        print(f"buys: {idx.stats.buys}")
        print(f"sells: {idx.stats.sells}")
        print(f"wallets: {idx.stats.wallets}")
        print(f"errors: {idx.stats.errors}")
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
