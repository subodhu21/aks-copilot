#!/usr/bin/env python3
"""Run git commands to push to GitHub and write output to git-push-output.txt"""
import subprocess, os

REPO_DIR = r"c:\aks-ai-agent"
LOG_FILE = os.path.join(REPO_DIR, "git-push-output.txt")

def run(cmd):
    print(f"\n>>> {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=REPO_DIR)
    out = (result.stdout + result.stderr).strip()
    print(out)
    return result.returncode, out

lines = []

def log(msg):
    print(msg)
    lines.append(msg)

# 1. Check current state
rc, out = run("git remote -v")
log(f"REMOTES:\n{out}")

rc, out = run("git branch")
log(f"BRANCHES:\n{out}")

rc, out = run("git log --oneline -3")
log(f"RECENT COMMITS:\n{out}")

# 2. Set remote (remove if already exists to avoid error)
run("git remote remove origin")
rc, out = run("git remote add origin https://github.com/subodhu21/aks-copilot.git")
log(f"ADD REMOTE: rc={rc} {out}")

# 3. Rename branch to main
rc, out = run("git branch -M main")
log(f"BRANCH -M main: rc={rc} {out}")

# 4. Stage any uncommitted changes (there shouldn't be any but just in case)
rc, out = run("git status --short")
log(f"STATUS: {out}")
if out.strip():
    run("git add -A")
    run('git commit -m "chore: final demo polish — rich Slack notifications, per-deployment healing report"')

# 5. Push
rc, out = run("git push -u origin main")
log(f"PUSH: rc={rc}\n{out}")

if rc == 0:
    log("\n✅ Successfully pushed to https://github.com/subodhu21/aks-copilot.git")
else:
    log(f"\n❌ Push failed (rc={rc}). Check output above.")

# Write to file
with open(LOG_FILE, "w") as f:
    f.write("\n".join(lines))
print(f"\nOutput saved to {LOG_FILE}")
