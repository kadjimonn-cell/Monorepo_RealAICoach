import subprocess
import sys

with open('/app/frontend/export_out.log', 'w') as f:
    process = subprocess.Popen(
        "cd /app/frontend && yarn export:web",
        shell=True,
        stdout=f,
        stderr=subprocess.STDOUT,
        start_new_session=True
    )
print("Spawned process with PID:", process.pid)
