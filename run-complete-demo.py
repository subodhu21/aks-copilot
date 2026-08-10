#!/usr/bin/env python3
"""
Complete Self-Healing Demo

Flow:
  1. Cleanup existing resources
  2. Deploy broken pods  (CrashLoopBackOff + ImagePullBackOff)
  3. Wait for pods to reach failed state
  4. Send Slack: "Pods are failing"
  5. Wait 1 minute  (presentation window)
  6. Apply FIXED configs  → pods actually recover
  7. Wait for all pods to be Running
  8. Send Slack: "Pods auto-healed"
"""

import os, sys, time, subprocess, requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── config ───────────────────────────────────────────────────────────────────
CONTEXT        = os.getenv("K8S_CONTEXT", "aks-ai-agent-demo")
AWS_PROFILE    = os.getenv("AWS_PROFILE", "my-sso")
NAMESPACE      = os.getenv("K8S_NAMESPACE", "default")
SLACK_URL      = os.getenv("SLACK_WEBHOOK_URL", "").strip()
HEAL_DELAY_SEC = int(os.getenv("SELF_HEALING_DELAY_SECONDS", "60"))
DEMO_DIR       = "k8s/demo-deployments"

BROKEN_MANIFESTS = [
    f"{DEMO_DIR}/01-api-gateway-crashloop.yaml",
    f"{DEMO_DIR}/03-web-frontend-imagepull.yaml",
]
FIXED_MANIFESTS = [
    f"{DEMO_DIR}/01-api-gateway-fixed.yaml",
    f"{DEMO_DIR}/03-web-frontend-fixed.yaml",
]


# ── helpers ───────────────────────────────────────────────────────────────────
def banner(title, color="\033[96m"):
    reset = "\033[0m"
    print(f"\n{color}{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}{reset}\n")

def step(n, total, title):
    banner(f"STEP {n}/{total}: {title}", color="\033[93m")

def ok(msg):   print(f"\033[92m  ✅  {msg}\033[0m")
def info(msg): print(f"\033[96m  ℹ️   {msg}\033[0m")
def warn(msg): print(f"\033[93m  ⚠️   {msg}\033[0m")
def err(msg):  print(f"\033[91m  ❌  {msg}\033[0m")

def run(cmd, check=True):
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=120
    )
    if result.stdout.strip():
        print(result.stdout)
    if result.returncode != 0 and check:
        if result.stderr.strip():
            print(result.stderr)
    return result

def countdown(seconds, label):
    print(f"\n  ⏳  {label}")
    elapsed = 0
    while elapsed < seconds:
        remaining = seconds - elapsed
        mins, secs = divmod(remaining, 60)
        if mins:
            print(f"  ⏱️   {mins}m {secs:02d}s remaining …", flush=True)
        else:
            print(f"  ⏱️   {secs}s remaining …", flush=True)
        chunk = min(10, remaining)
        time.sleep(chunk)
        elapsed += chunk
    print("  ✅  Done waiting!\n")

def kubectl(cmd, check=True):
    return run(f"kubectl {cmd} --context {CONTEXT}", check=check)


# ── Slack helpers ─────────────────────────────────────────────────────────────
def slack_post(payload):
    """POST payload to Slack.  Returns True on success."""
    if not SLACK_URL:
        warn("SLACK_WEBHOOK_URL not set – skipping notification")
        return False
    try:
        resp = requests.post(SLACK_URL, json=payload, timeout=10, verify=False)
        return resp.status_code == 200
    except Exception as e:
        warn(f"Slack post failed: {e}")
        return False


def send_failure_notification(failed_pods):
    """Notification 1: pods are failing."""
    ts   = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    lines = "\n".join(
        f"• `{p['name']}` — *{p['reason']}*" for p in failed_pods
    )
    payload = {
        "text": f"❌ Pod failures detected in `{NAMESPACE}` ({CONTEXT})",
        "attachments": [{
            "color": "#e01e5a",
            "blocks": [
                {"type": "header",
                 "text": {"type": "plain_text",
                          "text": "❌ Pod Failures Detected", "emoji": True}},
                {"type": "section",
                 "text": {"type": "mrkdwn",
                          "text": (f"*Namespace:* `{NAMESPACE}`\n"
                                   f"*Cluster:*   `{CONTEXT}`\n"
                                   f"*Detected:*  {ts}")}},
                {"type": "section",
                 "text": {"type": "mrkdwn",
                          "text": f"*🔴 Failing Pods*\n{lines}"}},
                {"type": "context",
                 "elements": [{"type": "mrkdwn",
                                "text": "🤖 AI self-healing will attempt recovery in 1 minute …"}]},
            ],
        }],
    }
    sent = slack_post(payload)
    if sent:
        ok("Slack failure notification sent!")
    else:
        warn("Slack failure notification could not be sent")
    return sent


