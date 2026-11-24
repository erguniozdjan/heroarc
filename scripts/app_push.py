"""Build the app snapshot from the sheet and push it to Cloudflare KV."""
import json, datetime as dt, urllib.request, urllib.parse
from config import env, now, STORAGE
import google_auth

def serial(v): return (dt.date(1899, 12, 30) + dt.timedelta(days=int(v))).isoformat()

def build(read=None, fmt_read=None):
    """read(range)->rows is injectable so this can be tested without Google."""
    ts = U = None
    if read is None and STORAGE == 'notion':
        import notion_store as NS
        NS.fresh(); read = NS.make_read()
        if fmt_read is None: fmt_read = read
    if read is None:
        S = env('SHEET_ID', required=True); ts = google_auth.token()
        U = f'https://sheets.googleapis.com/v4/spreadsheets/{S}/values/'
        read = lambda rng: google_auth.api('GET', U + urllib.parse.quote(rng) + '?valueRenderOption=UNFORMATTED_VALUE', ts).get('values', [])
    nw = now(); today = nw.date().isoformat()
    if fmt_read is None:
        fmt_read = lambda rng: google_auth.api('GET', U + urllib.parse.quote(rng) + '?valueRenderOption=FORMATTED_VALUE', ts).get('values', [])
    _fmt = fmt_read
    n = lambda x: x if isinstance(x, (int, float)) and not isinstance(x, bool) else None
    mins = lambda x: round(x * 1440) if isinstance(x, (int, float)) else None
    oura = {}
    for r in read('Oura!A2:U400'):
        if r and isinstance(r[0], (int, float)): oura[serial(r[0])] = (list(r) + [''] * 21)[:21]
    wt = {}
    for r in read("'Weight Log'!A2:B400"):
        if len(r) > 1 and isinstance(r[0], (int, float)) and isinstance(r[1], (int, float)): wt[serial(r[0])] = r[1]
    cfg = [(r[0] if r else None) for r in read('Settings!B1:B4')]
    cfg = (cfg + [None] * 4)[:4]
    kcal_g, prot_g, steps_g, act_g = (cfg[0] or 2200), (cfg[1] or 150), (cfg[2] or 10000), (cfg[3] or 500)
    nut = {}
    for r in read("'Nutrition Log'!A2:H1000"):
        if r and isinstance(r[0], (int, float)):
            d = serial(r[0]); a = nut.setdefault(d, [0, 0, 0, 0]); r = (list(r) + [0] * 8)[:8]
            for k, i in enumerate((4, 5, 6, 7)): a[k] += r[i] if isinstance(r[i], (int, float)) else 0
    days = sorted(oura)
    lastfull = next((d for d in reversed(days) if n(oura[d][1]) is not None or n(oura[d][2]) is not None), None)
    o = oura.get(today); L = oura.get(lastfull, [''] * 21)
    lw = sorted(wt)[-1] if wt else None
    trend = []
    for i in range(13, -1, -1):
        d = (nw.date() - dt.timedelta(days=i)).isoformat(); r = oura.get(d, [''] * 21)
        trend.append({'d': d, 'sleep': n(r[1]), 'readiness': n(r[2]), 'weight': wt.get(d)})
    hist = {}
    for i in range(90):
        d = (nw.date() - dt.timedelta(days=i)).isoformat(); r = oura.get(d, [''] * 21); nn = nut.get(d)
        if any(n(r[j]) is not None for j in (1, 2, 13, 14, 15)) or (isinstance(r[20], str) and r[20]) or d in wt or nn:
            hist[d] = {'sleep': n(r[1]), 'readiness': n(r[2]), 'sleepHours': n(r[4]), 'hrv': n(r[9]), 'rhr': n(r[10]), 'bed': mins(r[16]), 'wake': mins(r[17]),
                'stressMin': n(r[18]), 'recoverMin': n(r[19]), 'stressSummary': (r[20] if isinstance(r[20], str) and r[20] else None),
                'steps': n(r[13]), 'activeKcal': n(r[14]), 'totalKcal': n(r[15]),
                'weight': wt.get(d), 'kcalIn': round(nn[0]) if nn else None, 'protein': round(nn[1]) if nn else None}
    tn = nut.get(today, [0, 0, 0, 0])
    # Training (plan from the Plan tab, history from Training Log) and Habits. A blank tab gives an empty block: the cards show
    # an "add your first" prompt and the editors in the app create the rows.
    def _g(rng, mode='UNFORMATTED_VALUE'):
        return read(rng) if mode == 'UNFORMATTED_VALUE' else _fmt(rng)
    training = habits = mood = None
    try:
        import training as _T
        training = _T.snapshot_section(_g)
    except Exception as e:
        print('training block skipped:', type(e).__name__, str(e)[:120])
    try:
        import habits as _H
        habits = _H.snapshot_section(_g, today=nw.date())
    except Exception as e:
        print('habits block skipped:', type(e).__name__, str(e)[:120])
    try:
        import mood as _M
        mood = _M.snapshot_section(_g, today=nw.date())
    except Exception as e:
        print('mood block skipped:', type(e).__name__, str(e)[:120])
    try:
        gs = read('Settings!B7:B7'); goals_set = bool(gs and gs[0] and str(gs[0][0]).strip() == 'set')
    except Exception:
        goals_set = False
    return {'sample': False, 'training': training, 'habits': habits, 'mood': mood, 'days': hist,
      'goals': {'steps': steps_g, 'activeKcal': act_g, 'kcal': kcal_g, 'protein': round(prot_g), 'goalsSet': goals_set}, 'date': today,
      'updated': nw.strftime('%-I:%M %p ') + (nw.tzname() or ''), 'ouraDay': lastfull,
      'today': {'steps': (n(o[13]) or 0) if o else 0, 'stepsGoal': steps_g, 'activeKcal': (n(o[14]) or 0) if o else 0,
        'totalKcal': (n(o[15]) if o else None), 'activeGoal': act_g,
        'kcalIn': round(tn[0]), 'kcalTarget': kcal_g, 'protein': round(tn[1]), 'proteinTarget': round(prot_g),
        'readiness': n(L[2]), 'sleep': n(L[1]), 'sleepHours': n(L[4]), 'hrv': n(L[9]), 'rhr': n(L[10]), 'bed': mins(L[16]), 'wake': mins(L[17]),
        'weight': wt.get(lw)},
      'trend': trend}

