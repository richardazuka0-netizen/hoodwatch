from __future__ import annotations
import html, sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from datetime import datetime, timezone
import os

ROOT=Path(__file__).resolve().parent; DB=ROOT/"hoodwatch.db"; CFG=ROOT/"config.toml"

def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c

def esc(x):return html.escape(str(x or ""))
def link(addr,kind="address"):return f'https://explorer.testnet.chain.robinhood.com/{kind}/{addr}'
def a(text,url):return f'<a href="{esc(url)}" target="_blank" rel="noreferrer">{esc(text)}</a>'
def css():return '''body{font-family:system-ui,sans-serif;max-width:1200px;margin:0 auto;padding:24px;background:#0b0d10;color:#e8eaed}a{color:#8ab4f8}nav a{margin-right:16px}.card{background:#151922;border:1px solid #292f3a;border-radius:12px;padding:16px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}.muted{color:#9aa4b2}.tag{display:inline-block;border:1px solid #3a4250;border-radius:999px;padding:3px 8px;margin:2px;font-size:12px}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #292f3a;text-align:left}code{word-break:break-all}.warn{border-left:4px solid #f2c94c}.danger{border-left:4px solid #eb5757}form{display:inline}button{background:#202633;color:#fff;border:1px solid #3a4250;border-radius:7px;padding:6px 10px}input,select{background:#11151d;color:#fff;border:1px solid #3a4250;padding:7px;border-radius:7px}'''

def page(title,body):return f'''<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Hoodwatch — {esc(title)}</title><style>{css()}</style></head><body><nav><a href="/">Hoodwatch</a><a href="/leaderboard">Leaderboard</a><a href="/follows">Follows</a><a href="/about">About</a></nav><h1>{esc(title)}</h1>{body}</body></html>'''

def tags(c,w):
 return ''.join(f'<span class=tag>{esc(r["tag"])} {r["rate"]:.0f}% / n={r["sample_size"]}</span>' for r in c.execute('SELECT * FROM wallet_tags WHERE wallet=? ORDER BY tag',(w,))) or '<span class=muted>untagged</span>'

def home(c):
 launches=c.execute('SELECT COUNT(*) FROM launches').fetchone()[0]; trades=c.execute('SELECT COUNT(*) FROM trades').fetchone()[0]; wallets=c.execute('SELECT COUNT(DISTINCT wallet) FROM trades').fetchone()[0]; tagged=c.execute('SELECT COUNT(DISTINCT wallet) FROM wallet_tags').fetchone()[0]
 last=c.execute('SELECT MAX(block) FROM (SELECT block FROM launches UNION ALL SELECT block FROM trades)').fetchone()[0]
 return page('Home',f'<div class=grid><div class=card><b>{launches}</b><br>launches</div><div class=card><b>{trades}</b><br>trade rows</div><div class=card><b>{wallets}</b><br>wallets</div><div class=card><b>{tagged}</b><br>tagged wallets</div></div><div class="card warn"><b>Testnet only.</b> Hoodwatch is read-only. Testnet ETH is free and no PnL/win-rate/volume ranking is shown.</div><p>Last indexed block: <code>{last or '—'}</code></p><p class=muted>Cloud v0.1 uses a recent window. Free hosting may sleep and reset local storage; a fresh wake-up re-indexes the recent window.</p>')

def leaderboard(c,params):
 tag=params.get('tag',[''])[0]; where='';args=[]
 if tag:where='WHERE wt.tag=?';args=[tag]
 rows=c.execute(f'''SELECT wt.wallet,GROUP_CONCAT(wt.tag,'|') tags,GROUP_CONCAT(printf('%.0f%%/%d',wt.rate,wt.sample_size),'|') metrics FROM wallet_tags wt {where} GROUP BY wt.wallet ORDER BY wt.wallet''',args).fetchall()
 opts=''.join(f'<option {"selected" if r[0]==tag else ""}>{esc(r[0])}</option>' for r in c.execute('SELECT DISTINCT tag FROM wallet_tags ORDER BY tag'))
 body=f'<form><select name=tag><option value="">all tags</option>{opts}</select> <button>Filter</button></form><div class=card><table><tr><th>Wallet</th><th>Tags</th><th>Rate/sample</th></tr>'+''.join(f'<tr><td>{a(esc(r["wallet"]),"/wallet/"+r["wallet"])}</td><td>{esc(r["tags"]).replace("|"," ")}</td><td>{esc(r["metrics"]).replace("|"," · ")}</td></tr>' for r in rows)+'</table></div>' if rows else '<div class=card>Empty state: no wallet has met a configured tag threshold in this indexed window yet.</div>'
 return page('Leaderboard',body)