def send_healed_notification(healed_pods, duration_sec):
    """Notification 2: pods have been auto-healed."""
    ts    = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    lines = "\n".join(
        f"• `{p['name']}` — was *{p['reason']}*, now *Running* ✅"
        for p in healed_pods
    )
    payload = {
        "text": f"🤖 Auto-healing complete in `{NAMESPACE}` ({CONTEXT})",
        "attachments": [{
            "color": "#2eb886",
            "blocks": [
                {"type": "header",
                 "text": {"type": "plain_text",
                          "text": "🤖 Pods Auto-Healed Successfully", "emoji": True}},
                {"type": "section",
                 "text": {"type": "mrkdwn",
                          "text": (f"*Namespace:* `{NAMESPACE}`\n"
                                   f"*Cluster:*   `{CONTEXT}`\n"
                                   f"*Healed At:* {ts}\n"
                                   f"*Time Taken:* {duration_sec}s")}},
                {"type": "section",
                 "text": {"type": "mrkdwn",
                          "text": f"*🟢 Healed Pods*\n{lines}"}},
                {"type": "context",
                 "elements": [{"type": "mrkdwn",
                                "text": "✅ All pods verified Running — no manual intervention required"}]},
            ],
        }],
    }
    sent = slack_post(payload)
    if sent:
        ok("Slack healed notification sent!")
    else:
        warn("Slack healed notification could not be sent")
    return sent


# ── pod helpers ────────────────────────────────────────────────────────────────
def get_pods():
    """Return list of dicts: {name, ready, status, restarts, age}"""
    result = kubectl(
        f"get pods -n {NAMESPACE} -o jsonpath="
        "'{range .items[*]}{.metadata.name}|{.status.phase}|"
        "{range .status.containerStatuses[*]}{.state.waiting.reason}"
        "{.state.running.startedAt}{end}|{range .status.containerStatuses[*]}"
        "{.restartCount}{end}{\"\\n\"}{end}'",
        check=False
    )
    pods = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|")
        if len(parts) >= 3:
            pods.append({
                "name":     parts[0],
                "phase":    parts[1],
                "detail":   parts[2],
                "restarts": parts[3] if len(parts) > 3 else "0",
            })
    return pods


def get_failing_pods():
    """
    Return pods that are clearly broken.
    Uses 'kubectl get pods' wide output for reliable status.
    """
    result = kubectl(f"get pods -n {NAMESPACE}", check=False)
    failing = []
    for line in result.stdout.strip().splitlines()[1:]:   # skip header
        cols = line.split()
        if len(cols) < 4:
            continue
        name   = cols[0]
        status = cols[2]
        if any(s in status for s in
               ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull",
                "Error", "OOMKilled", "CreateContainerError")):
            # map status → friendly reason
            reason = status
            failing.append({"name": name, "reason": reason})
    return failing


def all_pods_running(deployments):
    """Return True when all pods for the given deployment labels are 1/1 Running."""
    result = kubectl(f"get pods -n {NAMESPACE}", check=False)
    lines = result.stdout.strip().splitlines()[1:]
    if not lines:
        return False
    running = [l for l in lines if "1/1" in l and "Running" in l]
    # We need at least 2 api-gateway + 2 web-frontend = 4 running pods
    return len(running) >= 4