def push(data):
    acct, tok = env('CLOUDFLARE_ACCOUNT_ID', required=True), env('CLOUDFLARE_API_TOKEN', required=True)
    H = {'Authorization': 'Bearer ' + tok}
    base = f'https://api.cloudflare.com/client/v4/accounts/{acct}/storage/kv/namespaces'
    ns = json.load(urllib.request.urlopen(urllib.request.Request(base, headers=H)))['result']
    nid = next(x['id'] for x in ns if x['title'] == 'health-data')
    r = urllib.request.Request(f'{base}/{nid}/values/data', json.dumps(data).encode(), {**H, 'Content-Type': 'text/plain'}, method='PUT')
    return json.load(urllib.request.urlopen(r)).get('success')

def drain_and_push():
    """Move edits made in the app (training taps, habit taps and edits, weight, goals, plan) from the small KV queue into the
    sheet, rebuild the snapshot, push it, and only then drop what was drained. Event ids make a re-run harmless."""
    if STORAGE == 'notion': return _drain_notion()
    import training as T, habits as HB, mood as MD
    from kvstore import kv
    S = env('SHEET_ID', required=True); ts = google_auth.token()
    U = f'https://sheets.googleapis.com/v4/spreadsheets/{S}/values/'
    q = lambda rng: urllib.parse.quote(rng)
    api = google_auth.api
    def append(tab, rows):
        r = api('POST', U + q(f"'{tab}'!A1") + ':append?valueInputOption=RAW&insertDataOption=INSERT_ROWS', ts, {'values': rows})
        if 'error' in r: raise RuntimeError(str(r)[:160])
    done = {}
    try:   # training taps
        if T.read_queue(kv):
            have = T.known_ids(api('GET', U + q("'Training Log'!A2:J3000") + '?valueRenderOption=UNFORMATTED_VALUE', ts).get('values', []))
            done['train'] = T.drain_begin(lambda rows: append('Training Log', rows), have, kv)
    except Exception as e: print('training drain failed:', type(e).__name__, str(e)[:120])
    try:   # habit list edit, new ids, habit taps
        def write_cfg(rows):
            r = api('PUT', U + q(f"'Habits'!A2:C{len(rows)+1}") + '?valueInputOption=RAW', ts, {'values': rows})
            if 'error' in r: raise RuntimeError(str(r)[:160])
            api('POST', U + q(f"'Habits'!A{len(rows)+2}:C60") + ':clear', ts, {})
        done['cfg'] = HB.apply_config(write_cfg, kv)
        cfg = api('GET', U + q("'Habits'!A2:C40") + '?valueRenderOption=FORMATTED_VALUE', ts).get('values', [])
        for rown, newid in HB.plan_ids(cfg):
            api('PUT', U + q(f"'Habits'!B{rown}") + '?valueInputOption=RAW', ts, {'values': [[newid]]})
        if HB.read_queue(kv):
            hhave = HB.known_ids(api('GET', U + q("'Habit Log'!A2:E20000") + '?valueRenderOption=UNFORMATTED_VALUE', ts).get('values', []))
            done['hab'] = HB.drain_begin(lambda rows: append('Habit Log', rows), hhave, kv)
    except Exception as e: print('habit drain failed:', type(e).__name__, str(e)[:120])
    try:   # mood taps: append-only to the Mood Log tab
        if MD.read_queue(kv):
            mhave = MD.known_ids(api('GET', U + q("'Mood Log'!A2:F20000") + '?valueRenderOption=UNFORMATTED_VALUE', ts).get('values', []))
            done['mood'] = MD.drain_begin(lambda rows: append('Mood Log', rows), mhave, kv)
    except Exception as e: print('mood drain failed:', type(e).__name__, str(e)[:120])
    try:   # goals chosen in the app: written to Settings (what the app and the Today box read)
        gp = json.loads(kv('GET', 'goals_pending') or 'null')
        if gp and isinstance(gp, dict) and gp.get('id'):
            r = api('PUT', U + q('Settings!B1:B2') + '?valueInputOption=RAW', ts, {'values': [[gp['kcal']], [gp['protein']]]})
            if 'error' in r: raise RuntimeError(str(r)[:160])
            api('PUT', U + q('Settings!B7') + '?valueInputOption=RAW', ts, {'values': [['set']]})
            done['goals'] = gp['id']
    except Exception as e: print('goals drain failed:', type(e).__name__, str(e)[:120])
    try:   # weights entered in the app: one row per date, same formulas as log_weight.py
        wp = json.loads(kv('GET', 'weight_pending') or '[]')
        if wp:
            v = api('GET', U + q("'Weight Log'!A2:E2000") + '?valueRenderOption=UNFORMATTED_VALUE', ts).get('values', [])
            byd = {int(r[0]): i + 2 for i, r in enumerate(v) if r and isinstance(r[0], (int, float))}
            seen = {r[4][4:] for r in v if len(r) > 4 and isinstance(r[4], str) and r[4].startswith('app:')}
            avg = lambda r: f'=ROUND(AVERAGEIFS($B$2:$B,$A$2:$A,">"&A{r}-7,$A$2:$A,"<="&A{r}),1)'
            chg = lambda r: f'=IF(A{r}-A{r-1}=1,B{r}-B{r-1},"")' if r > 2 else ''
            for x in sorted([x for x in wp if x.get('id') and x['id'] not in seen], key=lambda x: x['d']):
                ser = (dt.date.fromisoformat(x['d']) - dt.date(1899, 12, 30)).days
                if ser in byd:
                    r0 = byd[ser]; api('PUT', U + q(f"'Weight Log'!B{r0}") + '?valueInputOption=USER_ENTERED', ts, {'values': [[x['w']]]})
                    api('PUT', U + q(f"'Weight Log'!E{r0}") + '?valueInputOption=USER_ENTERED', ts, {'values': [['app:' + x['id']]]})
                else:
                    r0 = max(byd.values(), default=1) + 1; byd[ser] = r0
                    rr = api('PUT', U + q(f"'Weight Log'!A{r0}:E{r0}") + '?valueInputOption=USER_ENTERED', ts, {'values': [[x['d'], x['w'], avg(r0), chg(r0), 'app:' + x['id']]]})
                    if 'error' in rr: raise RuntimeError(str(rr)[:160])
            done['weight'] = [x['id'] for x in wp if x.get('id')]
    except Exception as e: print('weight drain failed:', type(e).__name__, str(e)[:120])
    try:   # workout plan edited in the app: replaces the Plan tab (history is untouched)
        pp = json.loads(kv('GET', 'plan_pending') or 'null')
        if pp and T.valid_plan(pp):
            rows = T.plan_rows(pp)
            api('POST', U + q("'Plan'!A2:E300") + ':clear', ts, {})
            r = api('PUT', U + q(f"'Plan'!A2:E{len(rows)+1}") + '?valueInputOption=RAW', ts, {'values': rows})
            if 'error' in r: raise RuntimeError(str(r)[:160])
            done['plan'] = pp['id']
    except Exception as e: print('plan drain failed:', type(e).__name__, str(e)[:120])
    ok = safe_push()
    if not ok: return ok
    def _clean(label, fn):
        try: fn()
        except Exception as e: print(label, 'queue cleanup failed:', type(e).__name__)
    if done.get('train'): _clean('training', lambda: T.drain_end(done['train'], kv))
    if done.get('mood'): _clean('mood', lambda: MD.drain_end(done['mood'], kv))
    if done.get('hab'): _clean('habit', lambda: HB.drain_end(done['hab'], kv))
    if done.get('cfg'): _clean('habit config', lambda: HB.finish_config(done['cfg'], kv))
    if done.get('goals'): _clean('goals', lambda: (json.loads(kv('GET', 'goals_pending') or 'null') or {}).get('id') == done['goals'] and kv('PUT', 'goals_pending', 'null'))
    if done.get('weight'): _clean('weight', lambda: kv('PUT', 'weight_pending', json.dumps([x for x in json.loads(kv('GET', 'weight_pending') or '[]') if x.get('id') not in set(done['weight'])])))
    if done.get('plan'): _clean('plan', lambda: (json.loads(kv('GET', 'plan_pending') or 'null') or {}).get('id') == done['plan'] and kv('PUT', 'plan_pending', 'null'))
    return ok

