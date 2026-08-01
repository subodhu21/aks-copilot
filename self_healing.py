"""
Self-Healing Actions for Kubernetes Pod Failures

Implements safe, automated remediation actions for common pod failure scenarios:
1. Auto-restart CrashLoopBackOff pods
2. Auto-scale up on OOMKilled/resource pressure
3. Retry ImagePullBackOff with pod deletion

Each action follows a validate → execute → verify → rollback pattern for safety.
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

# ========== Configuration ==========
SELF_HEALING_ENABLED = os.getenv("SELF_HEALING_ENABLED", "no").strip().lower() == "yes"
SELF_HEALING_MODE = os.getenv("SELF_HEALING_MODE", "ask").strip().lower()  # auto, ask, disabled
SELF_HEALING_MAX_ACTIONS_PER_HOUR = int(os.getenv("SELF_HEALING_MAX_ACTIONS_PER_HOUR", "10"))
SELF_HEALING_DRY_RUN = os.getenv("SELF_HEALING_DRY_RUN", "no").strip().lower() == "yes"

# Action-specific thresholds
RESTART_MIN_CRASH_COUNT = int(os.getenv("RESTART_MIN_CRASH_COUNT", "5"))
RESTART_MIN_INTERVAL_SECONDS = int(os.getenv("RESTART_MIN_INTERVAL_SECONDS", "300"))  # 5 minutes
SCALE_UP_MIN_OOM_COUNT = int(os.getenv("SCALE_UP_MIN_OOM_COUNT", "2"))
SCALE_UP_MAX_REPLICAS = int(os.getenv("SCALE_UP_MAX_REPLICAS", "10"))
IMAGEPULL_RETRY_MAX_AGE_SECONDS = int(os.getenv("IMAGEPULL_RETRY_MAX_AGE_SECONDS", "1800"))  # 30 minutes

# State tracking file
_DEFAULT_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "self_healing_state.json")
SELF_HEALING_STATE_FILE = os.getenv("SELF_HEALING_STATE_FILE", _DEFAULT_STATE_FILE)


class SelfHealingAction:
    """Base class for self-healing actions."""
    
    def __init__(self, pod_name: str, namespace: str, k8s_context: str, reason: str, pod_info: Dict[str, Any]):
        self.pod_name = pod_name
        self.namespace = namespace
        self.k8s_context = k8s_context
        self.reason = reason
        self.pod_info = pod_info
        self.action_id = f"{pod_name}-{int(time.time())}"
        self.action_type = self.__class__.__name__
        self.executed_at = None
        self.result = None
        
    def validate_safety(self) -> Dict[str, Any]:
        """Check if action is safe to execute. Return dict with 'safe': bool, 'reason': str"""
        raise NotImplementedError
        
    def execute(self) -> Dict[str, Any]:
        """Perform the healing action. Return dict with 'success': bool, 'message': str"""
        raise NotImplementedError
        
    def verify(self) -> Dict[str, Any]:
        """Verify action succeeded. Return dict with 'verified': bool, 'message': str"""
        raise NotImplementedError
        
    def rollback(self) -> Dict[str, Any]:
        """Undo action if verification failed. Return dict with 'rolled_back': bool, 'message': str"""
        return {"rolled_back": False, "message": "No rollback implemented for this action"}
        
    def run(self) -> Dict[str, Any]:
        """Execute full action lifecycle: validate → execute → verify."""
        result = {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "pod_name": self.pod_name,
            "namespace": self.namespace,
            "reason": self.reason,
            "timestamp": datetime.now().isoformat(),
            "dry_run": SELF_HEALING_DRY_RUN,
            "status": "pending"
        }
        
        # Step 1: Validate safety
        safety_check = self.validate_safety()
        result["safety_check"] = safety_check
        
        if not safety_check.get("safe", False):
            result["status"] = "rejected"
            result["message"] = f"Safety check failed: {safety_check.get('reason', 'Unknown')}"
            return result
            
        # Step 2: Execute action
        if SELF_HEALING_DRY_RUN:
            result["status"] = "dry_run"
            result["message"] = f"[DRY RUN] Would execute: {self.get_action_description()}"
            return result
            
        try:
            self.executed_at = time.time()
            exec_result = self.execute()
            result["execution"] = exec_result
            
            if not exec_result.get("success", False):
                result["status"] = "failed"
                result["message"] = f"Execution failed: {exec_result.get('message', 'Unknown error')}"
                return result
                
            # Step 3: Verify action succeeded
            time.sleep(5)  # Wait for k8s to update state
            verify_result = self.verify()
            result["verification"] = verify_result
            
            if verify_result.get("verified", False):
                result["status"] = "success"
                result["message"] = f"Action succeeded: {verify_result.get('message', '')}"
            else:
                result["status"] = "verification_failed"
                result["message"] = f"Action executed but verification failed: {verify_result.get('message', '')}"
                
                # Attempt rollback
                rollback_result = self.rollback()
                result["rollback"] = rollback_result
                
        except Exception as e:
            result["status"] = "error"
            result["message"] = f"Exception during execution: {str(e)}"
            result["error"] = str(e)
            
        return result
        
    def get_action_description(self) -> str:
        """Human-readable description of what this action will do."""
        return f"{self.action_type} on {self.pod_name}"


class RestartCrashLoopPod(SelfHealingAction):
    """Delete a pod stuck in CrashLoopBackOff to trigger fresh restart."""
    
    def validate_safety(self) -> Dict[str, Any]:
        from tools import run_cmd
        
        # Check restart count
        restart_count = self.pod_info.get("restart_count", 0)
        if restart_count < RESTART_MIN_CRASH_COUNT:
            return {
                "safe": False,
                "reason": f"Restart count ({restart_count}) below threshold ({RESTART_MIN_CRASH_COUNT})"
            }
            
        # Check if we recently restarted this pod
        state = _load_state()
        last_action = state.get("actions", {}).get(f"{self.namespace}/{self.pod_name}")
        if last_action:
            last_timestamp = last_action.get("timestamp", 0)
            if (time.time() - last_timestamp) < RESTART_MIN_INTERVAL_SECONDS:
                return {
                    "safe": False,
                    "reason": f"Pod was restarted recently (< {RESTART_MIN_INTERVAL_SECONDS}s ago)"
                }
                
        # Check if pod is part of StatefulSet (needs special handling)
        pod_desc = run_cmd(
            f"kubectl get pod {self.pod_name} -n {self.namespace} -o json",
            self.k8s_context
        )
        try:
            pod_json = json.loads(pod_desc)
            owner_refs = pod_json.get("metadata", {}).get("ownerReferences", [])
            for owner in owner_refs:
                if owner.get("kind") == "StatefulSet":
                    return {
                        "safe": False,
                        "reason": "Pod is part of StatefulSet (requires manual intervention)"
                    }
        except json.JSONDecodeError:
            pass
            
        return {"safe": True, "reason": "All safety checks passed"}
        
    def execute(self) -> Dict[str, Any]:
        from tools import run_cmd
        
        cmd = f"kubectl delete pod {self.pod_name} -n {self.namespace}"
        output = run_cmd(cmd, self.k8s_context)
        
        if "deleted" in output.lower() or "error" not in output.lower():
            _record_action(self.namespace, self.pod_name, "restart", self.executed_at)
            return {
                "success": True,
                "message": f"Pod deleted successfully",
                "output": output
            }
        else:
            return {
                "success": False,
                "message": f"Failed to delete pod",
                "output": output
            }
            
    def verify(self) -> Dict[str, Any]:
        from tools import run_cmd
        
        # Check if new pod was created
        cmd = f"kubectl get pods -n {self.namespace} -l app={self.pod_name.rsplit('-', 2)[0]} -o json"
        output = run_cmd(cmd, self.k8s_context)
        
        try:
            pods_json = json.loads(output)
            items = pods_json.get("items", [])
            
            if not items:
                return {
                    "verified": False,
                    "message": "No pods found after deletion (deployment may be scaled to 0)"
                }
                
            # Check if any pod is running or starting
            for pod in items:
                pod_name = pod.get("metadata", {}).get("name", "")
                phase = pod.get("status", {}).get("phase", "")
                
                if phase in ["Running", "Pending"]:
                    return {
                        "verified": True,
                        "message": f"New pod {pod_name} is {phase}"
                    }
                    
            return {
                "verified": False,
                "message": "New pod created but not in Running/Pending state"
            }
        except json.JSONDecodeError:
            return {
                "verified": False,
                "message": "Failed to parse kubectl output"
            }
            
    def get_action_description(self) -> str:
        return f"Delete pod {self.pod_name} to trigger fresh restart (restart count: {self.pod_info.get('restart_count', 0)})"


class ScaleUpOnResourcePressure(SelfHealingAction):
    """Scale up deployment when pods are OOMKilled or under resource pressure."""
    
    def __init__(self, pods: List[Dict[str, Any]], namespace: str, k8s_context: str, deployment_name: str):
        # Use first pod for base class init
        first_pod = pods[0] if pods else {}
        super().__init__(
            pod_name=first_pod.get("pod_name", "unknown"),
            namespace=namespace,
            k8s_context=k8s_context,
            reason="ResourcePressure",
            pod_info=first_pod
        )
        self.pods = pods
        self.deployment_name = deployment_name
        self.original_replicas = None
        self.target_replicas = None
        
    def validate_safety(self) -> Dict[str, Any]:
        from tools import run_cmd
        
        # Check if enough pods are affected
        if len(self.pods) < SCALE_UP_MIN_OOM_COUNT:
            return {
                "safe": False,
                "reason": f"Only {len(self.pods)} pods affected, threshold is {SCALE_UP_MIN_OOM_COUNT}"
            }
            
        # Get current replica count
        cmd = f"kubectl get deployment {self.deployment_name} -n {self.namespace} -o json"
        output = run_cmd(cmd, self.k8s_context)
        
        try:
            dep_json = json.loads(output)
            spec = dep_json.get("spec", {})
            self.original_replicas = spec.get("replicas", 1)
            self.target_replicas = min(self.original_replicas + 2, SCALE_UP_MAX_REPLICAS)
            
            if self.original_replicas >= SCALE_UP_MAX_REPLICAS:
                return {
                    "safe": False,
                    "reason": f"Already at max replicas ({SCALE_UP_MAX_REPLICAS})"
                }
                
            if self.target_replicas == self.original_replicas:
                return {
                    "safe": False,
                    "reason": "No scale-up needed (would exceed max replicas)"
                }
                
        except (json.JSONDecodeError, KeyError):
            return {
                "safe": False,
                "reason": "Failed to get current replica count"
            }
            
        return {
            "safe": True,
            "reason": f"Will scale from {self.original_replicas} to {self.target_replicas} replicas"
        }
        
    def execute(self) -> Dict[str, Any]:
        from tools import run_cmd
        
        cmd = f"kubectl scale deployment {self.deployment_name} --replicas={self.target_replicas} -n {self.namespace}"
        output = run_cmd(cmd, self.k8s_context)
        
        if "scaled" in output.lower():
            _record_action(self.namespace, self.deployment_name, "scale_up", self.executed_at)
            return {
                "success": True,
                "message": f"Scaled deployment from {self.original_replicas} to {self.target_replicas}",
                "output": output,
                "original_replicas": self.original_replicas
            }
        else:
            return {
                "success": False,
                "message": "Failed to scale deployment",
                "output": output
            }
            
    def verify(self) -> Dict[str, Any]:
        from tools import run_cmd
        
        cmd = f"kubectl get deployment {self.deployment_name} -n {self.namespace} -o json"
        output = run_cmd(cmd, self.k8s_context)
        
        try:
            dep_json = json.loads(output)
            status = dep_json.get("status", {})
            current_replicas = status.get("replicas", 0)
            ready_replicas = status.get("readyReplicas", 0)
            
            if current_replicas >= self.target_replicas:
                return {
                    "verified": True,
                    "message": f"Deployment scaled to {current_replicas} replicas ({ready_replicas} ready)"
                }
            else:
                return {
                    "verified": False,
                    "message": f"Scale not complete: {current_replicas}/{self.target_replicas} replicas"
                }
        except (json.JSONDecodeError, KeyError):
            return {
                "verified": False,
                "message": "Failed to verify scale operation"
            }
            
    def rollback(self) -> Dict[str, Any]:
        from tools import run_cmd
        
        if self.original_replicas is None:
            return {
                "rolled_back": False,
                "message": "Cannot rollback: original replica count unknown"
            }
            
        cmd = f"kubectl scale deployment {self.deployment_name} --replicas={self.original_replicas} -n {self.namespace}"
        output = run_cmd(cmd, self.k8s_context)
        
        if "scaled" in output.lower():
            return {
                "rolled_back": True,
                "message": f"Rolled back to {self.original_replicas} replicas"
            }
        else:
            return {
                "rolled_back": False,
                "message": "Failed to rollback scale operation"
            }
            
    def get_action_description(self) -> str:
        return f"Scale up deployment {self.deployment_name} from {self.original_replicas} to {self.target_replicas} replicas (OOMKilled: {len(self.pods)} pods)"


class RetryImagePull(SelfHealingAction):
    """Delete pod in ImagePullBackOff to retry image pull (transient registry issues)."""
    
    def validate_safety(self) -> Dict[str, Any]:
        from tools import run_cmd
        
        # Check pod age - only retry if relatively new (avoid old misconfigurations)
        try:
            cmd = f"kubectl get pod {self.pod_name} -n {self.namespace} -o json"
            output = run_cmd(cmd, self.k8s_context)
            pod_json = json.loads(output)
            
            creation_time = pod_json.get("metadata", {}).get("creationTimestamp", "")
            if creation_time:
                from dateutil import parser as date_parser
                created_at = date_parser.parse(creation_time)
                age_seconds = (datetime.now(created_at.tzinfo) - created_at).total_seconds()
                
                if age_seconds > IMAGEPULL_RETRY_MAX_AGE_SECONDS:
                    return {
                        "safe": False,
                        "reason": f"Pod is too old ({int(age_seconds/60)} minutes). Likely a config issue, not transient."
                    }
        except Exception:
            pass  # Continue if age check fails
            
        # Check if we recently retried this pod
        state = _load_state()
        last_action = state.get("actions", {}).get(f"{self.namespace}/{self.pod_name}")
        if last_action and last_action.get("action_type") == "imagepull_retry":
            last_timestamp = last_action.get("timestamp", 0)
            if (time.time() - last_timestamp) < RESTART_MIN_INTERVAL_SECONDS:
                return {
                    "safe": False,
                    "reason": f"ImagePull already retried recently (< {RESTART_MIN_INTERVAL_SECONDS}s ago)"
                }
                
        return {"safe": True, "reason": "Will retry image pull"}
        
    def execute(self) -> Dict[str, Any]:
        from tools import run_cmd
        
        cmd = f"kubectl delete pod {self.pod_name} -n {self.namespace}"
        output = run_cmd(cmd, self.k8s_context)
        
        if "deleted" in output.lower() or "error" not in output.lower():
            _record_action(self.namespace, self.pod_name, "imagepull_retry", self.executed_at)
            return {
                "success": True,
                "message": "Pod deleted to retry image pull",
                "output": output
            }
        else:
            return {
                "success": False,
                "message": "Failed to delete pod",
                "output": output
            }
            
    def verify(self) -> Dict[str, Any]:
        from tools import run_cmd
        
        time.sleep(10)  # Give registry more time
        
        cmd = f"kubectl get pod {self.pod_name} -n {self.namespace} -o json"
        output = run_cmd(cmd, self.k8s_context)
        
        try:
            pod_json = json.loads(output)
            phase = pod_json.get("status", {}).get("phase", "")
            container_statuses = pod_json.get("status", {}).get("containerStatuses", [])
            
            # Check if new pod exists (name might be different)
            if not container_statuses:
                # Try to find new pod
                cmd = f"kubectl get pods -n {self.namespace} -l app={self.pod_name.rsplit('-', 2)[0]} -o json"
                output = run_cmd(cmd, self.k8s_context)
                pods_json = json.loads(output)
                items = pods_json.get("items", [])
                
                if items:
                    latest_pod = items[0]
                    phase = latest_pod.get("status", {}).get("phase", "")
                    container_statuses = latest_pod.get("status", {}).get("containerStatuses", [])
                    
            # Check if any container is no longer in ImagePullBackOff
            for cs in container_statuses:
                waiting = cs.get("state", {}).get("waiting", {})
                if waiting.get("reason") == "ImagePullBackOff":
                    return {
                        "verified": False,
                        "message": "Still in ImagePullBackOff (likely a persistent issue)"
                    }
                    
            if phase in ["Running", "Pending"]:
                return {
                    "verified": True,
                    "message": f"Pod is now {phase}, image pull successful"
                }
            else:
                return {
                    "verified": False,
                    "message": f"Pod in unexpected phase: {phase}"
                }
                
        except (json.JSONDecodeError, KeyError) as e:
            return {
                "verified": False,
                "message": f"Failed to verify: {str(e)}"
            }
            
    def get_action_description(self) -> str:
        return f"Delete pod {self.pod_name} to retry image pull (ImagePullBackOff)"


# ========== State Management ==========

def _load_state() -> Dict[str, Any]:
    """Load self-healing state from disk."""
    try:
        with open(SELF_HEALING_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"actions": {}, "history": []}


def _save_state(state: Dict[str, Any]) -> None:
    """Save self-healing state to disk."""
    with open(SELF_HEALING_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _record_action(namespace: str, resource_name: str, action_type: str, timestamp: float) -> None:
    """Record action in state file."""
    state = _load_state()
    key = f"{namespace}/{resource_name}"
    state["actions"][key] = {
        "action_type": action_type,
        "timestamp": timestamp
    }
    _save_state(state)


def _check_rate_limit() -> Dict[str, Any]:
    """Check if we've hit the rate limit for self-healing actions."""
    state = _load_state()
    history = state.get("history", [])
    
    # Count actions in last hour
    one_hour_ago = time.time() - 3600
    recent_actions = [a for a in history if a.get("timestamp", 0) > one_hour_ago]
    
    if len(recent_actions) >= SELF_HEALING_MAX_ACTIONS_PER_HOUR:
        return {
            "allowed": False,
            "reason": f"Rate limit exceeded: {len(recent_actions)}/{SELF_HEALING_MAX_ACTIONS_PER_HOUR} actions in last hour"
        }
        
    return {"allowed": True, "count": len(recent_actions)}


