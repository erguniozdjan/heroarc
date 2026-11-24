#!/usr/bin/env python3
"""Log a workout (and optionally the max for a lift) from the command line, in the same format the app writes.
usage: log_training.py --workout "Push" [--status done|partial|rest] [--lift "Bench Press" --lb 185 --reps 6] [--date YYYY-MM-DD]"""
import argparse, sys, urllib.parse
from config import now, env, STORAGE
from google_auth import token, api
import training as T
import app_push
ap = argparse.ArgumentParser()
ap.add_argument('--workout', required=True); ap.add_argument('--status', default='done', choices=['done', 'partial', 'rest'])
ap.add_argument('--lift'); ap.add_argument('--lb', type=float); ap.add_argument('--reps', type=int); ap.add_argument('--date'); a = ap.parse_args()
if bool(a.lift) != bool(a.lb is not None and a.reps): sys.exit('Give --lift, --lb and --reps together (reps are required with a weight).')
nw = now(); d = a.date or nw.date().isoformat()
lifts = {a.lift: {'dir': None, 'wt': a.lb, 'reps': a.reps}} if a.lift else {}
ev = {'id': 'cli' + nw.strftime('%y%m%d%H%M%S'), 'd': d, 'w': a.workout, 's': a.status, 'lifts': lifts, 't': nw.strftime('%Y-%m-%d %H:%M:%S')}
if not T.valid_event(ev): sys.exit('That entry did not pass validation; nothing written.')
if STORAGE == 'notion':
    import notion_store as NS
    n_new = NS.add_training_rows(T.rows_for_event(ev)); NS.fresh()
    print(f'Logged {a.workout} ({a.status}) on {d}' + (f': {a.lift} {a.lb:g} lb x {a.reps}.' if a.lift else '.') + f' App pushed: {app_push.safe_push()}'); raise SystemExit(0)
S = env('SHEET_ID', required=True); ts = token(); U = f'https://sheets.googleapis.com/v4/spreadsheets/{S}/values/'
r = api('POST', U + urllib.parse.quote("'Training Log'!A1") + ':append?valueInputOption=RAW&insertDataOption=INSERT_ROWS', ts, {'values': T.rows_for_event(ev)})
if 'error' in r: sys.exit(f'append failed: {r}')
print(f'Logged {a.workout} ({a.status}) on {d}' + (f': {a.lift} {a.lb:g} lb x {a.reps}.' if a.lift else '.') + f' App pushed: {app_push.safe_push()}')
