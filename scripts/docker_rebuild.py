import subprocess
import sys
from pathlib import Path

root = Path(r'd:\approvalSys')
log_path = root / 'docker_build.log'

commands = [
    ['docker', 'build', '-t', 'approvalsys:latest', '.'],
    ['docker', 'run', '-d', '--name', 'approvalsys_app', '-p', '80:80', 'approvalsys:latest'],
]

for cmd in commands:
    print('RUN', ' '.join(cmd))
    completed = subprocess.run(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = completed.stdout.decode('utf-8', errors='replace')
    log_path.write_text(output, encoding='utf-8')
    print('exit', completed.returncode)
    if completed.returncode != 0:
        print(output)
        sys.exit(completed.returncode)

print('done')
print(log_path.read_text(encoding='utf-8', errors='replace'))
