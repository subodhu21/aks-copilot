import subprocess
import json
import os
import time
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from keyvault_loader import resolve_keyvault_refs
from aws_secrets_loader import resolve_aws_secret_refs

load_dotenv()
resolve_keyvault_refs()
resolve_aws_secret_refs()


# ---------------------------------------------------------------------------
# Notification deduplication state
# ---------------------------------------------------------------------------
# State file path — override with NOTIFICATION_STATE_FILE env var.
# Defaults to notification_state.json next to this script.
_DEFAULT_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notification_state.json")
NOTIFICATION_STATE_FILE = os.getenv("NOTIFICATION_STATE_FILE", _DEFAULT_STATE_FILE)

# How long (seconds) to suppress re-notifications for the same pod+reason.
# Default: 1 hour. Override with NOTIFICATION_COOLDOWN_SECONDS env var.
NOTIFICATION_COOLDOWN_SECONDS = int(os.getenv("NOTIFICATION_COOLDOWN_SECONDS", "3600"))

# Which channel(s) to notify: "slack", "teams", or "both". Default: "both".
NOTIFICATION_PROVIDER = os.getenv("NOTIFICATION_PROVIDER", "both").strip().lower()
_NOTIFY_TEAMS = NOTIFICATION_PROVIDER in ("teams", "both")
_NOTIFY_SLACK = NOTIFICATION_PROVIDER in ("slack", "both")

# ---------------------------------------------------------------------------
# Application-level log error scanning (Running pods)
# ---------------------------------------------------------------------------
# Enable scanning of healthy/Running pods for app-level errors in logs.
LOG_ERROR_SCAN_ENABLED = os.getenv("LOG_ERROR_SCAN_ENABLED", "true").lower() == "true"

# Minimum number of matching error lines required to raise an alert.
# Prevents noise from single transient log lines.
LOG_ERROR_THRESHOLD = int(os.getenv("LOG_ERROR_THRESHOLD", "3"))

# How many recent log lines to scan per pod.
LOG_TAIL_LINES = int(os.getenv("LOG_TAIL_LINES", "200"))

# Comma-separated keywords to match in log lines (case-insensitive).
_DEFAULT_ERROR_KEYWORDS = (
    "error,exception,fatal,critical,unhandled,stacktrace,"
    "nullreferenceexception,nullpointerexception,"
    "sqlexception,dbexception,connectionrefused,"
    "timeout,unauthorized,forbidden,HTTP 500,HTTP 503"
)
LOG_ERROR_KEYWORDS = [
    k.strip().lower()
    for k in os.getenv("LOG_ERROR_KEYWORDS", _DEFAULT_ERROR_KEYWORDS).split(",")
    if k.strip()
]


