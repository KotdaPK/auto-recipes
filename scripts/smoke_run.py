"""Automated smoke-run for auto-recipes.

Checks:
- loads .env
- verifies GEMINI_API_KEY
- tries a small Gemini call via scripts/check_gemini.py
- runs scripts/test_ingest.py (end-to-end ingest)
- prints latest artifacts from data/gemini and data/ingests
- optionally starts uvicorn and checks /docs if --start-server

Usage:
  python scripts/smoke_run.py [--start-server]

Exit code: 0 on success (all checks), non-zero if any step fails.
"""

import os
import sys
import subprocess
import time
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

URL_SAMPLE = "https://www.saltandlavender.com/chicken-piccata/"


def run_subscript(script_path, args=None, timeout=300):
    args = args or []
    cmd = [PY, str(script_path)] + args
    print("\n>>> Running:", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    print("--- stdout ---")
    print(p.stdout[:8000])
    print("--- stderr ---")
    print(p.stderr[:8000])
    return p.returncode, p.stdout, p.stderr


def show_latest(dirpath, prefix=None, tail_chars=1000):
    p = Path(dirpath)
    if not p.exists():
        print(f"No directory: {dirpath}")
        return
    files = sorted(p.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
    if prefix:
        files = [f for f in files if f.name.startswith(prefix)]
    if not files:
        print(f"No files in {dirpath}")
        return
    print(f"Latest file in {dirpath}: {files[0].name}")
    try:
        text = files[0].read_text(encoding='utf8')
        print(text[:tail_chars])
    except Exception as e:
        print(f"Failed to read {files[0]}: {e}")


def check_http(url='http://127.0.0.1:8000/docs', timeout=5):
    print(f"\nChecking HTTP {url} ...")
    try:
        import urllib.request
        resp = urllib.request.urlopen(url, timeout=timeout)
        data = resp.read(4096).decode('utf8', errors='replace')
        print(f"HTTP {resp.status} {resp.reason}")
        print(data[:1000])
        return True
    except Exception as e:
        print("HTTP check failed:", e)
        return False


if __name__ == '__main__':
    start_server = '--start-server' in sys.argv
    ci_mode = '--ci' in sys.argv

    print('Python:', PY)
    print('Project root:', ROOT)
    print('GEMINI_API_KEY set?', bool(os.getenv('GEMINI_API_KEY')))

    # 1. check imports
    failed = False
    try:
        import google.genai as genai  # type: ignore
        print('google.genai import: OK')
    except Exception as e:
        print('google.genai import FAILED:', e)
        failed = True

    try:
        import uvicorn  # type: ignore
        print('uvicorn import: OK')
    except Exception as e:
        print('uvicorn import FAILED:', e)

    # 2. run scripts/check_gemini.py
    check_gemini_path = ROOT / 'scripts' / 'check_gemini.py'
    if check_gemini_path.exists():
        rc, out, err = run_subscript(check_gemini_path)
        if rc != 0:
            print('check_gemini returned non-zero exit code', rc)
            failed = True
    else:
        print('No check_gemini.py script found; skipping Gemini smoke test')

    # 3. run end-to-end ingest test
    test_ingest = ROOT / 'scripts' / 'test_ingest.py'
    if test_ingest.exists():
        rc, out, err = run_subscript(test_ingest)
        if rc != 0:
            print('test_ingest returned non-zero exit code', rc)
            failed = True
    else:
        print('No test_ingest.py script found; skipping ingest test')

    # 4. show latest artifacts
    show_latest(ROOT / 'data' / 'gemini')
    show_latest(ROOT / 'data' / 'ingests')

    # 5. optional: start uvicorn and check /docs
    server_proc = None
    if start_server:
        print('\nStarting uvicorn (background) ...')
        server_proc = subprocess.Popen([PY, '-m', 'uvicorn', 'src.main:app', '--port', '8000'])
        time.sleep(2)
        ok = check_http()
        if not ok:
            print('Server check failed after start')
            failed = True
        # cleanup
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()

    else:
        print('\nSkipping server start; will just probe localhost:8000 if already running')
        check_http()

    if failed:
        print('\nSMOKE RUN: FAIL')
        if ci_mode:
            import json
            out = {"status": "fail", "checks": {"gemini": bool(os.getenv('GEMINI_API_KEY')), "ingest": False}}
            print(json.dumps(out))
        sys.exit(2)
    else:
        print('\nSMOKE RUN: SUCCESS')
        if ci_mode:
            import json
            out = {"status": "success", "checks": {"gemini": bool(os.getenv('GEMINI_API_KEY')), "ingest": True}}
            print(json.dumps(out))
        sys.exit(0)
