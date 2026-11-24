#!/usr/bin/env python3
"""Create the HeroArc tables in YOUR Notion workspace and save their ids to .env (STORAGE=notion).

Before running:
  1. notion.so/profile/integrations -> New integration (internal). Permissions: read, update and insert content (no delete needed).
  2. Put the secret in .env as NOTION_TOKEN=...   (never paste it in chat)
  3. Make an empty page in Notion (any name, e.g. "HeroArc"), open it, "..." -> Connections -> add your integration.
  4. Put that page's id in .env as NOTION_PARENT_PAGE=...  (the 32 characters at the end of its URL)

Safe to re-run: tables that already exist in NOTION_IDS are skipped. Nothing is deleted, ever.
"""
import json
from config import env, set_env
import notion_store as NS

parent = env('NOTION_PARENT_PAGE', required=True).replace('-', '')
if len(parent) != 32: raise SystemExit('NOTION_PARENT_PAGE should be the 32-character page id from the end of the page URL.')

T, N = {'rich_text': {}}, {'number': {}}
def sel(*o): return {'select': {'options': [{'name': x} for x in o]}}
SPECS = {
 'Meals': {'Name': {'title': {}}, 'Date': {'date': {}}, 'Time': T, 'Meal': sel('Breakfast', 'Lunch', 'Dinner', 'Snack'), 'Calories': N, 'Protein (g)': N, 'Carbs (g)': N, 'Fat (g)': N,
           'Confidence': sel('High', 'Medium', 'Low'), 'Source': T, 'Notes': T},
 'Weight': {'Name': {'title': {}}, 'Date': {'date': {}}, 'Weight (lb)': N, '7-day avg': N, 'Notes': T},
 'Oura Daily': {'Name': {'title': {}}, 'Date': {'date': {}}, 'Sleep score': N, 'Readiness': N, 'Activity score': N, 'Sleep (h)': N, 'Deep (min)': N, 'REM (min)': N, 'Light (min)': N,
                'Efficiency %': N, 'Avg HRV': N, 'Lowest HR': N, 'Avg HR': N, 'Temp deviation (C)': N, 'Steps': N, 'Active kcal': N, 'Total kcal': N,
                'Bedtime (day fraction)': N, 'Wake time (day fraction)': N, 'High-stress (min)': N, 'High-recovery (min)': N, 'Stress summary': T},
 'Training': {'Name': {'title': {}}, 'Date': {'date': {}}, 'Workout': T, 'Status': T, 'Lift': T, 'Direction': T, 'Max (lb)': N, 'Reps': N, 'Notes': T, 'Event id': T, 'Logged at': T},
 'Plan': {'Name': {'title': {}}, 'Workout': T, 'Exercise': T, 'Sets': T, 'Key lift': T, 'Order': N, 'Type': T, 'Plan id': T},
 'Plan History': {'Name': {'title': {}}, 'Workout': T, 'Exercise': T, 'Sets': T, 'Key lift': T, 'Order': N, 'Type': T, 'Replaced at': T},
 'Habits': {'Name': {'title': {}}, 'Habit id': T, 'Archived': {'checkbox': {}}, 'Row': N},
 'Habit Log': {'Name': {'title': {}}, 'Date': {'date': {}}, 'Habit id': T, 'Done': {'checkbox': {}}, 'Event id': T, 'Logged at': T, 'Row': N},
 'Mood Log': {'Name': {'title': {}}, 'Date': {'date': {}}, 'Time': T, 'Mood (1-5)': N, 'Note': T, 'Event id': T, 'Logged at': T},
 'Settings': {'Name': {'title': {}}, 'Value': N},
}
have = json.loads(env('NOTION_IDS', '{}'))
for name, props in SPECS.items():
    if name in have: print('already there:', name); continue
    r = NS._req('POST', '/databases', {'parent': {'type': 'page_id', 'page_id': parent}, 'title': [{'text': {'content': name}}], 'initial_data_source': {'properties': props}})
    have[name] = {'db': r['id'], 'ds': r['data_sources'][0]['id']}
    set_env('NOTION_IDS', json.dumps(have, separators=(',', ':')))   # saved after every table so a failure can be resumed
    print('created:', name)
set_env('STORAGE', 'notion')
# goals live in the Settings table (same numbers the sheet's Settings tab holds)
st = {NS.ttl(p) for p in NS.query('Settings')}
for k, v in (('kcal target', int(env('CALORIE_GOAL', 2200))), ('protein target', int(env('PROTEIN_GOAL', 150))), ('steps goal', int(env('STEPS_GOAL', 10000))), ('active kcal goal', int(env('ACTIVE_KCAL_GOAL', 500)))):
    if k not in st: NS.create('Settings', {'Name': NS.title(k), 'Value': NS.num(v)})
print('Done. STORAGE=notion is saved in .env. Edit your goals in the Settings table in Notion.')
