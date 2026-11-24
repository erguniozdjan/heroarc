"""Notion storage backend for HeroArc (opt-in: set STORAGE=notion in .env; the default stays 'sheets').

Notion is the place writes land first; nothing here deletes anything. Every write is idempotent on a natural key (event id or
date), so a retry never duplicates. Needs an internal integration token (NOTION_TOKEN) and a parent page shared with it.
Tables are created by setup_notion.py under that page; their ids go into .env as NOTION_IDS (one JSON line).
"""
import json, time, urllib.request, urllib.error, datetime as dt
from config import env, set_env

API = env('NOTION_API_BASE', 'https://api.notion.com/v1')   # only changed for local testing
VER = '2025-09-03'
EPOCH = dt.date(1899, 12, 30)


def _req(method, path, body=None):
    r = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': 'Bearer ' + env('NOTION_TOKEN', required=True), 'Notion-Version': VER, 'Content-Type': 'application/json'})
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(r, timeout=40))
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(1.5 * (attempt + 1)); continue
            raise RuntimeError(f'Notion {e.code}: {e.read().decode()[:200]}')
    raise RuntimeError('Notion kept failing; try again later')


def ids():
    return json.loads(env('NOTION_IDS', required=True))


def title(s): return {'title': [{'text': {'content': str(s)[:200]}}]}
def text(s): return {'rich_text': [{'text': {'content': str(s)[:1900]}}]} if s not in (None, '') else {'rich_text': []}
def num(v): return {'number': float(v)} if isinstance(v, (int, float)) and not isinstance(v, bool) else {'number': None}
def date(iso): return {'date': {'start': iso}}


def query(name, flt=None):
    out, cur = [], None
    while True:
        body = {'page_size': 100}
        if flt: body['filter'] = flt
        if cur: body['start_cursor'] = cur
        r = _req('POST', f"/data_sources/{ids()[name]['ds']}/query", body)
        out += r['results']
        if not r.get('has_more'): return out
        cur = r['next_cursor']


def create(name, props):
    return _req('POST', '/pages', {'parent': {'type': 'data_source_id', 'data_source_id': ids()[name]['ds']}, 'properties': props})


def update(page_id, props):
    return _req('PATCH', '/pages/' + page_id, {'properties': props})


def rt(p, k): return ''.join(x['plain_text'] for x in p['properties'][k]['rich_text'])
def ttl(p, k='Name'): return ''.join(x['plain_text'] for x in p['properties'][k]['title'])
def n_of(p, k): return p['properties'][k]['number']
def serial(iso): return (dt.date.fromisoformat(iso[:10]) - EPOCH).days
def iso_of(s): return (EPOCH + dt.timedelta(days=int(s))).isoformat()


# ---------------------------------------------------------------- reads (return rows shaped like the sheet ranges the app builder expects)
_cache = {}
def _all(name):
    if name not in _cache: _cache[name] = query(name)
    return _cache[name]
def fresh(): _cache.clear()


def _tbl(name, cols, sort=None):
    ps = sorted(_all(name), key=lambda p: (p['properties'].get('Row', {}).get('number') or 0, p['created_time']))
    out = []
    for p in ps:
        row = []
        for c in cols:
            x = p['properties'][c]; t = x['type']
            if t == 'number': row.append('' if x['number'] is None else x['number'])
            elif t == 'date': row.append(serial(x['date']['start']) if x['date'] else '')
            elif t == 'select': row.append(x['select']['name'] if x['select'] else '')
            elif t == 'checkbox': row.append(1 if x['checkbox'] else 0)
            else: row.append(''.join(r['plain_text'] for r in x[t]))
        out.append(row)
    return sorted(out, key=sort) if sort else out


OURA_COLS = ['Date', 'Sleep score', 'Readiness', 'Activity score', 'Sleep (h)', 'Deep (min)', 'REM (min)', 'Light (min)', 'Efficiency %', 'Avg HRV', 'Lowest HR',
             'Avg HR', 'Temp deviation (C)', 'Steps', 'Active kcal', 'Total kcal', 'Bedtime (day fraction)', 'Wake time (day fraction)', 'High-stress (min)',
             'High-recovery (min)', 'Stress summary']