def _load_notification_state() -> dict:
    """Load persisted notification timestamps from disk."""
    try:
        with open(NOTIFICATION_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_notification_state(state: dict) -> None:
    """Persist notification timestamps to disk."""
    with open(NOTIFICATION_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _notification_key(pod_name: str, namespace: str) -> str:
    return f"{namespace}/{pod_name}"


def _should_notify(pod_name: str, namespace: str, state: dict) -> bool:
    """Return True if a notification should be sent (not seen within cooldown).

    Cooldown is tracked per pod (not per pod+reason) — a crash-looping pod can
    be observed with different transient reasons across polls (CrashLoopBackOff,
    Error, HighRestartCount (N) with N changing every run), so keying on the
    exact reason text would falsely treat every reason change as a new issue
    (spamming) or as a recovery (see _find_recovered_pods below).
    """
    entry = state.get(_notification_key(pod_name, namespace))
    if entry is None:
        return True
    last_notified = entry.get("ts") if isinstance(entry, dict) else entry
    if last_notified is None:
        return True
    return (time.time() - last_notified) >= NOTIFICATION_COOLDOWN_SECONDS


def _record_notification(pod_name: str, namespace: str, reason: str, state: dict) -> None:
    """Stamp the current time + latest reason for this pod in the state dict."""
    state[_notification_key(pod_name, namespace)] = {"ts": time.time(), "reason": reason}


def _prune_notification_state(state: dict, active_pods: list) -> dict:
    """Drop state entries for pods that are no longer failing (they recovered)."""
    active_keys = {
        _notification_key(p["pod_name"], p["namespace"])
        for p in active_pods
    }
    return {k: v for k, v in state.items() if k in active_keys}


def _find_recovered_pods(state: dict, active_pods: list) -> list:
    """Return pods that were previously notified (present in state) but are no
    longer in the active failing_pods list — i.e. they have recovered."""
    active_keys = {
        _notification_key(p["pod_name"], p["namespace"])
        for p in active_pods
    }
    recovered = []
    for key, entry in state.items():
        if key in active_keys:
            continue
        parts = key.split("/", 1)
        if len(parts) == 2:
            namespace, pod_name = parts
            last_reason = entry.get("reason", "Unknown") if isinstance(entry, dict) else "Unknown"
            recovered.append({"pod_name": pod_name, "namespace": namespace, "reason": last_reason})
    return recovered


def _deployment_key(pod_name: str) -> str:
    """Best-effort deployment name from a pod name (strip replicaset+pod hash suffix)."""
    parts = pod_name.split("-")
    return "-".join(parts[:-2]) if len(parts) > 2 else pod_name


def _group_pods_by_deployment(pods: list) -> dict:
    """Group pods by namespace/deployment so multiple pods failing for the same
    root cause produce one consolidated Teams notification instead of one per pod."""
    groups: dict = {}
    for pod in pods:
        key = f'{pod["namespace"]}/{_deployment_key(pod["pod_name"])}'
        groups.setdefault(key, []).append(pod)
    return groups


# ---------------------------------------------------------------------------


def _with_context(cmd, k8s_context=None):
    """Inject --context into kubectl commands when provided."""
    if not k8s_context:
        return cmd
    if cmd.strip().startswith("kubectl "):
        return cmd.replace("kubectl ", f"kubectl --context {k8s_context} ", 1)
    return cmd


def run_cmd(cmd, k8s_context=None, timeout=30):
    """Execute a shell command and return output. Defaults to 30s timeout."""
    try:
        full_cmd = _with_context(cmd, k8s_context)
        result = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s: {cmd}"
    except Exception as e:
        return f"Error executing command: {str(e)}"


def get_pod_logs(pod, namespace, k8s_context=None):
    """Get pod logs (last 50 lines)"""
    return run_cmd(f"kubectl logs {pod} -n {namespace} --tail=50", k8s_context)


def describe_pod(pod, namespace, k8s_context=None):
    """Get detailed pod description"""
    return run_cmd(f"kubectl describe pod {pod} -n {namespace}", k8s_context)


def summarize_description(description, max_lines=40):
    """Keep the most relevant parts of kubectl describe output for AI analysis."""
    lines = [line.rstrip() for line in description.splitlines() if line.strip()]
    important_prefixes = (
        "Name:",
        "Namespace:",
        "Node:",
        "Status:",
        "IP:",
        "Controlled By:",
        "Containers:",
        "State:",
        "Last State:",
        "Ready:",
        "Restart Count:",
        "Limits:",
        "Requests:",
        "Liveness:",
        "Readiness:",
        "Startup:",
        "Environment:",
        "Mounts:",
        "Conditions:",
        "Events:",
        "Reason:",
        "Message:",
    )

    selected = [line for line in lines if line.startswith(important_prefixes)]
    if not selected:
        selected = lines[:max_lines]

    return "\n".join(selected[:max_lines])


def detect_issue(description):
    """Detect obvious issues from pod description with fewer false positives."""
    desc = description.lower()

    if "crashloopbackoff" in desc:
        return "CrashLoopBackOff"
    if "oomkilled" in desc:
        return "OOMKilled"
    if "imagepullbackoff" in desc or "errimagepull" in desc:
        return "ImagePullBackOff"
    if "status:" in desc and "pending" in desc:
        return "Pending"
    if "liveness probe failed" in desc or ("unhealthy" in desc and "liveness" in desc):
        return "Liveness Probe Failure"
    if "status:" in desc and "running" in desc and "events:                      <none>" in description:
        return "No Issue Detected"
    return "Unknown"


def get_pods_json(namespace, k8s_context=None):
    """Return raw pod json for a namespace."""
    output = run_cmd(f"kubectl get pods -n {namespace} -o json", k8s_context)
    try:
        return json.loads(output)
    except Exception:
        return {"items": [], "raw_output": output}


def get_pod_runtime_signals(pod, namespace, k8s_context=None):
    """Return runtime signals to reduce ambiguity when pods flap between states."""
    output = run_cmd(f"kubectl get pod {pod} -n {namespace} -o json", k8s_context)
    try:
        data = json.loads(output)
    except Exception:
        return {
            "phase": None,
            "ready": None,
            "restart_count": None,
            "waiting_reason": None,
            "node": None,
        }

    status = data.get("status", {})
    spec = data.get("spec", {})
    container_statuses = status.get("containerStatuses", []) or []

    restart_count = 0
    waiting_reason = None
    ready = True if container_statuses else None

    for container in container_statuses:
        restart_count += container.get("restartCount", 0)
        if container.get("ready") is False:
            ready = False
        state = container.get("state", {})
        waiting = state.get("waiting", {})
        if waiting and waiting.get("reason") and not waiting_reason:
            waiting_reason = waiting.get("reason")

    return {
        "phase": status.get("phase"),
        "ready": ready,
        "restart_count": restart_count,
        "waiting_reason": waiting_reason,
        "node": spec.get("nodeName"),
    }


def list_k8s_contexts():
    """Return available kube contexts and current context."""
    contexts_output = run_cmd("kubectl config get-contexts -o name")
    current_output = run_cmd("kubectl config current-context")
    
    contexts = [line.strip() for line in contexts_output.splitlines() if line.strip()]
    current = current_output.strip().splitlines()[0] if current_output.strip() else None
    
    return {
        "contexts": contexts,
        "current_context": current,
    }


def list_namespaces(k8s_context=None):
    """Return available namespaces for the selected context."""
    output = run_cmd("kubectl get namespaces -o json", k8s_context)
    try:
        data = json.loads(output)
        namespaces = [item.get("metadata", {}).get("name") for item in data.get("items", [])]
        namespaces = [name for name in namespaces if name]
        return {
            "k8s_context": k8s_context,
            "namespaces": namespaces,
        }
    except Exception:
        return {
            "k8s_context": k8s_context,
            "namespaces": [],
            "error": output,
        }


def get_namespace_health_snapshot(namespace="default", k8s_context=None):
    """Build a lightweight operational summary for namespace health."""
    data = get_pods_json(namespace, k8s_context)
    items = data.get("items", []) if isinstance(data, dict) else []

    total = len(items)
    running = 0
    failing = 0
    pending = 0
    restart_heavy = 0
    problematic_pods = []

    for pod in items:
        metadata = pod.get("metadata", {})
        status = pod.get("status", {})
        pod_name = metadata.get("name", "unknown")
        phase = status.get("phase", "Unknown")
        container_statuses = status.get("containerStatuses", []) or []

        restart_count = 0
        waiting_reason = None
        for c in container_statuses:
            restart_count += c.get("restartCount", 0)
            state = c.get("state", {})
            waiting = state.get("waiting", {})
            if waiting and waiting.get("reason"):
                waiting_reason = waiting.get("reason")

        if phase == "Running":
            running += 1
        if phase == "Pending":
            pending += 1
        if restart_count >= 3:
            restart_heavy += 1

        is_problematic = phase not in ("Running", "Succeeded") or restart_count >= 3 or waiting_reason
        if is_problematic:
            failing += 1
            problematic_pods.append(
                {
                    "pod": pod_name,
                    "phase": phase,
                    "waiting_reason": waiting_reason,
                    "restart_count": restart_count,
                }
            )

    events_raw = run_cmd(
        f"kubectl get events -n {namespace} --sort-by=.lastTimestamp --field-selector type=Warning",
        k8s_context,
    )
    events_lines = [line for line in events_raw.splitlines() if line.strip()]
    recent_warnings = events_lines[-8:] if len(events_lines) > 8 else events_lines

    return {
        "namespace": namespace,
        "k8s_context": k8s_context,
        "total_pods": total,
        "running_pods": running,
        "pending_pods": pending,
        "problematic_pod_count": failing,
        "high_restart_pod_count": restart_heavy,
        "problematic_pods": problematic_pods,
        "recent_warning_events": recent_warnings,
    }


def infer_workload_name_from_description(description):
    """Best-effort inference of deployment name from pod description."""
    for line in description.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("Controlled By:"):
            value = cleaned.split("Controlled By:", 1)[1].strip()
            if value.startswith("ReplicaSet/"):
                rs_name = value.split("ReplicaSet/", 1)[1]
                # Common ReplicaSet naming pattern: deployment-<pod-template-hash>
                parts = rs_name.rsplit("-", 1)
                return parts[0] if len(parts) == 2 else rs_name
    return None


def build_remediation_plan(pod, namespace, issue_type, description, k8s_context=None):
    """Create a deterministic remediation plan with safe commands."""
    workload = infer_workload_name_from_description(description)
    runtime = get_pod_runtime_signals(pod, namespace, k8s_context)
    restart_count = runtime.get("restart_count") or 0
    waiting_reason = runtime.get("waiting_reason")

    # Suppress restart churn when pod is already flapping heavily.
    suppress_restart = bool(restart_count >= 10 or waiting_reason == "CrashLoopBackOff")

    safe_commands = [
        f"kubectl describe pod {pod} -n {namespace}",
        f"kubectl logs {pod} -n {namespace} --tail=100 --previous",
    ]

    if issue_type == "CrashLoopBackOff":
        safe_commands.append(f"kubectl get events -n {namespace} --sort-by=.lastTimestamp")
        if workload and not suppress_restart:
            safe_commands.append(f"kubectl rollout restart deployment/{workload} -n {namespace}")

        # Prefer deeper read-only diagnostics when restart loops are already severe.
        if suppress_restart:
            if workload:
                safe_commands.append(f"kubectl get deploy {workload} -n {namespace} -o yaml")
            safe_commands.append(f"kubectl get secret -n {namespace}")
            if "webhook" in (workload or "") or "webhook" in pod:
                safe_commands.append("kubectl get mutatingwebhookconfiguration,validatingwebhookconfiguration")
    elif issue_type == "OOMKilled":
        safe_commands.append(f"kubectl top pod {pod} -n {namespace}")
    elif issue_type == "ImagePullBackOff":
        safe_commands.append(f"kubectl get pod {pod} -n {namespace} -o yaml")
    elif issue_type == "Pending":
        safe_commands.append(f"kubectl describe nodes")
    elif issue_type == "Liveness Probe Failure":
        safe_commands.append(f"kubectl logs {pod} -n {namespace} --tail=100")

    return {
        "pod": pod,
        "namespace": namespace,
        "k8s_context": k8s_context,
        "issue_type": issue_type,
        "workload": workload,
        "runtime_signals": runtime,
        "restart_suppressed": suppress_restart,
        "commands": safe_commands,
        "auto_apply_supported": True,
    }


def execute_safe_remediation_commands(commands, k8s_context=None):
    """Execute commands with strict allowlist to avoid destructive operations."""
    allowed_prefixes = (
        "kubectl describe pod ",
        "kubectl logs ",
        "kubectl get events ",
        "kubectl top pod ",
        "kubectl get pod ",
        "kubectl get deploy ",
        "kubectl get secret ",
        "kubectl get mutatingwebhookconfiguration,validatingwebhookconfiguration",
        "kubectl describe nodes",
        "kubectl rollout restart deployment/",
    )

    results = []
    for command in commands:
        if not command.startswith(allowed_prefixes):
            results.append(
                {
                    "command": command,
                    "status": "blocked",
                    "output": "Command blocked by safety policy.",
                }
            )
            continue

        output = run_cmd(command, k8s_context)
        results.append(
            {
                "command": command,
                "status": "executed",
                "output": output[:2000],
            }
        )

    return results


# Per-pod log scan timeout in seconds — prevents slow pods from stalling the whole run.
LOG_SCAN_TIMEOUT = int(os.getenv("LOG_SCAN_TIMEOUT", "10"))


def _scan_running_pod_for_app_errors(pod_name, namespace, k8s_context=None):
    """
    Scan logs of a Running pod for application-level error patterns.

    Returns a dict with 'has_error', 'error_lines', and 'logs_snippet',
    or None if scanning is disabled or logs are unavailable.
    """
    if not LOG_ERROR_SCAN_ENABLED:
        return None

    logs = run_cmd(
        f"kubectl logs {pod_name} -n {namespace} --tail={LOG_TAIL_LINES} --all-containers=false",
        k8s_context,
        timeout=LOG_SCAN_TIMEOUT,
    )
    if not logs or logs.strip().startswith("Error"):
        return None

    import re
    _NEW_ENTRY = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}')

    all_lines = logs.splitlines()
    error_blocks = []
    i = 0
    while i < len(all_lines):
        line = all_lines[i]
        if any(kw in line.lower() for kw in LOG_ERROR_KEYWORDS):
            # Collect this line plus all continuation lines until next timestamped entry
            block = [line]
            i += 1
            while i < len(all_lines):
                next_line = all_lines[i]
                if _NEW_ENTRY.match(next_line):
                    break
                block.append(next_line)
                i += 1
            error_blocks.append("\n".join(block))
        else:
            i += 1

    # error_lines kept as flat list for threshold count compatibility
    error_lines = [b.splitlines()[0] for b in error_blocks]

    if len(error_lines) < LOG_ERROR_THRESHOLD:
        return None

    return {
        "has_error": True,
        "error_lines": error_lines,
        "logs_snippet": "\n\n".join(error_blocks[:10]),
    }


def detect_failing_pods(namespace="default", k8s_context=None):
    """
    Detect pods with major impact issues that need immediate attention.
    
    Major impact issues include:
    - CrashLoopBackOff
    - OOMKilled
    - ImagePullBackOff
    - Failed phase
    - High restart count (>= 3)
    - Pending for too long
    """
    pods_result = get_pods_json(namespace, k8s_context)
    items = pods_result.get("items", []) if isinstance(pods_result, dict) else []
    
    failing_pods = []
    
    for pod in items:
        metadata = pod.get("metadata", {})
        status = pod.get("status", {})
        
        pod_name = metadata.get("name", "unknown")
        pod_namespace = metadata.get("namespace", namespace)
        phase = status.get("phase", "Unknown")
        container_statuses = status.get("containerStatuses", []) or []
        
        # Check for critical states
        has_major_issue = False
        issue_reason = None
        logs_snippet = ""
        
        # Phase-based detection
        if phase == "Failed":
            has_major_issue = True
            issue_reason = "Failed"
        elif phase == "CrashLoopBackOff":
            has_major_issue = True
            issue_reason = "CrashLoopBackOff"
        elif phase == "Unknown":
            has_major_issue = True
            issue_reason = "Unknown"
        
        # Container status detection
        restart_count = 0
        for container in container_statuses:
            restart_count += container.get("restartCount", 0)
            state = container.get("state", {})
            
            # Check for waiting state with failure reasons
            waiting = state.get("waiting", {})
            if waiting:
                reason = waiting.get("reason", "")
                if reason in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "ImageInspectError"]:
                    has_major_issue = True
                    issue_reason = reason
            
            # Check for terminated state with failure
            terminated = state.get("terminated", {})
            if terminated:
                reason = terminated.get("reason", "")
                if reason in ["OOMKilled", "Error"]:
                    has_major_issue = True
                    issue_reason = reason
        
        # Check for excessive restarts (major performance impact)
        if restart_count >= 3 and not has_major_issue:
            has_major_issue = True
            issue_reason = f"HighRestartCount ({restart_count})"
        
        # Check for pending pods (potential scheduling/resource issues)
        # Only use "Pending" as reason if no more specific container-level reason was found
        if phase == "Pending" and not has_major_issue:
            has_major_issue = True
            issue_reason = "Pending"
        
        # If pod has major issue, get error logs (app container only, not sidecars)
        if has_major_issue:
            # Always try previous logs first for restart/crash scenarios — they contain the crash reason
            logs_previous = run_cmd(f"kubectl logs {pod_name} -n {pod_namespace} --tail=100 --previous --all-containers=false", k8s_context)
            logs_current  = run_cmd(f"kubectl logs {pod_name} -n {pod_namespace} --tail=100 --all-containers=false", k8s_context)

            # Combine both — previous contains the crash; current may have startup errors
            # Deduplicate: if previous and current are identical, use one copy
            if logs_previous.strip() and logs_current.strip() and logs_previous.strip() == logs_current.strip():
                combined = logs_previous.strip()
            else:
                combined = "\n".join(filter(None, [logs_previous, logs_current]))
            logs_output = combined if combined.strip() else "No logs available"

            # Strategy 1: Extract "Caused by:" chain (Java/Spring stack traces)
            all_lines = logs_output.split("\n")
            caused_by_blocks = []
            i = 0
            while i < len(all_lines):
                line = all_lines[i]
                if line.strip().startswith("Caused by:"):
                    block = [line.strip()]
                    i += 1
                    at_count = 0
                    while i < len(all_lines) and at_count < 3:
                        nl = all_lines[i].strip()
                        if nl.startswith("at ") or nl.startswith("... "):
                            block.append(nl)
                            at_count += 1
                            i += 1
                        else:
                            break
                    caused_by_blocks.append("\n".join(block))
                else:
                    i += 1

            if caused_by_blocks:
                # Use last 3 Caused-by entries (innermost = root cause)
                logs_snippet = "\n\n".join(caused_by_blocks[-3:])
            else:
                # Strategy 2: keyword-based filtering for non-Java logs
                error_lines = [line for line in all_lines
                               if any(kw in line.lower() for kw in [
                                   "error", "exception", "failed", "fail:", "null", "crash",
                                   "keyvault", "secret", "unauthorized", "forbidden",
                                   "connection", "timeout", "refused", "notfound", "404", "500"
                               ])]
                logs_snippet = "\n".join(error_lines[:20]) if error_lines else logs_output[:500]
            
            failing_pods.append({
                "pod_name": pod_name,
                "namespace": pod_namespace,
                "status": phase,
                "reason": issue_reason,
                "restart_count": restart_count,
                "error_logs": logs_snippet,
                "k8s_context": k8s_context,
            })

    # ── Second pass: scan Running pods for application-level log errors ──────
    # These pods look healthy to K8s but may have exceptions/failures in logs.
    # Runs in parallel (up to LOG_SCAN_WORKERS threads) to keep total time low.
    already_flagged = {p["pod_name"] for p in failing_pods}
    if LOG_ERROR_SCAN_ENABLED:
        candidates = [
            (pod.get("metadata", {}).get("name", "unknown"),
             pod.get("metadata", {}).get("namespace", namespace),
             pod.get("status", {}).get("phase", "Unknown"))
            for pod in items
        ]
        candidates = [
            (pn, pns, ph) for pn, pns, ph in candidates
            if pn not in already_flagged and ph == "Running"
        ]

        LOG_SCAN_WORKERS = int(os.getenv("LOG_SCAN_WORKERS", "10"))
        with ThreadPoolExecutor(max_workers=LOG_SCAN_WORKERS) as executor:
            futures = {
                executor.submit(_scan_running_pod_for_app_errors, pn, pns, k8s_context): (pn, pns)
                for pn, pns, _ in candidates
            }
            for future in as_completed(futures):
                pn, pns = futures[future]
                try:
                    scan = future.result()
                except Exception:
                    scan = None
                if scan:
                    failing_pods.append({
                        "pod_name": pn,
                        "namespace": pns,
                        "status": "Running",
                        "reason": f"AppError ({len(scan['error_lines'])} error lines in logs)",
                        "restart_count": 0,
                        "error_logs": scan["logs_snippet"],
                        "k8s_context": k8s_context,
                    })

    return {
        "namespace": namespace,
        "k8s_context": k8s_context,
        "failing_pods_count": len(failing_pods),
        "failing_pods": failing_pods,
    }