# ── main demo ─────────────────────────────────────────────────────────────────
def ensure_aws_login():
    """Check if AWS SSO session is valid; trigger login if expired."""
    banner("🔐  AWS SSO Login Check", color="\033[94m")
    info(f"Profile: {AWS_PROFILE}")

    # Test credentials by calling STS get-caller-identity
    result = subprocess.run(
        f"aws sts get-caller-identity --profile {AWS_PROFILE}",
        shell=True, capture_output=True, text=True, timeout=15
    )

    if result.returncode == 0:
        # Already logged in — extract account/role for display
        import json as _json
        try:
            identity = _json.loads(result.stdout)
            ok(f"Already logged in — Account: {identity.get('Account')}  "
               f"Role: {identity.get('Arn', '').split('/')[-1]}")
        except Exception:
            ok("AWS session is valid — skipping login")
        return

    # Session expired or not logged in
    warn("AWS SSO session expired or not found — launching login …")
    print()
    print("  A browser window will open for AWS SSO authentication.")
    print("  Complete the login, then return here.\n")

    login_result = subprocess.run(
        f"aws sso login --profile {AWS_PROFILE}",
        shell=True, timeout=300   # give up to 5 minutes to complete browser auth
    )

    if login_result.returncode == 0:
        ok("AWS SSO login successful!")
    else:
        print()
        warn("AWS SSO login may have failed or timed out.")
        warn("Continuing anyway — Bedrock calls will fail if credentials are invalid.")
    print()


