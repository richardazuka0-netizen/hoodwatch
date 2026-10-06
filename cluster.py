from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent; DB=ROOT/"hoodwatch.db"; CONFIG=ROOT/"config.toml"

def cfg():
 import tomllib
 with CONFIG.open("rb") as f:return tomllib.load(f)

def now():return datetime.now(timezone.utc).isoformat()
class UF:
 def __init__(self,x):self.p={a:a for a in x}
 def find(self,x):
  while self.p[x]!=x:self.p[x]=self.p[self.p[x]];x=self.p[x]
  return x
 def union(self,a,b):
  a,b=self.find(a),self.find(b)
  if a!=b:self.p[b]=a

def build():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; q=cfg()["clusters"]
 deny={x.lower() for x in cfg()["clusters"].get("faucet_denylist",[])}
 # Also accept top-level legacy location if present.
 deny |= {x.lower() for x in cfg().get("faucet_denylist",[])}
 wallets={r[0] for r in c.execute("SELECT DISTINCT wallet FROM trades")}
 uf=UF(wallets); edges=[]
 # Funding edges are optional in v1 because native internal transfers require traces.
 if deny:
  for r in c.execute("SELECT from_wallet,to_wallet FROM funding"):
   a,b=r[0].lower(),r[1].lower()
   if a in deny or b in deny: continue
   if a in uf.p and b in uf.p: uf.union(a,b); edges.append((a,b,"shared funder",1))
 # Co-trade: same token, same block, one buy and one sell by distinct wallets.
 min_tokens=int(q["co_trade_min_tokens"])
 pair_tokens={}
 for row in c.execute("SELECT token,block,wallet,side FROM trades WHERE side IN ('buy','sell') ORDER BY token,block"):
  pair_tokens.setdefault((row["token"],row["block"]),{"buy":set(),"sell":set()})[row["side"]].add(row["wallet"])
 pair_counts={}
 for (token,block),g in pair_tokens.items():
  for a in g["buy"]:
   for b in g["sell"]:
    if a==b:continue
    key=tuple(sorted((a,b))); pair_counts.setdefault(key,set()).add(token)
 for (a,b),tokens in pair_counts.items():
  if len(tokens)>=min_tokens:
   uf.union(a,b); edges.append((a,b,"same-block buy/sell",len(tokens)))
 # Build components and evidence-backed clusters only.
 groups={}
 for w in wallets:groups.setdefault(uf.find(w),[]).append(w)
 c.execute("DELETE FROM cluster_edges");c.execute("DELETE FROM cluster_members");c.execute("DELETE FROM clusters")
 for members in groups.values():
  if len(members)<2:continue
  # Only components with at least one evidence edge survive.
  es=[]
  ms=set(members)
  for e in edges:
   if e[0] in ms and e[1] in ms:es.append(e)
  if not es:continue
  cur=c.execute("INSERT INTO clusters(method,created_at) VALUES(?,?)",("funding+co-trade",now())); cid=cur.lastrowid
  for w in members:c.execute("INSERT INTO cluster_members VALUES(?,?)",(cid,w))
  for a,b,reason,weight in es:c.execute("INSERT OR IGNORE INTO cluster_edges VALUES(?,?,?,?,?)",(cid,a,b,reason,weight))
 c.commit(); print("clusters:",c.execute("SELECT COUNT(*) FROM clusters").fetchone()[0]); c.close()
if __name__=="__main__":build()