def wallet(c,w):
 r=c.execute('SELECT * FROM trades WHERE wallet=? ORDER BY block DESC,log_index DESC',(w,)).fetchall(); launches=c.execute('SELECT DISTINCT l.* FROM launches l JOIN trades t ON t.launch_id=l.id WHERE t.wallet=? ORDER BY l.block DESC',(w,)).fetchall(); ev=c.execute('SELECT * FROM tag_evidence WHERE wallet=? ORDER BY tag,token',(w,)).fetchall()
 body=f'<div class=card><code>{esc(w)}</code><div>{tags(c,w)}</div></div><h2>Launches touched</h2><div class=card><table><tr><th>Generation</th><th>Token</th><th>Curve</th><th>Graduated</th></tr>'+''.join(f'<tr><td>{esc(x["generation"])}</td><td>{a(x["token"],link(x["token"],"token"))}</td><td>{a(x["curve"],link(x["curve"]))}</td><td>{"yes" if x["graduated"] else "no"}</td></tr>' for x in launches)+'</table></div><h2>Trades</h2><div class=card><table><tr><th>Side</th><th>Role</th><th>Token</th><th>Amount</th><th>Block</th><th>Tx</th></tr>'+''.join(f'<tr><td>{x["side"]}</td><td>{x["role"]}</td><td>{esc(x["token"][:10])}…</td><td>{esc(x["token_amount"])}</td><td>{x["block"]}</td><td>{a(x["tx"][:12]+"…",link(x["tx"],"tx"))}</td></tr>' for x in r)+'</table></div><h2>Tag evidence</h2><div class=card><table><tr><th>Tag</th><th>Token</th><th>Reason</th><th>Tx</th></tr>'+''.join(f'<tr><td>{esc(x["tag"])}</td><td>{a(x["token"][:12]+"…",link(x["token"],"token"))}</td><td>{esc(x["reason_code"])}</td><td>{a(x["tx"][:12]+"…",link(x["tx"],"tx"))}</td></tr>' for x in ev)+'</table></div>'
 return page('Wallet',body)

def cluster(c,cid):
 members=c.execute('SELECT wallet FROM cluster_members WHERE cluster_id=? ORDER BY wallet',(cid,)).fetchall();edges=c.execute('SELECT * FROM cluster_edges WHERE cluster_id=? ORDER BY reason,weight DESC',(cid,)).fetchall(); maxm=50
 shown=members[:maxm]
 body=f'<div class=card><b>Likely related</b> — this is a behavioral cluster, not a confirmed identity.</div><h2>Members ({len(members)})</h2><div class=card>'+(' · '.join(a(x["wallet"],'/wallet/'+x["wallet"]) for x in shown) or 'none')+(f'<p class=muted>Displayed first {maxm}; component is capped in the UI.</p>' if len(members)>maxm else '')+'</div><h2>Edges</h2><div class=card><table><tr><th>From</th><th>To</th><th>Why</th><th>Weight</th></tr>'+''.join(f'<tr><td>{a(x["from_wallet"][:12]+"…","/wallet/"+x["from_wallet"])}</td><td>{a(x["to_wallet"][:12]+"…","/wallet/"+x["to_wallet"])}</td><td>{esc(x["reason"])}</td><td>{x["weight"]}</td></tr>' for x in edges)+'</table></div>'
 return page(f'Cluster {cid}',body)

