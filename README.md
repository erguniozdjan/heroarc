# HeroArc

A private health dashboard for your phone. Your Oura ring, weight, food and training go into **one Google Sheet or Notion workspace that you own**, and a small app shows them on a locked-down web page that only your email can open.

- **Runs on your own accounts.** Google, Oura and Cloudflare are all yours. Nothing is shared with anyone else, and nothing here phones home.
- **Costs nothing** on free plans (Cloudflare Workers, Google Sheets, Oura developer app). Any AI you use to log food is your own.
- **Your AI does the logging.** The scripts below are the "hands". Point your own AI assistant at this folder and have it run them when you text it a weight, a meal photo or a workout.

## What you get
- Phone and desktop app: readiness, sleep, activity, weight, calories and protein against your goals, energy balance (calories in minus Oura's calories out), weekly balance, and a 14-day sleep/readiness chart. Browse back up to 90 days.
- **Your own training plan, edited in the app.** The Training card starts empty. Tap Set up plan, name your workouts, add exercises with sets and reps, and star the lifts you want to track a max for. Log a workout with one tap (weight and reps for starred lifts). Changing the plan keeps your history.
- **Your own habits, edited in the app.** Add up to 8 habits, rename, reorder, hide and restore them from the Habits card. Tick them off each day; the card shows a week strip, a month grid and a trend.
- **Goals and weight in the app.** A calculator (Mifflin-St Jeor, an estimate and not medical advice) suggests calories and protein from your age, height, weight, activity and goal. You can accept it or type your own. Enter your weight from the Weight card.
- A hero character in the header that forges itself from your last 7 days: helm = nights scoring 75+, armor = days at 80% of your protein goal, legs = days near your step goal, blade = workouts logged. Tap it to see what counts. Rest days and unlogged days never count against you.
- Tap or drag along the weight and sleep charts to read the exact number for a day.
- Seven looks you can switch between with the round button at the bottom right: Night, Street Fighter, Cyberpunk, Gilded, Beige Box '84, Color Archive and E30 Cluster (analog gauges). The choice is remembered on each device.
- A Google Sheet with tabs: Settings, Oura, Nutrition Log, Weight Log, Training Log, Plan, Habits, Habit Log, Mood Log. (If you set up before the Mood card existed, add a tab named Mood Log with headers Date, Time, Mood (1-5), Note, Logged at, Event id; the card stays empty until then.)
- Scripts: `sync.py` (Oura to sheet to app, and your in-app edits to the sheet), `log_food.py`, `log_weight.py`, `log_training.py`.

How edits in the app reach your sheet: the app never writes to Google. It drops each edit into a small queue on Cloudflare, and `sync.py` (run every 15 minutes) copies it into your sheet, rebuilds the snapshot and then clears the queue. An edit shows in the app straight away and lands in the sheet on the next sync.

## What you need first
- A computer or small server that can run Python 3.9+ and Node 18+ (Node is only used to syntax-check the page before it is uploaded) and stay on, or run on a schedule.
- An Oura ring with membership.
- A Google account, a Cloudflare account (free), a GitHub account if you want your own copy of this code.

## Setup (about 45 minutes, once)

### 1. Get the code and make your settings file
```
git clone <this repo> heroarc && cd heroarc
cp .env.example .env && chmod 600 .env
```
Edit `.env`: set `TIMEZONE`, your calorie and protein goals, and `ALLOWED_EMAIL` (the one email that may open the app). **`.env` holds secrets. It is ignored by git. Never commit it, paste it in a chat, or share it.**

### 2. Google (your sheet)
1. Go to console.cloud.google.com, create a project, and **enable the Google Sheets API**.
2. OAuth consent screen: External, Testing, and add your own Gmail as a test user.
3. Credentials, Create credentials, **OAuth client ID**, type **Desktop app**. Put the client id and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
4. Run `python3 scripts/auth_google.py`. Open the link, allow access, and when the browser lands on a "can't connect to localhost" page, paste that full address back into the terminal. (That error is expected.)
5. Run `python3 scripts/setup_sheet.py`. It creates **HeroArc Health Log** in your Drive and saves its id. Edit your goals on the **Settings** tab at any time.

### 3. Oura
1. Go to cloud.ouraring.com/oauth/applications and create an app. Set the **redirect URI to exactly** `http://localhost:8080/callback` and tick all the scopes (email, personal, daily, heartrate, workout, session, spo2, tag, stress).
2. Put the client id and secret in `.env` as `OURA_CLIENT_ID` and `OURA_CLIENT_SECRET`.
3. Run `python3 scripts/auth_oura.py` and follow the same open-link, paste-back-the-address flow. Oura codes are single-use and expire fast, so paste right away.
4. Backfill and test: `python3 scripts/sync.py --days 60`. Your Oura tab should fill.
   - Note: Oura only has your latest sleep after your ring has synced through the Oura app on your phone. See "Keeping it fresh" below.

### 4. Cloudflare (the private app)
1. Sign up at cloudflare.com (free). In the dashboard, open **Zero Trust** and choose the Free plan. This is needed for the login gate.
2. Create an API token (My Profile, API Tokens, Create Custom Token) with **Account** permissions: *Workers Scripts: Edit*, *Workers KV Storage: Edit*, *Access: Apps and Policies: Edit*. Scope it to your account only.
3. Put `CLOUDFLARE_ACCOUNT_ID` (from the dashboard sidebar) and `CLOUDFLARE_API_TOKEN` in `.env`.
4. Try it without changing anything: `python3 scripts/deploy.py --dry-run`
5. Deploy: `python3 scripts/deploy.py`. If it says you have no workers.dev subdomain, set `WORKERS_SUBDOMAIN=` to a unique name in `.env` and re-run.
6. **The gate test must pass.** The script prints three lines: *no login*, *forged header*, *forged cookie*. Each must say `302`. If any is not 302, **stop**: do not load data until it is fixed.
7. Push your first data: `python3 scripts/app_push.py`
8. Open the printed address on your phone. Enter your email, then the code Cloudflare emails you. Add it to your home screen (iPhone: Share, then Add to Home Screen. Android: menu, Install app).
   - Optional: Google sign-in instead of the emailed code is in Zero Trust, Settings, Authentication.

## The Excel / Google Sheets template
`template/HeroArc_Health_Log_Template.xlsx` is a ready-made workbook in the same dark teal and clay style as the app. It has seven tabs: README, Calculator, Settings, Oura, Nutrition Log, Weight Log and Training Log.

- The log tabs are blank. The Calculator holds **made-up example numbers** (a 180 lb person on a cut) so you can see how it works. Replace them with yours.
- The Calculator turns bodyweight, goal (Cut, Recomp or Bulk), a maintenance multiplier and a protein-per-lb figure into daily calorie and protein targets. The Settings tab picks those up and the app reads them from there. The workbook's own README tab has a step-by-step guide.
- Two ways to use it: run `python3 scripts/setup_sheet.py` (builds a plain version in your Google account), or open Google Sheets, choose File > Import > Upload the .xlsx, then copy the sheet ID from its address into `.env` as `SHEET_ID=...`.
- Rebuild it from source with `pip install openpyxl` then `python3 tools/build_template_xlsx.py`.
- Note: `setup_sheet.py` makes a simpler, unstyled sheet with goals typed on the Settings tab. The .xlsx adds the Calculator and the styling.

## Choose where your data lives: Google Sheets (default) or Notion

HeroArc can keep your data in **a Google Sheet** (the default, everything above) **or in Notion**. Pick one at setup; the app looks the same either way.
You switch with one line in `.env`: `STORAGE=sheets` (default) or `STORAGE=notion`. This is the `notion-backend` branch; `main` is sheets only.

**What is the same:** the app, the logging scripts (`log_food.py`, `log_weight.py`, `log_training.py`), `sync.py`, the Cloudflare setup and the gate checks. Edits made in the app still go to a small queue on Cloudflare and are copied into your storage every sync, and a tap is only removed from the queue once it is safely written.

**With Notion, the first place writes land is Notion.** Nothing is ever deleted by the scripts. Every write is keyed on an event id or a date, so running anything twice never duplicates a row.

### Notion setup (about 10 minutes, instead of step 2 "Google")
1. Go to notion.so/profile/integrations, create an **internal** integration, and give it permission to read, update and insert content (it does not need delete).
2. Put the secret in `.env` as `NOTION_TOKEN=...` (never paste it into chat, a screenshot or an AI prompt).
3. Create an empty page in Notion (for example "HeroArc"). Open it, click "..." then Connections, and add your integration.
4. Copy the page id (the last 32 characters of the page's URL) into `.env` as `NOTION_PARENT_PAGE=...`.
5. Run `python3 scripts/setup_notion.py`. It creates ten tables under that page (Meals, Weight, Oura Daily, Training, Plan, Plan History, Habits, Habit Log, Mood Log, Settings), saves their ids to `.env` and sets `STORAGE=notion`. It is safe to run again; existing tables are skipped.
6. Set your calories, protein, steps and active-calorie goals in the **Settings** table (or set `CALORIE_GOAL`, `PROTEIN_GOAL` etc. in `.env` before step 5 to seed them).
7. Carry on with Oura and Cloudflare (steps 3 and 4 below). Google is not needed in this mode: you can skip step 2 and the Google OAuth client.

### Moving between the two
- There is no automatic migration yet. Switching `STORAGE` points the app at the other store, which will start empty (the Oura sync can backfill with `python3 scripts/sync.py --days 60`).
- If you already run on a sheet and want Notion too, ask your AI to copy the rows across table by table; every table has the same columns as its sheet tab.

### Notion limits to know about
- Notion's API allows about three requests a second. Reads of the whole history are slower than a sheet, so a sync takes a few seconds longer.
- The API cannot create formula columns, chart views or table footers on an existing table. Add averages, bars and charts in Notion by hand if you want them.
- Delete nothing in the tables while the app is running. The app reads every row; a removed Settings row falls back to the defaults.
- **Not tested against a real Notion workspace on this branch.** It was tested end to end against a local stand-in for the Notion API (all write paths, the snapshot builder, the queue drain, retries and idempotence) and compared with `main` in sheets mode (identical snapshot). Your first real run is the real test; report anything odd.

## Daily use (the logging scripts)
Run these from the folder, or have your AI run them for you:
```
python3 scripts/log_weight.py 189.2
python3 scripts/log_food.py --meal Lunch --items "chicken, rice" --kcal 650 --p 48 --c 70 --f 14 --conf Medium --source "photo estimate"
python3 scripts/log_training.py --workout "Push" --lift "Bench Press" --lb 185 --reps 6
```
Each one prints a single line saying what was logged. `log_food.py` and `log_weight.py` refresh the app straight away. `--dry-run` on `log_food.py` checks everything without writing.

### Giving the work to your AI
Tell your assistant: "You operate HeroArc in this folder. Use the scripts in `scripts/`. Never print or send `.env`. Estimate food from photos and show me a breakdown (per item grams, kcal, protein/carbs/fat, a confidence level, the biggest uncertainty). Only log after I say so. Use my timezone." That is the whole contract.

## Keeping it fresh
Run `python3 scripts/sync.py` every 15 minutes (cron example: `*/15 6-22 * * * cd ~/heroarc && python3 scripts/sync.py >> sync.log 2>&1`).

**Oura only uploads sleep when its phone app syncs with the ring.** The API has no "sync now" call, so to get your sleep score without opening the app: on iPhone, turn on Settings, Oura, Background App Refresh, Bluetooth, Location Always, and Cellular Data, turn off Low Power Mode, and do not swipe the Oura app away. Activity and stress update more readily on their own.

## Security notes
- The app is behind Cloudflare Access: only `ALLOWED_EMAIL` can open it, and the Worker refuses any request that did not come through Access.
- Your Google and Oura keys stay on **your** machine. Cloudflare only holds a small JSON snapshot of the numbers shown in the app.
- Never commit `.env` or `oura/tokens.json` (both are in `.gitignore`). If you ever do, rotate the keys.
- Health data on a web server is personal data. Keep the allow list to just you unless you decide otherwise.

## Troubleshooting
- **Oura 400 `invalid_request`:** the redirect URI in the Oura portal must match `OURA_REDIRECT_URI` character for character, and the code is single-use. Start `auth_oura.py` again.
- **No refresh token from Google:** remove the app at myaccount.google.com/permissions and re-run `auth_google.py`.
- **Today box refuses to write:** do not edit `Nutrition Log` columns M to P; the scripts read the Today box there.
- **App shows yesterday's sleep:** the ring has not synced through the Oura app yet.
- **Gate not 302:** do not continue; check the Access app in Zero Trust, Access, Applications.

## Known limits
This is a personal setup, not a product. The scripts have only been exercised against synthetic data and against the author's own accounts. Expect rough edges on first run, and read the printed errors.