def make_read(sheet_read=None):
    """read(range) -> rows, the same call app_push.build() makes against Sheets, answered from Notion."""
    def read(rng):
        r = rng.replace("'", '')
        if r.startswith('Oura!A2'): return _tbl('Oura Daily', OURA_COLS, lambda x: x[0] or 0)
        if r.startswith('Weight Log!A2'): return _tbl('Weight', ['Date', 'Weight (lb)'], lambda x: x[0] or 0)
        if r.startswith('Nutrition Log!A2'): return _tbl('Meals', ['Date', 'Time', 'Meal', 'Name', 'Calories', 'Protein (g)', 'Carbs (g)', 'Fat (g)'], lambda x: x[0] or 0)
        if r.startswith('Settings!B1:B4'):
            st = {ttl(p): n_of(p, 'Value') for p in _all('Settings')}
            return [[st.get('kcal target')], [st.get('protein target')], [st.get('steps goal')], [st.get('active kcal goal')]]
        if r.startswith('Settings!B7'):
            st = {ttl(p): n_of(p, 'Value') for p in _all('Settings')}
            return [['set']] if st.get('goals set') else []
        if r.startswith('Training Log!A2'):
            t = _tbl('Training', ['Date', 'Workout', 'Status', 'Lift', 'Direction', 'Max (lb)', 'Notes', 'Logged at', 'Event id', 'Reps'], lambda x: (str(x[7]), str(x[8])))
            for x in t: x[8] = str(x[8]).split('|')[0]
            return t
        if r.startswith('Plan!A2'):
            t = _tbl('Plan', ['Workout', 'Exercise', 'Sets', 'Key lift', 'Order'], lambda x: (x[4] if isinstance(x[4], (int, float)) else 9999))
            return [x for x in t if x[0] and x[1]]
        if r.startswith('Habits!A2'): return [[a, b, 'x' if c else ''] for a, b, c in _tbl('Habits', ['Name', 'Habit id', 'Archived'])]
        if r.startswith('Habit Log!A2'): return _tbl('Habit Log', ['Date', 'Habit id', 'Done', 'Logged at', 'Event id'], lambda x: str(x[3]))
        if r.startswith('Mood Log!A2'): return _tbl('Mood Log', ['Date', 'Time', 'Mood (1-5)', 'Note', 'Logged at', 'Event id'], lambda x: str(x[4]))
        return []
    return read


# ---------------------------------------------------------------- writes
def fmt_time(hhmm):
    h, m = map(int, hhmm.split(':')); return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def add_meal(date_iso, hhmm, meal, items, kcal, p, c, f, conf='Medium', source='Photo estimate', notes=''):
    t = fmt_time(hhmm); key = f'{date_iso} {t} {meal} {items[:40]}'
    have = {ttl(x) for x in query('Meals', {'property': 'Date', 'date': {'equals': date_iso}})}
    if key in have: return 'exists'
    create('Meals', {'Name': title(key), 'Date': date(date_iso), 'Time': text(t),
        'Meal': {'select': {'name': meal}} if meal in ('Breakfast', 'Lunch', 'Dinner', 'Snack') else {'select': None},
        'Calories': num(kcal), 'Protein (g)': num(p), 'Carbs (g)': num(c), 'Fat (g)': num(f),
        'Confidence': {'select': {'name': conf}} if conf in ('High', 'Medium', 'Low') else {'select': None}, 'Source': text(source), 'Notes': text(notes)})
    return 'added'


def day_totals(date_iso):
    r = query('Meals', {'property': 'Date', 'date': {'equals': date_iso}})
    g = lambda p, k: p['properties'][k]['number'] or 0
    return {'kcal': sum(g(x, 'Calories') for x in r), 'protein': sum(g(x, 'Protein (g)') for x in r), 'n': len(r)}


def set_weight(date_iso, w, note=''):
    r = query('Weight', {'property': 'Date', 'date': {'equals': date_iso}})
    if r: update(r[0]['id'], {'Weight (lb)': num(w), 'Notes': text(note)}); out = 'updated'
    else: create('Weight', {'Name': title(date_iso), 'Date': date(date_iso), 'Weight (lb)': num(w), 'Notes': text(note)}); out = 'added'
    d = dt.date.fromisoformat(date_iso)   # 7-day average = mean of weights in (date-7, date]
    rows = query('Weight', {'and': [{'property': 'Date', 'date': {'after': (d - dt.timedelta(days=7)).isoformat()}}, {'property': 'Date', 'date': {'on_or_before': date_iso}}]})
    ws = [x['properties']['Weight (lb)']['number'] for x in rows if x['properties']['Weight (lb)']['number'] is not None]
    me = [x for x in rows if x['properties']['Date']['date']['start'][:10] == date_iso]
    if ws and me: update(me[0]['id'], {'7-day avg': num(round(sum(ws) / len(ws), 1))})
    return out


def add_training_rows(rows):
    have = {rt(p, 'Event id') for p in query('Training')}; c = 0
    for r in rows:
        r = (list(r) + [''] * 10)[:10]; d = iso_of(r[0]); key = f'{r[8]}|{r[3] or ""}'
        if key in have: continue
        create('Training', {'Name': title(f'{d} {r[1]} {r[3] or "(session)"}'), 'Date': date(d), 'Workout': text(r[1]), 'Status': text(r[2]), 'Lift': text(r[3]),
            'Direction': text(r[4]), 'Max (lb)': num(r[5]), 'Reps': num(r[9]), 'Notes': text(r[6]), 'Event id': text(key), 'Logged at': text(r[7])})
        c += 1; time.sleep(0.3)
    return c


