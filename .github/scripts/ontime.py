"""On-time starter (2026-11-04). GitHub's scheduled runs start 5-70 minutes late; a run started through the API starts within about a minute.
This job (public repo = free minutes) starts hours early, reads the exact start times the private repo publishes (requests/dispatch_plan.json,
written by tools/pulse.py), waits, and at each time starts the private repo's lock check (pulse.yml, mode tick). The lock check itself decides
what is due and never runs the same check twice, so a duplicate start is harmless. Prints times only; secret FORGE_DISPATCH_TOKEN."""
import os, json, time, base64, datetime as dt, urllib.request
TOK = os.environ.get('TOKEN', ''); REPO = 'ForgeDFS/forge-os'; API = 'https://api.github.com'
HOURS = float(os.environ.get('HOURS', '5.6'))
def req(path, body=None):
    r = urllib.request.Request(API + path, data=None if body is None else json.dumps(body).encode(), method='GET' if body is None else 'POST',
                               headers={'Authorization': f'Bearer {TOK}', 'Accept': 'application/vnd.github+json', 'User-Agent': 'forge-ontime'})
    with urllib.request.urlopen(r, timeout=30) as f: b = f.read()
    return json.loads(b) if b else {}
def plan():
    d = req(f'/repos/{REPO}/contents/requests/dispatch_plan.json?ref=main')
    return json.loads(base64.b64decode(d['content']))['aims']
def ts(s): return dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
now = lambda: dt.datetime.now(dt.timezone.utc)

# ---- (2026-11-25, panel review #1) news watcher: inside 95 min before any lock (NBA: every game's tip), read Rotowire's public lineup page
# every 3 min; when who is Out / Doubtful / confirmed starting changes, start the private status-only news check (news.yml) -- at most every 6 min.
import re, hashlib
PAGES = {'nba': 'https://www.rotowire.com/basketball/nba-lineups.php', 'nfl': 'https://www.rotowire.com/football/lineups.php'}
WIN = 95; POLL = 180; GAP = 360; FP = {}; LAST = {'poll': 0.0, 'disp': 0.0}
def fingerprint(url):
    t = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36'}), timeout=25).read().decode('utf-8', 'ignore')
    keys = re.findall(r'lineup__status is-(\w+)', t)
    for li in re.findall(r'<li class="lineup__player[^"]*".*?</li>', t, re.S):
        n = re.search(r'<a title="([^"]+)"', li); p = re.search(r'is-pct-play-(\d+)', li); j = re.search(r'lineup__inj">([^<]+)<', li)
        if n: keys.append(f"{n.group(1)}|{p.group(1) if p else ''}|{j.group(1).strip() if j else ''}")
    return hashlib.sha1('\n'.join(keys).encode()).hexdigest() if keys else None
def watch(locks):
    t = now()
    if time.time() - LAST['poll'] < POLL: return
    live = {l['sport'] for l in locks if 0 < (ts(l['lock']) - t).total_seconds() / 60 <= WIN}
    if not live: return
    LAST['poll'] = time.time(); changed = []
    for sp in sorted(live):
        try: f = fingerprint(PAGES[sp])
        except Exception as e: print('watch read failed', sp, str(e)[:80]); continue
        if f and sp in FP and FP[sp] != f: changed.append(sp)
        if f: FP[sp] = f
    if changed and time.time() - LAST['disp'] >= GAP:
        sport = changed[0] if len(changed) == 1 else 'both'
        try:
            req(f'/repos/{REPO}/actions/workflows/news.yml/dispatches', dict(ref='main', inputs=dict(sport=sport))); LAST['disp'] = time.time()
            print(t.strftime('%H:%M:%SZ'), 'news changed:', changed, '-> news check started')
        except Exception as e: print('news dispatch failed:', str(e)[:120])
def plan_full():
    d = req(f'/repos/{REPO}/contents/requests/dispatch_plan.json?ref=main'); return json.loads(base64.b64decode(d['content']))
if not TOK: print('no FORGE_DISPATCH_TOKEN secret yet -- nothing to do'); raise SystemExit(0)
end = now() + dt.timedelta(hours=HOURS); fired = set()
try:   # one status line per start, so Claude can see the key works without Actions logs (times only)
    a0 = plan(); st = dict(started=now().strftime('%Y-%m-%dT%H:%MZ'), key='ok', aims=len(a0), next=min([a['at'] for a in a0 if ts(a['at']) > now()], default=None))
except Exception as e: st = dict(started=now().strftime('%Y-%m-%dT%H:%MZ'), key=f'FAILED: {e}')
print(st); open('.github/ontime_status.json', 'w').write(json.dumps(st) + '\n')
os.system('git config user.name Claude; git config user.email noreply@anthropic.com; git add .github/ontime_status.json && git commit -qm "ontime status" && git push -q origin HEAD:main || true')
while now() < end:
    try: P_ = plan_full(); aims = P_['aims']; LOCKS = P_.get('locks', [])
    except Exception as e: print('plan read failed:', e); aims = []; LOCKS = []
    try: watch(LOCKS)
    except Exception as e: print('watch failed:', str(e)[:120])
    due = sorted({a['at'] for a in aims if a['at'] not in fired and ts(a['at']) <= end})
    t = now()
    for at in due:
        lag = (t - ts(at)).total_seconds() / 60
        if 0 <= lag <= 10:   # its time has come (allow up to 10 min, e.g. right after a restart)
            try: req(f'/repos/{REPO}/actions/workflows/pulse.yml/dispatches', dict(ref='main', inputs=dict(mode='tick'))); print(t.strftime('%H:%M:%SZ'), 'started lock check for', at)
            except Exception as e: print('dispatch failed:', at, e); continue
            fired.add(at)
        elif lag > 10: fired.add(at)
    nxt = [ts(a) for a in due if a not in fired and ts(a) > now()]
    time.sleep(max(5, min(60, ((min(nxt) - now()).total_seconds() if nxt else 60))))   # 60 s max: the news watcher polls every 3 min inside it
print('window over; the next scheduled copy takes over')