def _classify_issue(reason, error_logs, is_repo_managed):
    """
    Classify the root cause into a human-readable category with emoji.
    Returns (category_label, action_owner).
    """
    logs_lower = error_logs.lower()

    if reason in ["ImagePullBackOff", "ErrImagePull", "ImageInspectError"]:
        return "🐳 Image / Deploy Issue", "DevOps / Release team"

    if reason == "OOMKilled" or "oomkilled" in logs_lower:
        return "📈 Resource Limit (OOMKilled)", "Helm repo — increase memory limits"

    if any(kw in logs_lower for kw in ["keyvault", "key vault", "secretnotfound", "azure.requestfailedexception"]):
        return "🔐 Infrastructure / Secret Missing", "Platform / Ops team (Key Vault)"

    # Config/env-var checks run BEFORE the generic dependency-keyword check below,
    # since a NullPointerException on a null config value (e.g. GatewayProperties
    # .getEnvironment()) is a strong, specific signal that should win even if the
    # surrounding stack trace happens to mention a dependency class/package name
    # (e.g. "com.mongodb...MongoClient") that would otherwise false-match "mongodb".
    if any(kw in logs_lower for kw in ["nullpointerexception", "cannot invoke", "getenv", "getenvironment", "getproperty", "missing required", "no value for"]):
        if is_repo_managed:
            return "⚙️ Config Issue — Helm Repo Change Needed", "Dev team — update values in devops repo"
        return "⚙️ Config Issue — Environment Variable Missing", "Platform / Ops team"

    # Require an actual connectivity-failure phrase, not just a bare dependency
    # name (e.g. "mongodb", "sql", "redis" appearing in a class/package name is
    # NOT evidence of an unreachable dependency on its own).
    if any(kw in logs_lower for kw in [
        "connection refused", "connection timeout", "connection timed out",
        "econnrefused", "unable to connect", "could not connect",
        "no route to host", "network is unreachable", "host unreachable",
        "connect timed out",
    ]):
        return "🔌 Infrastructure / Dependency Unreachable", "Platform / Ops team"

    if any(kw in logs_lower for kw in ["unauthorizedaccessexception", "forbidden", "401", "403", "access denied", "permission denied"]):
        return "🔒 Auth / Permission Issue", "Platform / Ops team"

    if any(kw in logs_lower for kw in ["exception", "error", "unhandled", "fatal", "panic", "stacktrace", "traceback"]):
        return "🐛 Application Code Issue", "Dev / Engineering team"

    if reason.startswith("HighRestartCount"):
        return "🔁 Repeated Restarts — Root Cause Unclear", "Dev + Ops team — check logs"

    return "❓ Unknown Issue", "Dev + Ops team"


