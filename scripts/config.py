"""Shared settings. Everything personal lives in ../.env, never in code."""
import os, sys, datetime as dt
from zoneinfo import ZoneInfo
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, '.env')

def _load():
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))
_load()

def env(k, default=None, required=False):
    v = os.environ.get(k, default)
    if required and not v:
        sys.exit(f'Missing {k} in .env (see README.md).')
    return v

def set_env(k, v):
    """Write or replace one KEY=value line in .env (file stays private, mode 600)."""
    lines = open(ENV_PATH).read().split('\n') if os.path.exists(ENV_PATH) else []
    out, found = [], False
    for l in lines:
        if l.startswith(k + '='): out.append(f'{k}={v}'); found = True
        else: out.append(l)
    if not found: out.append(f'{k}={v}')
    open(ENV_PATH, 'w').write('\n'.join(out).rstrip('\n') + '\n')
    os.chmod(ENV_PATH, 0o600); os.environ[k] = str(v)

STORAGE = env('STORAGE', 'sheets').strip().lower()   # 'sheets' (default) or 'notion'
if STORAGE not in ('sheets', 'notion'): sys.exit("STORAGE in .env must be 'sheets' or 'notion'.")
TZ = ZoneInfo(env('TIMEZONE', 'UTC'))
def now(): return dt.datetime.now(TZ)
