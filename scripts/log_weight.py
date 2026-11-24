#!/usr/bin/env python3
"""Log (or correct) a weight for a date, then refresh the app.
usage: log_weight.py 189.2 [--date YYYY-MM-DD]"""
import argparse, datetime as dt, urllib.parse, sys
from config import now, env, STORAGE
from google_auth import token, api
import app_push
ap = argparse.ArgumentParser(); ap.add_argument('lb', type=float); ap.add_argument('--date'); a = ap.parse_args()
if not 50 < a.lb < 700: sys.exit(f'{a.lb} lb does not look like a body weight; not logging.')
d = a.date or now().date().isoformat()
if STORAGE == 'notion':
    import notion_store as NS
    verb = NS.set_weight(d, round(a.lb, 1)).capitalize(); NS.fresh()
    print(f'{verb} {a.lb} lb for {d}. App pushed: {app_push.safe_push()}'); raise SystemExit(0)
S = env('SHEET_ID', required=True); ts = token(); U = f'https://sheets.googleapis.com/v4/spreadsheets/{S}/values/'
v = api('GET', U + urllib.parse.quote("'Weight Log'!A2:B1000") + '?valueRenderOption=UNFORMATTED_VALUE', ts).get('values', [])
rows = {(dt.date(1899, 12, 30) + dt.timedelta(days=int(r[0]))).isoformat(): i + 2 for i, r in enumerate(v) if r and isinstance(r[0], (int, float))}
if d in rows:
    r = rows[d]; api('PUT', U + urllib.parse.quote(f"'Weight Log'!B{r}") + '?valueInputOption=USER_ENTERED', ts, {'values': [[a.lb]]}); verb = 'Updated'
else:
    r = len(v) + 2
    f = [d, a.lb, f'=ROUND(AVERAGEIFS($B$2:$B,$A$2:$A,">"&A{r}-7,$A$2:$A,"<="&A{r}),1)',
         f'=IF(A{r}-A{r-1}=1,B{r}-B{r-1},"")' if r > 2 else '']
    res = api('PUT', U + urllib.parse.quote(f"'Weight Log'!A{r}:D{r}") + '?valueInputOption=USER_ENTERED', ts, {'values': [f]})
    if 'error' in res: sys.exit(f'write failed: {res}')
    verb = 'Logged'
back = api('GET', U + urllib.parse.quote(f"'Weight Log'!A{r}:D{r}") + '?valueRenderOption=FORMATTED_VALUE', ts).get('values')
print(f'{verb} {a.lb} lb for {d}. Row: {back}. App pushed: {app_push.safe_push()}')
