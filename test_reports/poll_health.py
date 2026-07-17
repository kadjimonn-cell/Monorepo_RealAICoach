#!/usr/bin/env python3
"""Poll /health every 250ms after backend restart, capture time-to-first-200."""
import time
import subprocess
import urllib.request
import json
import sys

# Restart backend
print("Restarting backend...", flush=True)
r = subprocess.run(["sudo", "supervisorctl", "restart", "backend"], capture_output=True, text=True)
print(r.stdout.strip(), r.stderr.strip(), flush=True)
t_restart = time.time()

deadline = t_restart + 30.0
first_200_at = None
first_payload = None
attempts = 0
last_err = None
while time.time() < deadline:
    attempts += 1
    try:
        with urllib.request.urlopen("http://localhost:8001/health", timeout=1.0) as resp:
            body = resp.read().decode("utf-8", "replace")
            if resp.status == 200:
                first_200_at = time.time()
                first_payload = body
                break
    except Exception as e:
        last_err = str(e)
    time.sleep(0.25)

if first_200_at is None:
    print(f"FAIL: no 200 in 30s. Last error: {last_err}. Attempts: {attempts}", flush=True)
    sys.exit(1)

elapsed = first_200_at - t_restart
print(f"TIME_TO_FIRST_200_SECONDS={elapsed:.2f}", flush=True)
print(f"ATTEMPTS={attempts}", flush=True)
print(f"FIRST_PAYLOAD={first_payload}", flush=True)

# Poll a bit more to try to catch different init states
states_seen = {}
try:
    payload = json.loads(first_payload)
    states_seen[payload.get("init")] = payload
except Exception:
    pass

# Poll for up to 15 more seconds to observe transitions
end = time.time() + 15
while time.time() < end:
    try:
        with urllib.request.urlopen("http://localhost:8001/health", timeout=1.0) as resp:
            body = resp.read().decode("utf-8", "replace")
            payload = json.loads(body)
            st = payload.get("init")
            if st not in states_seen:
                states_seen[st] = payload
                print(f"NEW_STATE at t+{time.time() - t_restart:.2f}s: {body}", flush=True)
            if st in ("complete", "completed_with_errors"):
                break
    except Exception:
        pass
    time.sleep(0.25)

print(f"STATES_OBSERVED={list(states_seen.keys())}", flush=True)
print(f"FINAL={json.dumps(states_seen, sort_keys=True)}", flush=True)