def _add_to_history(action_result: Dict[str, Any]) -> None:
    """Add action result to history."""
    state = _load_state()
    if "history" not in state:
        state["history"] = []
    
    state["history"].append({
        **action_result,
        "timestamp": time.time()
    })
    
    # Keep only last 100 actions
    state["history"] = state["history"][-100:]
    _save_state(state)


# ========== Main Self-Healing Logic ==========

def evaluate_and_heal(failing_pods: List[Dict[str, Any]], namespace: str, k8s_context: str) -> Dict[str, Any]:
    """
    Evaluate failing pods and execute appropriate self-healing actions.
    
    Args:
        failing_pods: List of failing pod dicts from tools.monitor_and_notify_failing_pods
        namespace: Kubernetes namespace
        k8s_context: Kubernetes context
        
    Returns:
        Dict with keys: enabled, actions_taken, actions_skipped, summary
    """
    result = {
        "enabled": SELF_HEALING_ENABLED,
        "mode": SELF_HEALING_MODE,
        "dry_run": SELF_HEALING_DRY_RUN,
        "actions_taken": [],
        "actions_skipped": [],
        "summary": ""
    }
    
    if not SELF_HEALING_ENABLED or SELF_HEALING_MODE == "disabled":
        result["summary"] = "Self-healing is disabled"
        return result
        
    # Check rate limit
    rate_check = _check_rate_limit()
    if not rate_check.get("allowed", False):
        result["summary"] = rate_check.get("reason", "Rate limit exceeded")
        return result
        
    # Group pods by issue type
    crashloop_pods = []
    oomkilled_pods = []
    imagepull_pods = []
    
    for pod in failing_pods:
        reason = pod.get("reason", "").lower()
        if "crashloopbackoff" in reason or "crash" in reason:
            crashloop_pods.append(pod)
        elif "oomkilled" in reason or "oom" in reason:
            oomkilled_pods.append(pod)
        elif "imagepullbackoff" in reason or "imagepull" in reason:
            imagepull_pods.append(pod)
            
    # Execute actions
    actions = []
    
    # 1. Handle CrashLoopBackOff pods
    for pod in crashloop_pods:
        action = RestartCrashLoopPod(
            pod_name=pod["pod_name"],
            namespace=namespace,
            k8s_context=k8s_context,
            reason=pod["reason"],
            pod_info=pod
        )
        actions.append(action)
        
    # 2. Handle ImagePullBackOff pods
    for pod in imagepull_pods:
        action = RetryImagePull(
            pod_name=pod["pod_name"],
            namespace=namespace,
            k8s_context=k8s_context,
            reason=pod["reason"],
            pod_info=pod
        )
        actions.append(action)
        
    # 3. Handle OOMKilled pods (group by deployment)
    if oomkilled_pods:
        # Group by deployment
        deployments = {}
        for pod in oomkilled_pods:
            # Extract deployment name (remove pod suffix)
            dep_name = "-".join(pod["pod_name"].split("-")[:-2]) or pod["pod_name"].split("-")[0]
            if dep_name not in deployments:
                deployments[dep_name] = []
            deployments[dep_name].append(pod)
            
        # Create scale-up action for each deployment
        for dep_name, pods in deployments.items():
            action = ScaleUpOnResourcePressure(
                pods=pods,
                namespace=namespace,
                k8s_context=k8s_context,
                deployment_name=dep_name
            )
            actions.append(action)
            
    # Execute actions (respecting rate limit)
    for action in actions:
        rate_check = _check_rate_limit()
        if not rate_check.get("allowed", False):
            result["actions_skipped"].append({
                "action_type": action.action_type,
                "pod_name": action.pod_name,
                "reason": "Rate limit reached"
            })
            continue
            
        action_result = action.run()
        
        if action_result["status"] in ["success", "dry_run"]:
            result["actions_taken"].append(action_result)
        else:
            result["actions_skipped"].append(action_result)
            
        # Add to history
        _add_to_history(action_result)
        
    # Generate summary
    taken = len(result["actions_taken"])
    skipped = len(result["actions_skipped"])
    
    if SELF_HEALING_DRY_RUN:
        result["summary"] = f"[DRY RUN] Would execute {taken} actions, skip {skipped}"
    else:
        result["summary"] = f"Executed {taken} self-healing actions, skipped {skipped}"
        
    return result