def _sanitize_markdown_for_teams(text):
    """Remove markdown heading syntax to ensure consistent font sizing in Teams."""
    import re
    # Remove markdown headings (##, ###, ####, etc.) and convert to plain text
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    return text.strip()


def _build_action_guide(issue_category, pod_name, namespace, deployment_name, repo_name, k8s_context, error_logs):
    """Return the appropriate action guide based on issue category."""
    import re

    base = f"\n✨ Full pod info: `kubectl describe pod -n {namespace} {pod_name}`"

    if "Secret Missing" in issue_category or "Key Vault" in issue_category:
        m = re.search(r'name/id\)\s+(\w+)\s+was not found', error_logs)
        secret_name = m.group(1) if m else "<secret-name>"
        return (
            f"**Step 1️⃣ — Identify the Key Vault used by this pod:**\n"
            f"```\nkubectl get pod {pod_name} -n {namespace} -o jsonpath='{{.spec.containers[*].env}}'\n```\n\n"
            f"**Step 2️⃣ — Check if the secret exists:**\n"
            f"```\naz keyvault secret show --name {secret_name} --vault-name <your-keyvault>\n```\n\n"
            f"**Step 3️⃣ — Restore / recreate the secret:**\n"
            f"```\naz keyvault secret set --name {secret_name} --vault-name <your-keyvault> --value <secret-value>\n```\n\n"
            f"**Step 4️⃣ — Verify pod recovers:**\n"
            f"```\nkubectl get pods -n {namespace} -l app={deployment_name}\n```\n\n"
            f"⚠️ Do NOT store secret values in the Helm repo — use Key Vault references only.{base}"
        )

    if "Helm Repo Change" in issue_category or "Config Issue" in issue_category:
        return (
            f"**Step 1️⃣ — Get current deployed values:**\n"
            f"```\nhelm get values {deployment_name} -n {namespace}\n```\n\n"
            f"**Step 2️⃣ — Update the values file in the {repo_name} repo**\n\n"
            f"**Step 3️⃣ — Deploy the fix:**\n"
            f"```\nhelm upgrade {deployment_name} ./helm/{deployment_name} -n {namespace} -f values-{namespace}.yaml\n```\n\n"
            f"**Step 4️⃣ — Monitor recovery:**\n"
            f"```\nkubectl logs -n {namespace} -l app={deployment_name} --tail=50 -f\n```\n\n"
            f"**Step 5️⃣ — Verify pod status:**\n"
            f"```\nkubectl get pods -n {namespace} -l app={deployment_name}\n```{base}"
        )

    if "Resource Limit" in issue_category or "OOMKilled" in issue_category:
        return (
            f"**Step 1️⃣ — Check current resource limits:**\n"
            f"```\nkubectl describe pod {pod_name} -n {namespace} | grep -A5 Limits\n```\n\n"
            f"**Step 2️⃣ — Increase memory in the {repo_name} values file**\n"
            f"File: `./helm/{deployment_name}/values-{namespace}.yaml`\n"
            f"Increase `resources.limits.memory`\n\n"
            f"**Step 3️⃣ — Deploy the fix:**\n"
            f"```\nhelm upgrade {deployment_name} ./helm/{deployment_name} -n {namespace} -f values-{namespace}.yaml\n```{base}"
        )

    if "Image" in issue_category or "Deploy" in issue_category:
        return (
            f"**Step 1️⃣ — Check the image being pulled:**\n"
            f"```\nkubectl describe pod {pod_name} -n {namespace} | grep Image\n```\n\n"
            f"**Step 2️⃣ — Verify the image tag exists in the registry**\n\n"
            f"**Step 3️⃣ — Update the image tag in {repo_name} values file and redeploy:**\n"
            f"```\nhelm upgrade {deployment_name} ./helm/{deployment_name} -n {namespace} -f values-{namespace}.yaml\n```{base}"
        )

    if "Dependency" in issue_category or "Unreachable" in issue_category:
        return (
            f"**Step 1️⃣ — Check pod logs for the failing dependency:**\n"
            f"```\nkubectl logs -n {namespace} {pod_name} --previous --tail=100\n```\n\n"
            f"**Step 2️⃣ — Verify the dependency service is running:**\n"
            f"```\nkubectl get svc -n {namespace}\n```\n\n"
            f"**Step 3️⃣ — Check network policies and DNS resolution from the pod**\n\n"
            f"**Step 4️⃣ — Escalate to Platform / Ops team** if the dependency is external.{base}"
        )

    if "Auth" in issue_category or "Permission" in issue_category:
        return (
            f"**Step 1️⃣ — Check what identity the pod uses:**\n"
            f"```\nkubectl describe pod {pod_name} -n {namespace} | grep -i 'service.account\\|identity'\n```\n\n"
            f"**Step 2️⃣ — Verify RBAC / managed identity permissions in Azure Portal**\n\n"
            f"**Step 3️⃣ — Escalate to Platform / Ops team** to fix IAM/RBAC permissions.{base}"
        )

    if "Application Code" in issue_category:
        return (
            f"**Step 1️⃣ — Get the full stack trace:**\n"
            f"```\nkubectl logs -n {namespace} {pod_name} --previous --tail=200\n```\n\n"
            f"**Step 2️⃣ — Identify the failing class/method and raise a bug ticket**\n\n"
            f"**Step 3️⃣ — Roll back to the previous stable image if needed:**\n"
            f"```\nkubectl rollout undo deployment/{deployment_name} -n {namespace}\n```\n\n"
            f"**Step 4️⃣ — Assign to Dev / Engineering team** for a code fix.{base}"
        )

    # Default / system / unknown
    return (
        f"**Step 1️⃣ — Check logs:**\n"
        f"```\nkubectl logs -n {namespace} {pod_name} --previous --tail=100\n```\n\n"
        f"**Step 2️⃣ — Describe pod:**\n"
        f"```\nkubectl describe pod -n {namespace} {pod_name}\n```\n\n"
        f"**Step 3️⃣ — Restart if safe:**\n"
        f"```\nkubectl rollout restart deployment/{deployment_name} -n {namespace}\n```\n\n"
        f"**Step 4️⃣ — Escalate to platform/infrastructure team** if the issue persists.{base}"
    )