def _drain_notion():
    """Same queue as the sheet version, written to Notion instead. A tap is only removed from the queue after the snapshot containing it is pushed;
    if a Notion write fails the tap stays queued and is retried on the next run (event ids make that harmless)."""
    import training as T, habits as HB, mood as MD, notion_store as NS
    from kvstore import kv
    done = {}
    def step(label, fn):
        try: fn()
        except Exception as e: print(label, 'drain failed:', type(e).__name__, str(e)[:140])
    def train():
        if T.read_queue(kv):
            have = {NS.rt(p, 'Event id').split('|')[0] for p in NS.query('Training')}
            done['train'] = T.drain_begin(lambda rows: NS.add_training_rows(rows), have, kv)
    def habits():
        done['cfg'] = HB.apply_config(lambda rows: NS.write_habit_list(rows), kv)
        if HB.read_queue(kv):
            have = {NS.rt(p, 'Event id') for p in NS.query('Habit Log')}
            done['hab'] = HB.drain_begin(lambda rows: NS.add_habit_rows(rows), have, kv)
    def mood():
        if MD.read_queue(kv):
            have = {NS.rt(p, 'Event id') for p in NS.query('Mood Log')}
            done['mood'] = MD.drain_begin(lambda rows: NS.add_mood_rows(rows), have, kv)
    def goals():
        gp = json.loads(kv('GET', 'goals_pending') or 'null')
        if gp and isinstance(gp, dict) and gp.get('id'): NS.set_goals(gp['kcal'], gp['protein']); done['goals'] = gp['id']
    def weight():
        wp = json.loads(kv('GET', 'weight_pending') or '[]')
        if wp:
            for x in sorted([x for x in wp if x.get('id')], key=lambda x: x['d']): NS.set_weight(x['d'], round(float(x['w']), 1), 'app:' + x['id'])
            done['weight'] = [x['id'] for x in wp if x.get('id')]
    def plan():
        pp = json.loads(kv('GET', 'plan_pending') or 'null')
        if pp and T.valid_plan(pp): NS.write_plan(T.plan_rows(pp), pp['id'], now().strftime('%Y-%m-%d %H:%M:%S')); done['plan'] = pp['id']
    for label, fn in (('training', train), ('habit', habits), ('mood', mood), ('goals', goals), ('weight', weight), ('plan', plan)): step(label, fn)
    ok = safe_push()
    if not ok: return ok
    def _clean(label, fn):
        try: fn()
        except Exception as e: print(label, 'queue cleanup failed:', type(e).__name__)
    if done.get('train'): _clean('training', lambda: T.drain_end(done['train'], kv))
    if done.get('mood'): _clean('mood', lambda: MD.drain_end(done['mood'], kv))
    if done.get('hab'): _clean('habit', lambda: HB.drain_end(done['hab'], kv))
    if done.get('cfg'): _clean('habit config', lambda: HB.finish_config(done['cfg'], kv))
    if done.get('goals'): _clean('goals', lambda: (json.loads(kv('GET', 'goals_pending') or 'null') or {}).get('id') == done['goals'] and kv('PUT', 'goals_pending', 'null'))
    if done.get('weight'): _clean('weight', lambda: kv('PUT', 'weight_pending', json.dumps([x for x in json.loads(kv('GET', 'weight_pending') or '[]') if x.get('id') not in set(done['weight'])])))
    if done.get('plan'): _clean('plan', lambda: (json.loads(kv('GET', 'plan_pending') or 'null') or {}).get('id') == done['plan'] and kv('PUT', 'plan_pending', 'null'))
    return ok

def safe_push(data=None):
    d = data or build(); g = d.get('goals', {})
    if not (800 < g.get('kcal', 0) < 8000 and 20 < g.get('protein', 0) < 500):
        raise RuntimeError(f'goals look wrong, not pushing: {g}')
    return push(d)

if __name__ == '__main__':
    d = build(); print(json.dumps(d)[:600]); print('pushed', safe_push(d))