def follows(c):
 rows=c.execute('SELECT * FROM follows ORDER BY created_at DESC').fetchall();body='<div class=card><form method=post action=/follow><select name=subject_type><option>wallet</option><option>cluster</option></select><input name=subject_id placeholder="address or cluster id" required><button>Add</button></form></div>'
 body+='<div class=card><table><tr><th>Subject</th><th>Created</th><th></th></tr>'+''.join(f'<tr><td>{a(x["subject_type"]+":"+x["subject_id"],("/wallet/"+x["subject_id"]) if x["subject_type"]=="wallet" else ("/cluster/"+x["subject_id"]))}</td><td>{esc(x["created_at"])}</td><td><form method=post action=/unfollow><input type=hidden name=id value="{x["id"]}"><button>Remove</button></form></td></tr>' for x in rows)+'</table></div>'
 # Alert since last view: local only; viewing marks all follows as viewed.
 for x in rows:
  since=x['last_viewed_at'] or x['created_at']; subj=x['subject_id'] if x['subject_type']=='wallet' else None
  if subj:
   acts=c.execute('SELECT * FROM trades WHERE wallet=? AND timestamp>? ORDER BY timestamp DESC',(subj,int(datetime.fromisoformat(since.replace('Z','+00:00')).timestamp()) if 'T' in since else 0)).fetchall()
   if acts: body+=f'<h2>New activity for {esc(subj)}</h2><div class=card>'+''.join(f'<p>{x["side"]} {x["token"][:12]}… · {a("tx",link(x["tx"],"tx"))} · {a("token",link(x["token"],"token"))}</p>' for x in acts[:100])+'</div>'
 c.execute('UPDATE follows SET last_viewed_at=?',(datetime.now(timezone.utc).isoformat(),));c.commit();return page('Follows',body)

def about():
 return page('About','''<div class=card><h2>Deterministic labels</h2><ul><li><b>Rugger:</b> creator/fee-recipient/vault on ≥3 launches and ≥60% of those launches must show ≥70% initial-position exit within 120s or before +25% quote-reserve move.</li><li><b>Early nuke:</b> early entry (first 10 buyers or &lt;20% verified graduation target), ≥70% exit after ≥3 later distinct buyers, ≥3 tokens.</li><li><b>Holder:</b> non-graduated only; ≥80% of bought size retained after ≥50% quote-reserve move; ≥2 tokens.</li><li><b>Sniper:</b> buy in launch block on ≥5 tokens.</li></ul><p>Rates and sample sizes are stored per wallet/tag; evidence stores token, tx and reason code.</p></div><div class=card><h2>Clusters</h2><p>Funding and same-block co-trade edges are deterministic. Faucet addresses are excluded before funding edges are made. Components are labeled <b>likely related</b>, never confirmed identity.</p></div><div class="card warn"><h2>Excluded</h2><ul><li>Post-graduation Uniswap v4 trades.</li><li>Testnet PnL, win rate and volume ranking.</li><li>LLM scoring/clustering/ingestion.</li><li>Copy trading or transaction construction.</li><li>Identity claims.</li></ul></div><div class=card><h2>Data source</h2><p>Hoodwatch reads public chain logs only. It does not scrape the Vibe/Vibe site for trades.</p></div>''')

class H(BaseHTTPRequestHandler):
 def send(self,s):
  b=s.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  c=db();p=urlparse(self.path);path=p.path;qs=parse_qs(p.query)
  try:
   if path=='/':self.send(home(c))
   elif path=='/leaderboard':self.send(leaderboard(c,qs))
   elif path.startswith('/wallet/'):self.send(wallet(c,path.split('/',2)[2].lower()))
   elif path.startswith('/cluster/'):self.send(cluster(c,int(path.split('/',2)[2])))
   elif path=='/follows':self.send(follows(c))
   elif path=='/about':self.send(about())
   elif path=='/health':
    self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8');self.end_headers();self.wfile.write(b'ok')
   else:self.send(page('404','<div class=card>Not found.</div>'))
  finally:c.close()
 def do_POST(self):
  c=db();p=urlparse(self.path);n=int(self.headers.get('Content-Length','0'));data=parse_qs(self.rfile.read(n).decode())
  if p.path=='/follow':
   c.execute('INSERT OR IGNORE INTO follows(subject_type,subject_id,created_at,last_viewed_at) VALUES(?,?,?,?,?)'.replace('?,?,?,?,?','?,?,?,?'),(data['subject_type'][0],data['subject_id'][0].lower(),datetime.now(timezone.utc).isoformat(),None));c.commit()
  elif p.path=='/unfollow':c.execute('DELETE FROM follows WHERE id=?',(data['id'][0],));c.commit()
  self.send_response(303);self.send_header('Location','/follows');self.end_headers();c.close()

def main():
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--host',default=os.getenv('HOODWATCH_HOST','127.0.0.1'));ap.add_argument('--port',type=int,default=int(os.getenv('PORT','8787')));args=ap.parse_args()
 ThreadingHTTPServer((args.host,args.port),H).serve_forever()
if __name__=='__main__':main()