def _build_notification_content(pod_name, namespace, status, reason, error_logs, k8s_context=None, related_pods=None):
    """
    Compute the shared, channel-agnostic notification content (AI explanation,
    AI solution, issue classification, action guide, repo/deployment metadata).

    Kept separate from the channel-specific builders (Teams/Slack) so the AI
    inference call and repo-context lookups only run ONCE per failure even when
    multiple notification channels are configured.
    """
    related_pods = related_pods or []

    # Generate AI explanation and solution
    from agent import analyze_logs
    from helm_config import get_helm_context
    from repo_context import get_repo_context, format_repo_context_for_ai

    ai_explanation = "Unable to generate explanation at this time"
    ai_solution = "Unable to generate solution at this time"

    # Get pod description
    pod_description = describe_pod(pod_name, namespace, k8s_context)

    # Get Helm metadata context (from helm_config.py)
    helm_context = get_helm_context(pod_name, namespace)

    # Get repository context from Azure DevOps (uses correct repo for this k8s context)
    repo_context = get_repo_context(pod_name, namespace, k8s_context=k8s_context)
    repo_context_str = format_repo_context_for_ai(repo_context)

    # Derive deployment name and repo name — always available from here on
    deployment_name = repo_context.get("deployment_name", "-".join(pod_name.split("-")[:-2])) or pod_name.split("-")[0]
    repo_url = repo_context.get("repo_url", "")
    repo_name = repo_url.split("_git/")[-1] if "_git/" in repo_url else os.getenv("AZURE_DEVOPS_REPO", "devops")

    # Detect whether this is a repo-managed deployment or a system/infrastructure pod
    from repo_context import AzureDevOpsRepoLoader
    _loader = AzureDevOpsRepoLoader(k8s_context=k8s_context)
    _values_path = _loader.find_helm_values_path(deployment_name, namespace)
    _values_content = _loader.get_file_content(_values_path)
    is_repo_managed = bool(_values_content and not _values_content.startswith("Error"))

    # Classify the issue for the notification header
    issue_category, action_owner = _classify_issue(reason, error_logs, is_repo_managed)

    try:
        # Get AI explanation of the issue using error logs, Helm context, and repo context
        # Include all deployment details so AI can generate exact Helm-specific fixes
        full_context = f"{pod_description}\n{helm_context}\n{repo_context_str}" if helm_context or repo_context_str else pod_description
        analysis = analyze_logs(error_logs, full_context)
        if isinstance(analysis, dict) and "analysis" in analysis:
            ai_explanation = _sanitize_markdown_for_teams(analysis["analysis"][:1500])
        elif isinstance(analysis, str):
            ai_explanation = _sanitize_markdown_for_teams(analysis[:1500])
    except Exception as e:
        ai_explanation = f"Issue: {reason}. {str(e)[:150]}"

    try:
        # Generate solution text aligned with issue_category so it always matches
        # the Action Guide branch selected below (same category checks/order as
        # _build_action_guide, to avoid mismatched "Helm fix" text on non-Helm issues).
        if "Secret Missing" in issue_category or "Key Vault" in issue_category:
            import re
            secret_match = re.search(r'name/id\)\s+(\w+)\s+was not found', error_logs)
            secret_name = secret_match.group(1) if secret_match else "the missing secret"
            ai_solution = (
                f"Key Vault Secret Missing — `{secret_name}` was not found in the Key Vault.\n"
                f"See the Step-by-Step Action Guide below for the exact commands to verify and restore the secret.\n"
                f"Note: Do NOT store secret values in the Helm repo — use Key Vault references only."
            )
        elif "Helm Repo Change" in issue_category or "Config Issue" in issue_category:
            ai_solution = f"Configuration error in `{deployment_name}` ({repo_name} repo). See the Step-by-Step Action Guide below for the exact Helm fix commands."
        elif "Resource Limit" in issue_category or "OOMKilled" in issue_category:
            ai_solution = f"Resource limit issue (OOMKilled) on `{deployment_name}` ({repo_name} repo). See the Step-by-Step Action Guide below for the exact commands to check usage and raise the memory limit."
        elif "Image" in issue_category or "Deploy" in issue_category:
            ai_solution = f"Image / deployment issue ({reason}) on `{deployment_name}` ({repo_name} repo). See the Step-by-Step Action Guide below for the exact commands to verify and fix the image."
        elif "Dependency" in issue_category or "Unreachable" in issue_category:
            ai_solution = f"Dependency unreachable — `{deployment_name}` cannot reach a required service. See the Step-by-Step Action Guide below to verify connectivity; escalate if the dependency is external."
        elif "Auth" in issue_category or "Permission" in issue_category:
            ai_solution = f"Auth / permission issue on `{deployment_name}` — likely identity/RBAC misconfiguration. See the Step-by-Step Action Guide below and escalate to Platform / Ops."
        elif "Application Code Issue" in issue_category:
            ai_solution = f"Application code issue ({reason}) in `{deployment_name}` — this is an app-level bug, not an infra/config problem. See the Step-by-Step Action Guide below for triage/rollback steps."
        elif not is_repo_managed:
            # System/infrastructure pod — no Helm chart in devops repo
            ai_solution = (
                f"System Pod Issue ({reason}) — this pod is NOT managed by a Helm chart in the devops repo.\n"
                f"See the Step-by-Step Action Guide below for exact diagnostic commands.\n"
                f"Escalate to the platform/infrastructure team if the issue persists."
            )
        else:
            ai_solution = f"Deployment issue ({reason}) in `{deployment_name}` ({repo_name} repo). See the Step-by-Step Action Guide below for the exact fix commands."
    except Exception as e:
        ai_solution = f"Please check pod logs manually: {str(e)[:100]}"

    # Sanitize AI-generated text to ensure consistent font sizing across channels
    ai_solution = _sanitize_markdown_for_teams(ai_solution)
    action_guide = _build_action_guide(issue_category, pod_name, namespace, deployment_name, repo_name, k8s_context, error_logs)

    return {
        "related_pods": related_pods,
        "ai_explanation": ai_explanation,
        "ai_solution": ai_solution,
        "action_guide": action_guide,
        "issue_category": issue_category,
        "action_owner": action_owner,
        "deployment_name": deployment_name,
        "repo_name": repo_name,
        "repo_url": repo_url,
        "is_repo_managed": is_repo_managed,
        "error_summary": error_logs[:1500] if error_logs else "No logs available",
        "timestamp": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
    }


