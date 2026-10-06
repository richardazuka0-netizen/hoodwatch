from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB = ROOT / "hoodwatch.db"
CONFIG = ROOT / "config.toml"


def load_config():
    import tomllib
    with CONFIG.open("rb") as f: return tomllib.load(f)

def now(): return datetime.now(timezone.utc).isoformat()

def D(x): return Decimal(str(x))

def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def all_trades(c, token=None):
    if token:
        return c.execute("SELECT * FROM trades WHERE token=? ORDER BY block,log_index,id",(token,)).fetchall()
    return c.execute("SELECT * FROM trades ORDER BY token,block,log_index,id").fetchall()

def score():
    cfg=load_config(); t=cfg["tags"]; c=conn()
    c.execute("DELETE FROM wallet_tags"); c.execute("DELETE FROM tag_evidence")
    launches=c.execute("SELECT * FROM launches ORDER BY block,log_index").fetchall()
    trades_by_token={l["token"]: all_trades(c,l["token"]) for l in launches}
    results={}
    samples={}

    def add(wallet, tag, token, tx, reason):
        results.setdefault((wallet,tag), {"evidence":set(),"sample":0})["evidence"].add((token,tx,reason))

    # Per-token reserve series. The reserve used here is a deterministic reconstruction:
    # generation initial virtual ETH reserve + cumulative curve quote in - curve quote out.
    for l in launches:
        target = D(l["graduation_target_wei"]) if l["graduation_target_wei"] else None
        initial_reserve = {
            "retired": D("1764594628672298"),
            "current": D("1764594628672298575"),
        }.get(l["generation"])
        if initial_reserve is None:
            # Gen2 initial reserve was not verified by the reference indexer. Do not invent it.
            initial_reserve = None
        rows=trades_by_token[l["token"]]
        reserve=initial_reserve
        first_buyers=[]; buyer_set=set(); position={}; entry_reserve={}; first_entry={}
        for r in rows:
            if r["side"]=="buy":
                w=r["wallet"]
                if w not in buyer_set:
                    buyer_set.add(w); first_buyers.append(w)
                if w not in first_entry:
                    first_entry[w]=r
                    entry_reserve[w]=reserve
                position[w]=position.get(w,D(0))+D(r["token_amount"])
                if reserve is not None: reserve += D(r["quote_amount"])
            else:
                w=r["wallet"]
                position[w]=position.get(w,D(0))-D(r["token_amount"])
                if reserve is not None: reserve -= D(r["quote_amount"])
            # Attach deterministic state to a transient row map keyed by id.
        # second pass for rules
        if not rows: continue
        # Rugger: creator-side wallets on this launch.
        creator_side={l["creator"],l["creator_fee_recipient"],l["creator_vault"]}
        creator_rows=[r for r in rows if r["wallet"] in creator_side and r["side"]=="buy"]
        creator_buys={w: sum(D(r["token_amount"]) for r in creator_rows if r["wallet"]==w) for w in creator_side}
        creator_first={w:min((r for r in creator_rows if r["wallet"]==w),key=lambda x:(x["block"],x["log_index"]),default=None) for w in creator_side}
        for w,fb in creator_first.items():
            if not fb: continue
            samples[(w,"Rugger")]=samples.get((w,"Rugger"),0)+1
            bought=creator_buys[w]
            sold=Decimal(0); good=False; good_tx=None
            for r in rows:
                if r["wallet"]!=w or r["side"]!="sell": continue
                sold += D(r["token_amount"])
                within_time = r["timestamp"]-fb["timestamp"] <= int(t["rugger_max_seconds"])
                # Reserve test: recompute reserve at the sell block from all prior trades.
                rr=initial_reserve
                if rr is not None:
                    for x in rows:
                        if (x["block"],x["log_index"],x["id"]) > (r["block"],r["log_index"],r["id"]): break
                        rr += D(x["quote_amount"]) if x["side"]=="buy" else -D(x["quote_amount"])
                    base=initial_reserve
                    reserve_rise=(rr-base)/base if base else Decimal(0)
                    before_rise=reserve_rise <= D(t["rugger_reserve_rise"])
                else: before_rise=False
                if sold >= bought*D(t["rugger_sell_fraction"]) and (within_time or before_rise):
                    good=True; good_tx=r["tx"]; break
            if good: add(w,"Rugger",l["token"],good_tx,"RUGGER_CREATOR_SIDE_EXIT")

        # Early nuke: first 10 buyers OR progress <20%, then >=70% sell after 3 later distinct buyers.
        if target is not None or len(first_buyers)>=int(t["nuke_first_buyers"]):
            for w,entry in first_entry.items():
                reserve_at_entry=entry_reserve.get(w)
                early=(first_buyers.index(w)<int(t["nuke_first_buyers"])) if w in first_buyers else False
                if target is not None and reserve_at_entry is not None:
                    early = early or ((reserve_at_entry - initial_reserve) / target < D(t["nuke_progress"]))
                if not early: continue
                samples[(w,"Early nuke")]=samples.get((w,"Early nuke"),0)+1
                later_buyers=set(); sold=Decimal(0); ok=None
                for r in rows:
                    if r["block"] < entry["block"] or (r["block"]==entry["block"] and r["log_index"]<=entry["log_index"]): continue
                    if r["side"]=="buy" and r["wallet"]!=w: later_buyers.add(r["wallet"])
                    if r["side"]=="sell" and r["wallet"]==w:
                        if len(later_buyers)>=int(t["nuke_later_buyers"]):
                            sold += D(r["token_amount"])
                            if sold >= D(entry["token_amount"])*D(t["nuke_sell_fraction"]): ok=r["tx"]; break
                if ok: add(w,"Early nuke",l["token"],ok,"EARLY_ENTRY_THEN_70PCT_EXIT_AFTER_3_BUYERS")

        # Holder: pre-graduation only, >=80% retained and reserve +50% from entry.
        if not l["graduated"]:
            for w,entry in first_entry.items():
                bought=sum(D(r["token_amount"]) for r in rows if r["wallet"]==w and r["side"]=="buy")
                sold=sum(D(r["token_amount"]) for r in rows if r["wallet"]==w and r["side"]=="sell")
                er=entry_reserve.get(w)
                if bought<=0 or er is None: continue
                samples[(w,"Holder")]=samples.get((w,"Holder"),0)+1
                rr=er
                for r in rows:
                    if (r["block"],r["log_index"],r["id"]) <= (entry["block"],entry["log_index"],entry["id"]): continue
                    rr += D(r["quote_amount"]) if r["side"]=="buy" else -D(r["quote_amount"])
                retained=(bought-sold)/bought
                reserve_move=(rr-er)/er if er else Decimal(0)
                creator_no_dump = w in creator_side and not any(r["wallet"]==w and r["side"]=="sell" for r in rows)
                if retained>=D(t["holder_fraction"]) and (reserve_move>=D(t["holder_reserve_rise"]) or creator_no_dump and reserve_move>=D(t["holder_reserve_rise"])):
                    add(w,"Holder",l["token"],entry["tx"],"HOLDER_RETENTION_AFTER_50PCT_RESERVE_MOVE")

        # Sniper: buy in launch block. Initial buy is also a real curve buy and counts.
        for w in {r["wallet"] for r in rows if r["side"]=="buy" and r["block"]==l["block"]}:
            samples[(w,"Sniper")]=samples.get((w,"Sniper"),0)+1
            tx=next(r["tx"] for r in rows if r["wallet"]==w and r["side"]=="buy" and r["block"]==l["block"])
            add(w,"Sniper",l["token"],tx,"BUY_IN_TOKEN_LAUNCH_BLOCK")

    # Compute sample denominators from the observed window, not PnL/volume.
    for (wallet,tag),v in results.items():
        sample=samples.get((wallet,tag),0)
        minimum={"Rugger":int(t["rugger_min_launches"]),"Early nuke":int(t["nuke_min_tokens"]),"Holder":int(t["holder_min_tokens"]),"Sniper":int(t["sniper_min_tokens"])}[tag]
        if sample < minimum: continue
        rate=(len({e[0] for e in v["evidence"]})/sample)*100 if sample else 0
        c.execute("INSERT INTO wallet_tags VALUES (?,?,?,?,?)",(wallet,tag,rate,sample,now()))
        for token,tx,reason in sorted(v["evidence"]):
            c.execute("INSERT OR IGNORE INTO tag_evidence VALUES (?,?,?,?,?)",(wallet,tag,token,tx,reason))
    c.commit()
    print("tags:", c.execute("SELECT COUNT(*) FROM wallet_tags").fetchone()[0])
    for r in c.execute("SELECT * FROM wallet_tags ORDER BY wallet,tag"): print(dict(r))
    c.close()

if __name__=="__main__": score()