def get_self_healing_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent self-healing action history."""
    state = _load_state()
    history = state.get("history", [])
    return sorted(history, key=lambda x: x.get("timestamp", 0), reverse=True)[:limit]


def get_self_healing_stats() -> Dict[str, Any]:
    """Get self-healing statistics."""
    state = _load_state()
    history = state.get("history", [])
    
    # Calculate stats
    total = len(history)
    successful = len([h for h in history if h.get("status") == "success"])
    failed = len([h for h in history if h.get("status") in ["failed", "error", "verification_failed"]])
    
    # Count by action type
    by_type = {}
    for h in history:
        action_type = h.get("action_type", "unknown")
        if action_type not in by_type:
            by_type[action_type] = {"total": 0, "success": 0, "failed": 0}
        by_type[action_type]["total"] += 1
        if h.get("status") == "success":
            by_type[action_type]["success"] += 1
        elif h.get("status") in ["failed", "error", "verification_failed"]:
            by_type[action_type]["failed"] += 1
            
    # Recent activity (last hour)
    one_hour_ago = time.time() - 3600
    recent = [h for h in history if h.get("timestamp", 0) > one_hour_ago]
    
    return {
        "total_actions": total,
        "successful": successful,
        "failed": failed,
        "success_rate": f"{(successful/total*100):.1f}%" if total > 0 else "N/A",
        "by_action_type": by_type,
        "recent_hour_count": len(recent),
        "rate_limit": f"{len(recent)}/{SELF_HEALING_MAX_ACTIONS_PER_HOUR}"
    }