def _convert_markdown_to_slack(text):
    """Convert standard Markdown to Slack mrkdwn syntax.

    Handles:
    - **bold** → *bold*
    - Markdown tables → key: value lines (Slack has no table support)
    - ### headings → *bold* lines
    """
    import re
    if not text:
        return ""

    lines = text.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip standalone horizontal rules (---, ***, ___)
        if re.match(r'^[-*_]{3,}\s*$', stripped):
            i += 1
            continue

        # Detect markdown table: header row with | separators
        if "|" in stripped and stripped.startswith("|") and stripped.endswith("|"):
            # Collect all table rows
            table_rows = []
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                row = lines[i].strip()
                # Skip separator rows like |---|---|  or | :---: | --- |
                cells = [c.strip() for c in row.strip("|").split("|")]
                if all(re.match(r'^[\s\-:]+$', c) for c in cells):
                    i += 1
                    continue
                cells = [c.strip() for c in row.strip("|").split("|")]
                table_rows.append(cells)
                i += 1

            if len(table_rows) >= 2:
                headers = table_rows[0]
                # Check if this is a 2-column key-value table
                is_kv = len(headers) == 2
                for data_row in table_rows[1:]:
                    if is_kv and len(data_row) >= 2:
                        # Render as "Key: Value" — first col is key, second is value
                        key = re.sub(r'\*\*(.+?)\*\*', r'\1', data_row[0])
                        val = re.sub(r'\*\*(.+?)\*\*', r'*\1*', data_row[1])
                        result.append(f"• *{key}:* {val}")
                    else:
                        pairs = []
                        for h, v in zip(headers, data_row):
                            h_clean = re.sub(r'\*\*(.+?)\*\*', r'\1', h)
                            v_clean = re.sub(r'\*\*(.+?)\*\*', r'*\1*', v)
                            pairs.append(f"*{h_clean}:* {v_clean}")
                        result.append(" | ".join(pairs))
            elif len(table_rows) == 1:
                cells = table_rows[0]
                result.append(" | ".join(cells))
            continue

        # Convert ### headings to bold
        heading_match = re.match(r'^(#{1,4})\s+(.+)', stripped)
        if heading_match:
            heading_text = re.sub(r'\*\*(.+?)\*\*', r'\1', heading_match.group(2))
            result.append(f"\n*{heading_text}*")
            i += 1
            continue

        # Convert **bold** to *bold*
        converted = re.sub(r'\*\*(.+?)\*\*', r'*\1*', line)
        result.append(converted)
        i += 1

    return "\n".join(result)


def send_teams_notification(pod_name, namespace, status, reason, error_logs, k8s_context=None, related_pods=None, content=None):
    """
    Send MS Teams notification for pod failures with major impact.

    Includes:
    - Pod name and namespace (plus any related_pods failing for the same deployment)
    - Current status and failure reason
    - Error log summary
    - AI explanation of the issue
    - AI-recommended solution
    - Kubernetes context
    - Timestamp

    related_pods: optional list of other pod dicts (pod_name, reason, status) that
    belong to the same deployment and are failing in this same run — they are
    listed in the card instead of sending a separate notification for each.

    content: optional pre-computed dict from _build_notification_content(), to
    avoid recomputing the AI explanation/solution when sending to multiple
    channels for the same failure.
    """
    related_pods = related_pods or []
    webhook_url = os.getenv("MS_TEAMS_WEBHOOK_URL", "").strip()
    
    if not webhook_url or webhook_url.startswith("https://outlook.webhook.office.com/webhookb2/xxxxx"):
        # Placeholder webhook, log but don't fail
        return {
            "status": "skipped",
            "reason": "MS Teams webhook not configured",
            "message": f"Would notify: {pod_name} in {namespace} - {reason}",
        }

    content = content or _build_notification_content(pod_name, namespace, status, reason, error_logs, k8s_context, related_pods)
    ai_explanation = content["ai_explanation"]
    ai_solution = content["ai_solution"]
    issue_category = content["issue_category"]
    action_owner = content["action_owner"]
    deployment_name = content["deployment_name"]
    repo_name = content["repo_name"]
    repo_url = content["repo_url"]
    is_repo_managed = content["is_repo_managed"]
    error_summary = content["error_summary"]
    timestamp = content["timestamp"]

    # Create color based on failure reason
    theme_color = "cc0000"  # Red for errors
    if "Pending" in reason:
        theme_color = "ff9800"  # Orange for pending

    header_facts = [
        {
            "name": "🔴 Primary Pod:" if related_pods else "🔴 Pod Name:",
            "value": f"**{pod_name}**"
        },
        {
            "name": "📍 Namespace:",
            "value": f"`{namespace}`"
        },
        {
            "name": "⚠️ Failure Reason:",
            "value": f"**{reason}**"
        },
        {
            "name": "🏃 Pod Status:",
            "value": f"**{reason}** (phase: {status})"
        },
        {
            "name": "🎯 K8s Context:",
            "value": f"`{k8s_context or os.getenv('K8S_CONTEXT') or 'unknown'}`"
        },
        {
            "name": "🏷️ Issue Category:",
            "value": f"**{issue_category}**"
        },
        {
            "name": "⏰ Detected At:",
            "value": timestamp
        }
    ]
    if related_pods:
        header_facts.append({
            "name": "🧩 Also Affected:",
            "value": ", ".join(f"`{p['pod_name']}` ({p['reason']})" for p in related_pods),
        })

    summary_text = (
        f"🚨 AI Alert: {pod_name} - {reason}" if not related_pods
        else f"🚨 AI Alert: {1 + len(related_pods)} pods affected in {deployment_name} ({reason})"
    )

    # Build formatted sections with proper font sizing hierarchy
    message = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": summary_text,
        "themeColor": theme_color,
        "sections": [
            # HEADER SECTION - Pod Status Overview
            {
                "activityTitle": "🚨 AI-Detected Kubernetes Incident",
                "activitySubtitle": "⚡ Intelligent Cluster Health Monitor",
                "facts": header_facts
            },
            # ERROR LOGS SECTION
            {
                "activityTitle": "� Captured Signal — Log Evidence",
                "markdown": True,
                "text": f"```\n{error_summary}\n```\n\n> **Note:** Check full logs with `kubectl logs -n {namespace} {pod_name}`"
            },
            # AI ROOT CAUSE SECTION
            {
                "activityTitle": "🧠 Intelligent RCA — AI-Powered Insights",
                "markdown": True,
                "text": ai_explanation
            },
            # AI SOLUTION SECTION
            {
                "activityTitle": (
                    "💡 AI Prescription — Helm-Native Fix" if "Helm Repo Change" in issue_category or "Config Issue" in issue_category
                    else "💡 AI Prescription — Key Vault Fix" if "Secret Missing" in issue_category or "Key Vault" in issue_category
                    else "💡 AI Prescription — Infrastructure Fix" if not is_repo_managed
                    else "💡 AI Prescription — Recommended Fix"
                ),
                "markdown": True,
                "text": ai_solution
            },
            # ACTION ITEMS SECTION — content driven by issue_category
            {
                "activityTitle": "�️ AI-Generated Recovery Playbook",
                "markdown": True,
                "text": content["action_guide"]
            }
        ],
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "📊 View in Azure Portal",
                "targets": [
                    {
                        "os": "default",
                        "uri": f"https://portal.azure.com/"
                    }
                ]
            },
            {
                "@type": "OpenUri",
                "name": f"📖 View {repo_name} Repo",
                "targets": [
                    {
                        "os": "default",
                        "uri": repo_url or f"https://dev.azure.com/techdatacorp/"
                    }
                ]
            }
        ]
    }
    
    try:
        response = requests.post(webhook_url, json=message, timeout=10, verify=False)
        
        if response.status_code in [200, 201, 202]:  # 202 = Accepted by Power Automate
            return {
                "status": "sent",
                "pod": pod_name,
                "message": "Notification sent successfully to MS Teams"
            }
        else:
            return {
                "status": "failed",
                "pod": pod_name,
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }
    except Exception as e:
        return {
            "status": "error",
            "pod": pod_name,
            "error": str(e)
        }


