"""Pull recent Oura data into the Oura tab (upsert by date), then push the app snapshot."""
import json, time, os, datetime as dt, urllib.request, urllib.parse
from config import env, ROOT, now, STORAGE
from google_auth import token, api
TOK = os.path.join(ROOT, 'oura', 'tokens.json')
UA = {'User-Agent': 'HeroArc/1.0'}

def access():
    t = json.load(open(TOK))
    if time.time() > t['obtained_at'] + t['expires_in'] - 86400:   # refresh a day early; refresh tokens are single-use
        d = urllib.parse.urlencode({'grant_type': 'refresh_token', 'refresh_token': t['refresh_token'],
            'client_id': env('OURA_CLIENT_ID', required=True), 'client_secret': env('OURA_CLIENT_SECRET', required=True)}).encode()
        n = json.load(urllib.request.urlopen(urllib.request.Request('https://api.ouraring.com/oauth/token', d, UA)))
        n['obtained_at'] = int(time.time()); json.dump(n, open(TOK, 'w')); os.chmod(TOK, 0o600); t = n
    return t['access_token']

def og(a, ep, s, e):
    out = []; base = f'https://api.ouraring.com/v2/usercollection/{ep}?start_date={s}&end_date={e}'; url = base
    while url:
        j = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'Authorization': 'Bearer ' + a, **UA})))
        out += j['data']; nt = j.get('next_token'); url = f'{base}&next_token={nt}' if nt else None
    return out

def tod(iso):
    if not iso: return ''
    hh, mm, ss = (int(x) for x in iso[11:19].split(':'))
    return round((hh * 3600 + mm * 60 + ss) / 86400, 6)

def sync(days=14):
    if STORAGE != 'notion':
        S = env('SHEET_ID', required=True); ts = token()
        U = f'https://sheets.googleapis.com/v4/spreadsheets/{S}'
    a = access(); today = now().date(); s = (today - dt.timedelta(days=days)).isoformat(); e = (today + dt.timedelta(days=1)).isoformat()
    ds = {x['day']: x for x in og(a, 'daily_sleep', s, e)}; rd = {x['day']: x for x in og(a, 'daily_readiness', s, e)}
    ac = {x['day']: x for x in og(a, 'daily_activity', s, e)}
    sl = {x['day']: x for x in og(a, 'sleep', s, e) if x.get('type') == 'long_sleep'}
    try: st = {x['day']: x for x in og(a, 'daily_stress', s, e)}
    except Exception: st = {}
    h = lambda v: round(v / 3600, 2) if v else ''; m = lambda v: round(v / 60) if v else ''
    new = {}
    for d in sorted(set(ds) | set(rd) | set(ac) | set(sl) | set(st)):
        x = sl.get(d, {}); sd = st.get(d, {})
        new[d] = [d, ds.get(d, {}).get('score', ''), rd.get(d, {}).get('score', ''), ac.get(d, {}).get('score', ''),
            h(x.get('total_sleep_duration')), m(x.get('deep_sleep_duration')), m(x.get('rem_sleep_duration')), m(x.get('light_sleep_duration')),
            x.get('efficiency', ''), x.get('average_hrv', ''), x.get('lowest_heart_rate', ''), x.get('average_heart_rate', ''),
            rd.get(d, {}).get('temperature_deviation', ''), ac.get(d, {}).get('steps', ''), ac.get(d, {}).get('active_calories', ''),
            ac.get(d, {}).get('total_calories', ''), tod(x.get('bedtime_start')), tod(x.get('bedtime_end')),
            (sd.get('stress_high') or 0) // 60 if sd.get('stress_high') is not None else '',
            (sd.get('recovery_high') or 0) // 60 if sd.get('recovery_high') is not None else '', sd.get('day_summary') or '']
    if not new: return 'no Oura data in range (is the ring synced in the Oura app?)'
    if STORAGE == 'notion':
        import notion_store as NS
        n_changed = NS.upsert_oura(list(new.values()))
        out = f"{len(new)} days upserted ({min(new)}..{max(new)}) to Notion, {n_changed} changed"
        try:
            import app_push; app_push.drain_and_push()
        except Exception as ex: out += f' | app push failed: {type(ex).__name__}: {ex}'
        return out
    col = api('GET', U + '/values/Oura!A:A?valueRenderOption=UNFORMATTED_VALUE', ts).get('values', [])
    rowof = {}
    for i, r in enumerate(col, 1):
        if r and isinstance(r[0], (int, float)): rowof[(dt.date(1899, 12, 30) + dt.timedelta(days=int(r[0]))).isoformat()] = i
    data = []; nxt = len(col) + 1
    for d, row in new.items():
        r = rowof.get(d)
        if not r: r = nxt; nxt += 1
        data.append({'range': f'Oura!A{r}:U{r}', 'values': [row]})
    res = api('POST', U + '/values:batchUpdate', ts, {'valueInputOption': 'USER_ENTERED', 'data': data})
    out = res.get('error') or f'{len(data)} days upserted ({min(new)}..{max(new)})'
    try:
        import app_push; app_push.drain_and_push()
    except Exception as ex: out += f' | app push failed: {type(ex).__name__}: {ex}'
    return out

if __name__ == '__main__': print(sync())
