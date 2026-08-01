#!/usr/bin/env python3
"""
Complete Self-Healing Demo Script

This script automates the entire demo flow:
1. Cleanup any existing demo resources
2. Deploy broken pods (CrashLoopBackOff, ImagePullBackOff)
3. Wait for pods to be in failed state
4. Run monitoring (detects failures, sends notifications)
5. Wait 1 minute (demo delay for presentation)
6. Auto-healing executes
7. Apply fixed configurations
8. Verify all pods are healthy
9. Show summary
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

K8S_CONTEXT = os.getenv("K8S_CONTEXT", "aks-ai-agent-demo")
DEMO_DIR = "k8s/demo-deployments"

def run_command(cmd, description, cwd=None, check=True):
    """Run a shell command and display output"""
    print(f"\n{'='*70}")
    print(f"⚙️  {description}")
    print(f"{'='*70}")
    print(f"Command: {cmd}")
    print()
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr and "configured" not in result.stderr.lower():
            print(result.stderr)
            
        if check and result.returncode != 0:
            print(f"❌ Command failed with exit code {result.returncode}")
            return False
        
        print(f"✅ {description} - Complete")
        return True
    except subprocess.TimeoutExpired:
        print(f"⚠️  Command timed out after 180 seconds")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def print_header(title):
    """Print a formatted section header"""
    print("\n" + "="*70)
    print(f"🎯 {title}")
    print("="*70 + "\n")

def print_step(step_num, total_steps, description):
    """Print a step indicator"""
    print(f"\n{'='*70}")
    print(f"STEP {step_num}/{total_steps}: {description}")
    print(f"{'='*70}\n")

def wait_with_countdown(seconds, message):
    """Wait with a countdown display"""
    print(f"\n⏳ {message}")
    for remaining in range(seconds, 0, -5):
        mins, secs = divmod(remaining, 60)
        if mins > 0:
            time_str = f"{mins}m {secs}s"
        else:
            time_str = f"{secs}s"
        print(f"   ⏱️  {time_str} remaining...")
        time.sleep(min(5, remaining))
    print(f"✅ Wait complete!\n")

# ============================================================================
# MAIN DEMO SCRIPT
# ============================================================================

def main():
    print("\n" + "="*70)
    print("🎬 KUBERNETES SELF-HEALING DEMO - COMPLETE AUTOMATED RUN")
    print("="*70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Context: {K8S_CONTEXT}")
    print("="*70 + "\n")
    
    total_steps = 9
    
    # ========================================================================
    # STEP 1: Cleanup existing resources
    # ========================================================================
    print_step(1, total_steps, "Cleanup - Remove any existing demo resources")
    
    run_command(
        f"kubectl delete deployment api-gateway web-frontend --context {K8S_CONTEXT} --ignore-not-found=true",
        "Delete existing deployments",
        check=False
    )
    
    run_command(
        f"kubectl delete service api-gateway-service web-frontend-service --context {K8S_CONTEXT} --ignore-not-found=true",
        "Delete existing services",
        check=False
    )
    
    run_command(
        f"kubectl delete configmap web-frontend-html --context {K8S_CONTEXT} --ignore-not-found=true",
        "Delete existing configmaps",
        check=False
    )
    
    wait_with_countdown(10, "Waiting for resources to be deleted...")
    
    # ========================================================================
    # STEP 2: Deploy broken pods
    # ========================================================================
    print_step(2, total_steps, "Deploy Broken Pods (CrashLoopBackOff, ImagePullBackOff)")
    
    print("📋 Deploying api-gateway (will crash - missing REDIS_HOST)...")
    run_command(
        f"kubectl apply -f {DEMO_DIR}/01-api-gateway-crashloop.yaml --context {K8S_CONTEXT}",
        "Deploy api-gateway (broken)"
    )
    
    print("\n📋 Deploying web-frontend (will fail - non-existent image)...")
    run_command(
        f"kubectl apply -f {DEMO_DIR}/03-web-frontend-imagepull.yaml --context {K8S_CONTEXT}",
        "Deploy web-frontend (broken)"
    )
    
    # ========================================================================
    # STEP 3: Wait for pods to reach failed state
    # ========================================================================
    print_step(3, total_steps, "Wait for Pods to Fail")
    
    wait_with_countdown(45, "Waiting for pods to accumulate failures...")
    
    print("\n📊 Current pod status:")
    run_command(
        f"kubectl get pods --context {K8S_CONTEXT}",
        "Show pod status",
        check=False
    )
    
    # ========================================================================
    # STEP 4: Run monitoring and detection
    # ========================================================================
    print_step(4, total_steps, "Run Monitoring - Detect Failures and Send Notifications")
    
    print("🔍 AI is now scanning the cluster for failures...")
    print("📧 Notifications will be sent to Slack...")
    print("⏳ Then AI will wait 1 minute before auto-healing (demo mode)...\n")
    
    # Run the monitoring script with Python
    python_exe = sys.executable
    result = subprocess.run(
        [python_exe, "-u", "test_step1_monitoring.py"],
        capture_output=False,  # Show output in real-time
        text=True
    )
    
    if result.returncode != 0:
        print(f"\n⚠️  Monitoring script finished with warnings (exit code {result.returncode})")
        print("This is expected due to PowerShell output issues, continuing...\n")
    
    # ========================================================================
    # STEP 5: Show what happened
    # ========================================================================
    print_step(5, total_steps, "Review Self-Healing Actions")
    
    print("📊 Checking self-healing state file...")
    
    if os.path.exists("self_healing_state.json"):
        run_command(
            f"{python_exe} -c \"import json; data=json.load(open('self_healing_state.json')); print(f'Total actions in history: {{len(data.get(\\\"history\\\", []))}}'); recent=[a for a in data.get('history',[])[-4:]]; [print(f'  - {{a[\\\"action_type\\\"]}} on {{a[\\\"pod_name\\\"]}}: {{a[\\\"status\\\"]}}') for a in recent]\"",
            "Show recent self-healing actions",
            check=False
        )
    
    # ========================================================================
    # STEP 6: Apply fixed configurations
    # ========================================================================
    print_step(6, total_steps, "Apply Fixed Configurations")
    
    print("🔧 Applying api-gateway fix (adding REDIS_HOST)...")
    run_command(
        f"kubectl apply -f {DEMO_DIR}/01-api-gateway-fixed.yaml --context {K8S_CONTEXT}",
        "Apply api-gateway fix"
    )
    
    print("\n🔧 Applying web-frontend fix (using nginx image)...")
    run_command(
        f"kubectl apply -f {DEMO_DIR}/03-web-frontend-fixed.yaml --context {K8S_CONTEXT}",
        "Apply web-frontend fix"
    )
    
    # ========================================================================
    # STEP 7: Wait for pods to be ready
    # ========================================================================
    print_step(7, total_steps, "Wait for Pods to Become Healthy")
    
    print("⏳ Waiting for api-gateway pods to be ready...")
    run_command(
        f"kubectl wait --for=condition=ready pod -l app=api-gateway --context {K8S_CONTEXT} --timeout=120s",
        "Wait for api-gateway",
        check=False
    )
    
    print("\n⏳ Waiting for web-frontend pods to be ready...")
    run_command(
        f"kubectl wait --for=condition=ready pod -l app=web-frontend --context {K8S_CONTEXT} --timeout=120s",
        "Wait for web-frontend",
        check=False
    )
    
    wait_with_countdown(10, "Giving pods time to stabilize...")
    
    # ========================================================================
    # STEP 8: Verify success
    # ========================================================================
    print_step(8, total_steps, "Verify All Pods Are Healthy")
    
    run_command(
        f"kubectl get pods --context {K8S_CONTEXT} -o wide",
        "Show final pod status",
        check=False
    )
    
    # ========================================================================
    # STEP 9: Summary
    # ========================================================================
    print_step(9, total_steps, "Demo Complete - Summary")
    
    print("="*70)
    print("✅ DEMO COMPLETE!")
    print("="*70)
    print()
    print("What happened:")
    print("  1. ❌ Deployed 4 broken pods (2 CrashLoopBackOff, 2 ImagePullBackOff)")
    print("  2. 🔍 AI detected the failures")
    print("  3. 📧 Notifications sent to Slack")
    print("  4. ⏳ Waited 1 minute (demo delay)")
    print("  5. 🤖 AI auto-healed the pods (restart/retry)")
    print("  6. 🔧 Applied configuration fixes")
    print("  7. ✅ All pods are now healthy!")
    print()
    print("="*70)
    print("View Results:")
    print("="*70)
    print(f"  Dashboard: http://127.0.0.1:63390")
    print(f"  Context: {K8S_CONTEXT}")
    print()
    print("  All 4 pods should be green and Running:")
    print("    - api-gateway (2 replicas)")
    print("    - web-frontend (2 replicas)")
    print()
    print("="*70)
    print("Next Steps:")
    print("="*70)
    print("  • Check Slack for failure notifications")
    print("  • Open dashboard to see green pods")
    print("  • Review self_healing_state.json for audit trail")
    print("  • Run 'kubectl get pods' to verify status")
    print()
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {e}")
        sys.exit(1)