def send_slack_notification(pod_name, namespace, status, reason, error_logs, k8s_context=None, related_pods=None, content=None):
    """
    Send a Slack notification (via Incoming Webhook) for pod failures with
    major impact. Mirrors send_teams_notification but renders Slack Block Kit
    instead of a Teams MessageCard.

    content: optional pre-computed dict from _build_notification_content(), to
    avoid recomputing the AI explanation/solution when sending to multiple
    channels for the same failure.
    """
    related_pods = related_pods or []
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()

    if not webhook_url or webhook_url.startswith("https://hooks.slack.com/services/xxxxx"):
        # Placeholder webhook, log but don't fail
        return {
            "status": "skipped",
            "reason": "Slack webhook not configured",
            "message": f"Would notify: {pod_name} in {namespace} - {reason}",
        }

    content = content or _build_notification_content(pod_name, namespace, status, reason, error_logs, k8s_context, related_pods)
    ai_explanation = _convert_markdown_to_slack(content["ai_explanation"])
    ai_solution = _convert_markdown_to_slack(content["ai_solution"])
    action_guide = _convert_markdown_to_slack(content["action_guide"])
    issue_category = content["issue_category"]
    action_owner = content["action_owner"]
    deployment_name = content["deployment_name"]
    repo_name = content["repo_name"]
    repo_url = content["repo_url"]
    is_repo_managed = content["is_repo_managed"]
    error_summary = content["error_summary"]
    timestamp = content["timestamp"]

    # Color bar based on failure reason (matches Teams themeColor)
    bar_color = "#cc0000"  # Red for errors
    if "Pending" in reason:
        bar_color = "#ff9800"  # Orange for pending

    header_lines = [
        f"   *{'Primary Pod' if related_pods else 'Pod Name'}:* {pod_name}",
        f"   *Namespace:* {namespace}",
        f"   *Failure Reason:* {reason}",
        f"   *Pod Status:* {reason} (phase: {status})",
        f"   *K8s Context:* {k8s_context or os.getenv('K8S_CONTEXT') or 'unknown'}",
        f"   *Issue Category:* {issue_category}",
        f"   *Detected At:* {timestamp}",
    ]
    if related_pods:
        header_lines.append(
            "   *Also Affected:* " + ", ".join(f"{p['pod_name']} ({p['reason']})" for p in related_pods)
        )

    summary_text = (
        f"🚨 AI Alert: {pod_name} - {reason}" if not related_pods
        else f"🚨 AI Alert: {1 + len(related_pods)} pods affected in {deployment_name} ({reason})"
    )

    solution_title = (
        "💡 AI Prescription — Helm-Native Fix" if "Helm Repo Change" in issue_category or "Config Issue" in issue_category
        else "💡 AI Prescription — Key Vault Fix" if "Secret Missing" in issue_category or "Key Vault" in issue_category
        else "💡 AI Prescription — Infrastructure Fix" if not is_repo_managed
        else "💡 AI Prescription — Recommended Fix"
    )

    # Split long text into multiple Slack blocks to avoid "Show more" links.
    # Slack shows "Show more" when a single section exceeds ~3000 chars.
    def _indent(text, prefix="   "):
        """Add consistent left indent to every line of text."""
        return "\n".join(prefix + line if line.strip() else line for line in text.split("\n"))

    def _split_blocks(title, text, max_len=2800):
        """Return a list of section blocks, splitting text if needed."""
        indented = _indent(text)
        full = f"*{title}*\n{indented}" if title else indented
        if len(full) <= max_len:
            return [
                {"type": "divider"},
                {"type": "header", "text": {"type": "plain_text", "text": title, "emoji": True}},
                {"type": "section", "text": {"type": "mrkdwn", "text": indented}},
            ]
        # Split on paragraph boundaries (double newline) to keep readability
        result = [
            {"type": "divider"},
            {"type": "header", "text": {"type": "plain_text", "text": title, "emoji": True}},
        ]
        chunk = ""
        for para in indented.split("\n\n"):
            candidate = chunk + para + "\n\n"
            if len(candidate) > max_len and chunk.strip():
                result.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk.rstrip()}})
                chunk = para + "\n\n"
            else:
                chunk = candidate
        if chunk.strip():
            result.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk.rstrip()}})
        return result

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "🚨 AI-Detected Kubernetes Incident", "emoji": True}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(header_lines)}},
        {"type": "divider"},
        {"type": "header", "text": {"type": "plain_text", "text": "🔍 Captured Signal — Log Evidence", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"   ```{error_summary}```\n   _Check full logs with_ `kubectl logs -n {namespace} {pod_name}`"}},
        *_split_blocks("🧠 Intelligent RCA — AI-Powered Insights", ai_explanation),
        *_split_blocks(solution_title, ai_solution),
        *_split_blocks("🛠️ AI-Generated Recovery Playbook", action_guide),
    ]

    message = {
        "text": summary_text,
        "blocks": blocks,
    }

    try:
        response = requests.post(webhook_url, json=message, timeout=10, verify=False)

        if response.status_code == 200:
            return {
                "status": "sent",
                "pod": pod_name,
                "message": "Notification sent successfully to Slack"
            }
        else:
            return {
                "status": "failed",
                "pod": pod_name,
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }
    except Exception as e:
        return {
            "status": "error",
            "pod": pod_name,
            "error": str(e)
        }


def _send_recovery_notification(pods, k8s_context=None):
    """Send a single 'Recovered' Teams card for one or more pods that were
    previously alerted and are no longer failing (grouped by deployment)."""
    webhook_url = os.getenv("MS_TEAMS_WEBHOOK_URL", "").strip()

    if not webhook_url or webhook_url.startswith("https://outlook.webhook.office.com/webhookb2/xxxxx"):
        return {
            "status": "skipped",
            "reason": "MS Teams webhook not configured",
            "message": f"Would notify recovery for: {[p['pod_name'] for p in pods]}",
        }

    namespace = pods[0]["namespace"]
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    pod_list_text = "\n".join(f"- `{p['pod_name']}` (was: {p['reason']})" for p in pods)

    message = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": f"✅ Recovered: {len(pods)} pod(s) in {namespace}",
        "themeColor": "2eb886",
        "sections": [
            {
                "activityTitle": "✅ AI Verified — Pod(s) Recovered",
                "activitySubtitle": "Previously reported issue(s) have cleared",
                "facts": [
                    {"name": "📍 Namespace:", "value": f"`{namespace}`"},
                    {"name": "🎯 K8s Context:", "value": f"`{k8s_context or os.getenv('K8S_CONTEXT') or 'unknown'}`"},
                    {"name": "⏰ Recovered At:", "value": timestamp},
                ],
            },
            {
                "activityTitle": "🟢 Recovered Pods",
                "markdown": True,
                "text": pod_list_text,
            },
        ],
    }

    try:
        response = requests.post(webhook_url, json=message, timeout=10, verify=False)
        if response.status_code in [200, 201, 202]:
            return {"status": "sent", "pods": [p["pod_name"] for p in pods], "message": "Recovery notification sent"}
        return {"status": "failed", "pods": [p["pod_name"] for p in pods], "error": f"HTTP {response.status_code}: {response.text[:200]}"}
    except Exception as e:
        return {"status": "error", "pods": [p["pod_name"] for p in pods], "error": str(e)}


