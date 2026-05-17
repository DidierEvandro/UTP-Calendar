import importlib, inspect, os, sys
from pathlib import Path

print('PYTHON', sys.executable)
try:
    p = importlib.import_module('playwright')
    print('PLAYWRIGHT_VERSION', getattr(p, '__version__', 'unknown'))
    print('PLAYWRIGHT_LOCATION', getattr(p, '__file__', 'n/a'))
except Exception as e:
    print('ERR_IMPORT_PLAYWRIGHT', e)
    sys.exit(2)

try:
    from playwright._impl._driver import compute_driver_executable, get_driver_env
    de = compute_driver_executable()
    print('compute_driver_executable ->', de)
    env = get_driver_env()
    print('driver env keys:', list(env.keys()))
except Exception as e:
    print('ERR_DRIVER_INTROSPECT', e)

# Check PLAYWRIGHT_BROWSERS_PATH
pw_env = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
print('PLAYWRIGHT_BROWSERS_PATH (env) =', pw_env)

local_app = os.environ.get('LOCALAPPDATA') or os.environ.get('USERPROFILE')
if local_app:
    local_app = Path(local_app)
    ms_playwright = local_app / 'ms-playwright'
    print('EXPECTED_MS_PLAYWRIGHT_DIR=', ms_playwright)
    if ms_playwright.exists():
        print('ms-playwright exists, listing:')
        for pth in ms_playwright.rglob('*'):
            try:
                print(' -', pth.relative_to(ms_playwright))
            except Exception:
                print(' -', pth)
    else:
        print('ms-playwright not found')

# Also check for .local-browsers under package driver
try:
    # search for any chrome-headless-shell in temp dirs
    import glob
    candidates = glob.glob(os.path.join(os.getenv('TEMP', ''), '_MEI*', 'playwright', 'driver', 'package', '.local-browsers', '**', 'chrome-headless-shell.exe'), recursive=True)
    print('TEMP chrome-headless-shell candidates:', candidates[:5])
except Exception as e:
    print('ERR_SEARCH_TEMP', e)

print('DONE')