def add_habit_rows(rows):
    ex = query('Habit Log'); have = {rt(p, 'Event id') for p in ex}
    base = max([p['properties']['Row']['number'] or 0 for p in ex] or [0]); c = 0
    for r in rows:
        r = (list(r) + [''] * 5)[:5]
        if r[4] in have: continue
        d = iso_of(r[0]); base += 1
        create('Habit Log', {'Row': num(base), 'Name': title(f'{d} {r[1]}'), 'Date': date(d), 'Habit id': text(r[1]), 'Done': {'checkbox': bool(r[2])},
            'Event id': text(r[4]), 'Logged at': text(r[3])})
        c += 1; time.sleep(0.3)
    return c


def add_mood_rows(rows):
    have = {rt(p, 'Event id') for p in query('Mood Log')}; c = 0
    for r in rows:
        r = (list(r) + [''] * 6)[:6]
        if r[5] in have: continue
        d = iso_of(r[0])
        create('Mood Log', {'Name': title(f'{d} {r[1]}'), 'Date': date(d), 'Time': text(r[1]), 'Mood (1-5)': num(r[2]), 'Note': text(r[3]), 'Event id': text(r[5]), 'Logged at': text(r[4])})
        c += 1; time.sleep(0.3)
    return c


def write_habit_list(rows):
    """rows = [[name, id, 'x' or '']]. Upserts by id and renumbers Row. Never deletes."""
    have = {rt(p, 'Habit id'): p for p in query('Habits')}; i = 0
    for name, hid, arch in rows:
        i += 1
        props = {'Name': title(name), 'Habit id': text(hid), 'Archived': {'checkbox': bool(arch)}, 'Row': num(i)}
        if hid in have: update(have[hid]['id'], props)
        else: create('Habits', props)
        time.sleep(0.3)
    return i


def write_plan(rows, plan_id, stamp):
    """Old plan rows are copied to Plan History first; the Plan table is then rewritten in place. Nothing is deleted."""
    cur = sorted(query('Plan'), key=lambda p: p['created_time'])
    if any(rt(p, 'Plan id') == plan_id for p in cur): return plan_id
    for p in cur:
        if rt(p, 'Workout') or rt(p, 'Exercise'):
            create('Plan History', {'Name': title(ttl(p)), 'Workout': text(rt(p, 'Workout')), 'Exercise': text(rt(p, 'Exercise')), 'Sets': text(rt(p, 'Sets')),
                'Key lift': text(rt(p, 'Key lift')), 'Order': num(n_of(p, 'Order')), 'Replaced at': text(stamp)}); time.sleep(0.3)
    for i, r in enumerate(rows):
        props = {'Name': title(f'{r[0]} - {r[1]}'), 'Workout': text(r[0]), 'Exercise': text(r[1]), 'Sets': text(r[2]), 'Key lift': text(r[3]), 'Order': num(r[4]), 'Plan id': text(plan_id)}
        if i < len(cur): update(cur[i]['id'], props)
        else: create('Plan', props)
        time.sleep(0.3)
    for p in cur[len(rows):]:
        update(p['id'], {'Name': title('(unused)'), 'Workout': text(''), 'Exercise': text(''), 'Sets': text(''), 'Key lift': text(''), 'Plan id': text(plan_id)}); time.sleep(0.3)
    return plan_id


def set_goals(kcal, protein):
    st = {ttl(p): p for p in query('Settings')}
    for k, v in (('kcal target', kcal), ('protein target', protein), ('goals set', 1)):
        if k in st: update(st[k]['id'], {'Value': num(v)})
        else: create('Settings', {'Name': title(k), 'Value': num(v)})
    fresh()


def upsert_oura(rows):
    """rows are 21-column lists: [iso date, sleep, readiness, activity, sleep_h, deep, rem, light, eff, hrv, lowhr, avghr, temp, steps, active, total, bed, wake, hi-stress, hi-recov, summary]."""
    if not rows: return 0
    have = {ttl(p): p for p in query('Oura Daily', {'property': 'Date', 'date': {'on_or_after': min(r[0] for r in rows)}})}; c = 0
    num_cols = OURA_COLS[1:18]
    for r in rows:
        r = (list(r) + [''] * 21)[:21]; d = r[0]
        props = {'Name': title(d), 'Date': date(d), 'High-stress (min)': num(r[18]), 'High-recovery (min)': num(r[19]), 'Stress summary': text(r[20])}
        for k, i in zip(num_cols, range(1, 18)): props[k] = num(r[i])
        x = have.get(d)
        if x is None: create('Oura Daily', props); c += 1; time.sleep(0.3)
        else:
            diff = any((x['properties'][k]['number'] is None) != (props[k]['number'] is None) or (props[k]['number'] is not None and abs(x['properties'][k]['number'] - props[k]['number']) > 1e-4) for k in num_cols)
            if diff: update(x['id'], {k: v for k, v in props.items() if k not in ('Name', 'Date')}); c += 1; time.sleep(0.3)
    return c