def _send_slack_recovery_notification(pods, k8s_context=None):
    """Send a single 'Recovered' Slack message for one or more pods that were
    previously alerted and are no longer failing (grouped by deployment)."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()

    if not webhook_url or webhook_url.startswith("https://hooks.slack.com/services/xxxxx"):
        return {
            "status": "skipped",
            "reason": "Slack webhook not configured",
            "message": f"Would notify recovery for: {[p['pod_name'] for p in pods]}",
        }

    namespace = pods[0]["namespace"]
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    pod_list_text = "\n".join(f"- `{p['pod_name']}` (was: {p['reason']})" for p in pods)

    message = {
        "text": f"✅ Recovered: {len(pods)} pod(s) in {namespace}",
        "attachments": [{
            "color": "#2eb886",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "✅ AI Verified — Pod(s) Recovered", "emoji": True}},
                {"type": "section", "text": {"type": "mrkdwn", "text": (
                    f"*Namespace:* `{namespace}`\n"
                    f"*K8s Context:* `{k8s_context or os.getenv('K8S_CONTEXT') or 'unknown'}`\n"
                    f"*Recovered At:* {timestamp}"
                )}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*🟢 Recovered Pods*\n{pod_list_text}"}},
            ],
        }],
    }

    try:
        response = requests.post(webhook_url, json=message, timeout=10, verify=False)
        if response.status_code == 200:
            return {"status": "sent", "pods": [p["pod_name"] for p in pods], "message": "Recovery notification sent"}
        return {"status": "failed", "pods": [p["pod_name"] for p in pods], "error": f"HTTP {response.status_code}: {response.text[:200]}"}
    except Exception as e:
        return {"status": "error", "pods": [p["pod_name"] for p in pods], "error": str(e)}


def send_healing_success_notification(actions, namespace, k8s_context=None):
    """Send a Slack notification showing which pods were auto-healed by AI.
    
    Args:
        actions: List of successful self-healing actions with pod_name, action_type, message
        namespace: Kubernetes namespace
        k8s_context: Kubernetes context name
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()

    if not webhook_url or webhook_url.startswith("https://hooks.slack.com/services/xxxxx"):
        return {
            "status": "skipped",
            "reason": "Slack webhook not configured",
            "message": f"Would notify healing for {len(actions)} action(s)",
        }

    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    
    # Group actions by type
    action_summary = {}
    for action in actions:
        action_type = action.get("action_type", "Unknown")
        action_summary[action_type] = action_summary.get(action_type, 0) + 1
    
    # Build action list
    action_list = []
    for action in actions[:10]:  # Limit to 10 for readability
        pod_name = action.get("pod_name", "unknown")
        action_type = action.get("action_type", "Unknown")
        
        # Map action types to friendly names and emojis
        action_map = {
            "RestartCrashLoopPod": "🔄 Restarted crashing pod",
            "RetryImagePull": "📦 Retried image pull",
            "ScaleUpOnResourcePressure": "⬆️  Scaled up deployment"
        }
        
        friendly_action = action_map.get(action_type, f"🤖 {action_type}")
        action_list.append(f"• {friendly_action}: `{pod_name}`")
    
    actions_text = "\n".join(action_list)
    
    # Build summary line
    summary_parts = [f"{count} {atype.replace('Pod', '').replace('OnResourcePressure', '')}" 
                     for atype, count in action_summary.items()]
    summary_line = ", ".join(summary_parts)

    message = {
        "text": f"🤖 Auto-Healed: {len(actions)} pod(s) in {namespace}",
        "attachments": [{
            "color": "#36a64f",
            "blocks": [
                {
                    "type": "header", 
                    "text": {
                        "type": "plain_text", 
                        "text": "🤖 AI Auto-Healing Complete", 
                        "emoji": True
                    }
                },
                {
                    "type": "section", 
                    "text": {
                        "type": "mrkdwn", 
                        "text": (
                            f"*Namespace:* `{namespace}`\n"
                            f"*K8s Context:* `{k8s_context or os.getenv('K8S_CONTEXT') or 'unknown'}`\n"
                            f"*Healed At:* {timestamp}\n"
                            f"*Actions:* {summary_line}"
                        )
                    }
                },
                {
                    "type": "section", 
                    "text": {
                        "type": "mrkdwn", 
                        "text": f"*✅ Successfully Healed*\n{actions_text}"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "💡 All actions passed safety checks and were verified successful"
                        }
                    ]
                }
            ],
        }],
    }

    try:
        response = requests.post(webhook_url, json=message, timeout=10, verify=False)
        if response.status_code == 200:
            return {
                "status": "sent", 
                "action_count": len(actions),
                "message": "Healing success notification sent"
            }
        return {
            "status": "failed", 
            "error": f"HTTP {response.status_code}: {response.text[:200]}"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def monitor_and_notify_failing_pods(namespace="default", k8s_context=None, raise_pr=False):
    """
    Main function: Detect failing pods, send consolidated MS Teams + Slack
    notifications (one per deployment/root-cause instead of one per pod),
    send recovery notifications for pods that have healed since the last run,
    and optionally raise an auto-fix PR in Azure DevOps.

    Args:
        raise_pr: If True and AZURE_DEVOPS_PAT is set, create a fix branch
                  and open a PR per affected deployment.

    Returns:
    - List of detected failing pods
    - List of notification results (failures + recoveries)
    - List of PR results (if raise_pr=True)
    """
    detection_result = detect_failing_pods(namespace, k8s_context)
    failing_pods = detection_result.get("failing_pods", [])

    # Load persisted state, and figure out which previously-notified pods have
    # recovered (were in state but are no longer in the active failing list).
    notif_state = _load_notification_state()
    recovered_pods = _find_recovered_pods(notif_state, failing_pods)
    notif_state = _prune_notification_state(notif_state, failing_pods)

    notification_results = []
    pr_results = []

    # Determine which pods are actually due for notification (not within cooldown)
    notifiable_pods = []
    for pod in failing_pods:
        if _should_notify(pod["pod_name"], pod["namespace"], notif_state):
            notifiable_pods.append(pod)
        else:
            notification_results.append({
                "status": "suppressed",
                "pod": pod["pod_name"],
                "message": (
                    f"Already notified within cooldown window "
                    f"({NOTIFICATION_COOLDOWN_SECONDS}s). Skipping duplicate."
                ),
            })

    # Group notifiable pods by deployment so pods failing for the same root
    # cause produce ONE consolidated card instead of spamming one per pod.
    for group_pods in _group_pods_by_deployment(notifiable_pods).values():
        primary, related = group_pods[0], group_pods[1:]

        # Compute the shared AI explanation/solution/action-guide ONCE, then
        # reuse it across every configured channel (Teams, Slack, ...).
        content = _build_notification_content(
            pod_name=primary["pod_name"],
            namespace=primary["namespace"],
            status=primary["status"],
            reason=primary["reason"],
            error_logs=primary["error_logs"],
            k8s_context=k8s_context,
            related_pods=related,
        )

        group_notifs = []
        if _NOTIFY_TEAMS:
            group_notifs.append(send_teams_notification(
                pod_name=primary["pod_name"],
                namespace=primary["namespace"],
                status=primary["status"],
                reason=primary["reason"],
                error_logs=primary["error_logs"],
                k8s_context=k8s_context,
                related_pods=related,
                content=content,
            ))
        if _NOTIFY_SLACK:
            group_notifs.append(send_slack_notification(
                pod_name=primary["pod_name"],
                namespace=primary["namespace"],
                status=primary["status"],
                reason=primary["reason"],
                error_logs=primary["error_logs"],
                k8s_context=k8s_context,
                related_pods=related,
                content=content,
            ))
        notification_results.extend(group_notifs)

        if any(n.get("status") in ("sent", "skipped") for n in group_notifs):
            for pod in group_pods:
                _record_notification(pod["pod_name"], pod["namespace"], pod["reason"], notif_state)

        if raise_pr and os.getenv("AZURE_DEVOPS_PAT"):
            # Raise a single PR per deployment group (using the primary pod) to
            # avoid duplicate branches/PRs for pods sharing the same deployment.
            try:
                from agent import create_fix_pr
                pr = create_fix_pr(primary["pod_name"], primary["namespace"], k8s_context)
                pr_results.append(pr)
            except Exception as e:
                pr_results.append({"status": "error", "pod": primary["pod_name"], "error": str(e)})

    # Send one consolidated recovery notification per deployment for pods that
    # were previously alerted and have since healed.
    # NOTE: Skip recovery notifications if self-healing is enabled in auto mode,
    # because pods are deleted during healing and would immediately trigger
    # false "recovered" alerts before the fixed config is applied.
    send_recovery_notifications = os.getenv("SEND_RECOVERY_NOTIFICATIONS", "yes").strip().lower() == "yes"
    
    recovered_count = len(recovered_pods)
    if send_recovery_notifications:
        for group_pods in _group_pods_by_deployment(recovered_pods).values():
            if _NOTIFY_TEAMS:
                notification_results.append(_send_recovery_notification(group_pods, k8s_context=k8s_context))
            if _NOTIFY_SLACK:
                notification_results.append(_send_slack_recovery_notification(group_pods, k8s_context=k8s_context))
    else:
        # Still track recovered_count for summary, but don't send notifications
        if recovered_count > 0:
            notification_results.append({
                "status": "skipped",
                "reason": "Recovery notifications disabled (SEND_RECOVERY_NOTIFICATIONS=no)",
                "message": f"Skipped recovery notifications for {recovered_count} pod(s)"
            })

    _save_notification_state(notif_state)

    pr_summary = ""
    if raise_pr:
        successful = len([p for p in pr_results if p.get("status") == "success"])
        skipped = len([p for p in pr_results if p.get("status") == "skipped"])
        pr_summary = f", raised {successful} PR(s)"
        if skipped:
            pr_summary += f", skipped {skipped} system pod(s)"

    summary = (
        f"Detected {len(failing_pods)} failing pod(s), "
        f"sent {len(notification_results)} notification(s){pr_summary}"
    )
    if recovered_count:
        summary += f", {recovered_count} pod(s) recovered"

    return {
        "namespace": namespace,
        "k8s_context": k8s_context,
        "detection": detection_result,
        "notifications": notification_results,
        "pr_results": pr_results,
        "summary": summary,
    }