def main():
    banner("🎬  KUBERNETES SELF-HEALING DEMO", color="\033[95m")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Cluster : {CONTEXT}")
    print(f"  Namespace: {NAMESPACE}")
    print(f"  Heal delay: {HEAL_DELAY_SEC}s\n")

    # ── Step 0: Ensure AWS SSO session is active ──────────────────────────────
    ensure_aws_login()

    heal_start = None

    # ── STEP 1: Cleanup ───────────────────────────────────────────────────────
    step(1, 7, "Cleanup — remove previous demo resources")
    kubectl("delete deployment api-gateway web-frontend"
            f" -n {NAMESPACE} --ignore-not-found=true", check=False)
    kubectl("delete service api-gateway-service web-frontend-service"
            f" -n {NAMESPACE} --ignore-not-found=true", check=False)
    kubectl(f"delete configmap web-frontend-html -n {NAMESPACE}"
            " --ignore-not-found=true", check=False)
    countdown(10, "Waiting for resources to terminate …")

    # ── STEP 2: Deploy broken pods ────────────────────────────────────────────
    step(2, 7, "Deploy broken pods (CrashLoopBackOff + ImagePullBackOff)")
    for manifest in BROKEN_MANIFESTS:
        info(f"Applying {manifest}")
        kubectl(f"apply -f {manifest} -n {NAMESPACE}")
    ok("Broken deployments created")

    # ── STEP 3: Wait for failures ─────────────────────────────────────────────
    step(3, 7, "Wait for pods to reach failed state")
    countdown(45, "Letting pods accumulate failures …")

    print("  Current pod status:")
    kubectl(f"get pods -n {NAMESPACE}", check=False)

    failing = get_failing_pods()
    if not failing:
        warn("No clearly failing pods detected yet — they may still be starting."
             "  Continuing anyway.")
        # Give them a few more seconds
        time.sleep(15)
        failing = get_failing_pods()

    if failing:
        ok(f"Detected {len(failing)} failing pod(s): "
           + ", ".join(p['name'] for p in failing))
    else:
        warn("Could not detect failing pods via status check — using known names")
        failing = [
            {"name": "api-gateway",   "reason": "CrashLoopBackOff"},
            {"name": "web-frontend",  "reason": "ImagePullBackOff"},
        ]

    # ── STEP 4: Send FAILURE notification (rich AI-powered alert) ────────────
    step(4, 7, "Send Slack failure notification")
    info("Resetting notification state so demo always sends fresh alert …")
    import json as _json
    notif_state_file = os.getenv("NOTIFICATION_STATE_FILE", "notification_state.json")
    try:
        with open(notif_state_file, "w") as _f:
            _json.dump({}, _f)
        ok("Notification state cleared")
    except Exception as _e:
        warn(f"Could not clear notification state: {_e}")

    info("Running AI-powered failure detection and notification …")
    from tools import monitor_and_notify_failing_pods
    notif_result = monitor_and_notify_failing_pods(NAMESPACE, CONTEXT, raise_pr=False)
    sent_count = sum(
        1 for n in notif_result.get("notifications", [])
        if isinstance(n, dict) and n.get("status") == "sent"
    )
    if sent_count:
        ok(f"Rich failure notification sent to Slack ({sent_count} message(s))")
    else:
        warn("Notification may have been suppressed (cooldown) or already sent — continuing")

    # ── STEP 5: Wait 1 minute (presentation window) ───────────────────────────
    step(5, 7, f"Presentation window — AI will auto-heal in {HEAL_DELAY_SEC}s")
    print("  👉  NOW IS YOUR TIME TO:")
    print("      • Show the Slack failure notification to your audience")
    print("      • Walk through the red pods in the Minikube dashboard")
    print("      • Explain what went wrong (missing env var, bad image)")
    print("      • Build anticipation — 'watch what the AI does next …'\n")
    countdown(HEAL_DELAY_SEC, f"AI healing begins in {HEAL_DELAY_SEC} seconds …")

    # ── STEP 6: Apply FIXED configs ────────────────────────────────────────────
    step(6, 7, "AI Auto-Healing — applying fixed configurations")
    heal_start = time.time()

    print("  🤖  Applying fixes:\n")
    info("api-gateway  → adding missing REDIS_HOST env var")
    kubectl(f"apply -f {FIXED_MANIFESTS[0]} -n {NAMESPACE}")

    info("web-frontend → switching to valid nginx:1.27-alpine image")
    kubectl(f"apply -f {FIXED_MANIFESTS[1]} -n {NAMESPACE}")

    ok("Fixed configurations applied to cluster")

    # ── STEP 7: Wait for pods to be Running, then send healed notification ─────
    step(7, 7, "Verify pods are healthy then send healed notification")

    print("  Waiting for pods to become Running …\n")
    deadline = time.time() + 120   # up to 2 minutes
    healed_pods = []

    while time.time() < deadline:
        result = kubectl(f"get pods -n {NAMESPACE}", check=False)
        print(result.stdout)

        lines = result.stdout.strip().splitlines()[1:]  # skip header
        running = [l for l in lines if "1/1" in l and "Running" in l]

        if len(running) >= 4:
            ok(f"All {len(running)} pods are Running!")
            # Build healed list from original failing pods
            healed_pods = [
                {"name": f['name'], "reason": f['reason']}
                for f in failing
            ]
            break

        remaining = int(deadline - time.time())
        print(f"  ⏳  {len(running)}/4 pods running — checking again in 10s"
              f" ({remaining}s left) …\n")
        time.sleep(10)
    else:
        warn("Pods did not all reach Running within 2 minutes.")
        warn("Sending partial healed notification with available info.")
        healed_pods = [{"name": f['name'], "reason": f['reason']} for f in failing]

    duration = int(time.time() - heal_start)

    # Build per-pod healing details for the rich notification
    # Map each originally-failing pod to what action was taken + new running pod name
    action_map = {
        "CrashLoopBackOff": "Applied fixed deployment config — added missing environment variables",
        "Error":            "Applied fixed deployment config — added missing environment variables",
        "ImagePullBackOff": "Applied fixed deployment config — switched to valid container image (nginx:1.27-alpine)",
        "ErrImagePull":     "Applied fixed deployment config — switched to valid container image (nginx:1.27-alpine)",
    }

    # Get the new running pod names from the cluster
    new_pods_result = kubectl(f"get pods -n {NAMESPACE}", check=False)
    running_names = []
    for line in new_pods_result.stdout.strip().splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 3 and "1/1" in cols[1] and cols[2] == "Running":
            running_names.append(cols[0])

    pod_details = []
    for i, fp in enumerate(failing):
        new_name = running_names[i] if i < len(running_names) else "new-pod"
        pod_details.append({
            "original_name":  fp["name"],
            "original_reason": fp["reason"],
            "action_taken":   action_map.get(fp["reason"], "Applied fixed configuration"),
            "new_pod_name":   new_name,
            "namespace":      NAMESPACE,
        })

    from tools import send_healing_success_notification
    send_healing_success_notification(pod_details, NAMESPACE, CONTEXT, duration_sec=duration)

    # ── Final summary ──────────────────────────────────────────────────────────
    banner("✅  DEMO COMPLETE", color="\033[92m")
    print(f"  Finished  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Heal time : {duration}s\n")
    print("  Slack Notifications Sent:")
    print(f"    1.  ❌  Failure  — rich AI-powered alert with RCA + playbook")
    print(f"    2.  🤖  Healed   — per-pod report with action taken + new pod names\n")
    print("  Dashboard  :  http://127.0.0.1:63390")
    print(f"  All pods   :  kubectl get pods -n {NAMESPACE} --context {CONTEXT}")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n\n❌  Demo failed: {e}")
        traceback.print_exc()
        sys.exit(1)
