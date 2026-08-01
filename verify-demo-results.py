#!/usr/bin/env python3
"""Verify demo results - check pods and notifications"""

import os
import subprocess
import json
from datetime import datetime

K8S_CONTEXT = os.getenv("K8S_CONTEXT", "aks-ai-agent-demo")

print("=" * 70)
print("VERIFYING DEMO RESULTS")
print("=" * 70)
print()

# Check pod status
print("1. Current Pod Status:")
print("-" * 70)
try:
    result = subprocess.run(
        f"kubectl get pods --context {K8S_CONTEXT}",
        shell=True,
        capture_output=True,
        text=True,
        timeout=30
    )
    print(result.stdout)
    
    # Count Running pods
    lines = result.stdout.strip().split('\n')[1:]  # Skip header
    running_count = sum(1 for line in lines if 'Running' in line and '1/1' in line)
    total_pods = len(lines)
    
    print(f"Running pods: {running_count}/{total_pods}")
    
    if running_count == total_pods and total_pods >= 4:
        print("✅ All pods are healthy!")
    else:
        print("⚠️  Some pods are not fully healthy yet")
        
except Exception as e:
    print(f"❌ Error checking pods: {e}")

print()

# Check self-healing state
print("2. Recent Self-Healing Actions:")
print("-" * 70)
try:
    with open('self_healing_state.json', 'r') as f:
        state = json.load(f)
        
    history = state.get('history', [])
    recent = [h for h in history[-10:] if not h.get('dry_run', False)]
    
    print(f"Total actions in history: {len(history)}")
    print(f"Recent live actions: {len(recent)}")
    print()
    
    for action in recent[-4:]:
        status_icon = "✅" if action.get('status') == 'success' else "⚠️"
        print(f"{status_icon} {action.get('action_type', 'Unknown')}")
        print(f"   Pod: {action.get('pod_name', 'N/A')}")
        print(f"   Status: {action.get('status', 'unknown')}")
        print(f"   Message: {action.get('message', 'N/A')[:80]}")
        print()
        
except FileNotFoundError:
    print("❌ self_healing_state.json not found")
except Exception as e:
    print(f"❌ Error reading state file: {e}")

print()

# Check notification state
print("3. Notification State:")
print("-" * 70)
try:
    with open('notification_state.json', 'r') as f:
        notif_state = json.load(f)
        
    print(f"Pods tracked: {len(notif_state)}")
    
    for key, entry in list(notif_state.items())[:5]:
        if isinstance(entry, dict):
            print(f"  - {key}: {entry.get('reason', 'Unknown')}")
            
except FileNotFoundError:
    print("⚠️  notification_state.json not found (may be first run)")
except Exception as e:
    print(f"❌ Error reading notification state: {e}")

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print()

# Final checks
config_checks = []

# Check SEND_RECOVERY_NOTIFICATIONS
from dotenv import load_dotenv
load_dotenv()

send_recovery = os.getenv("SEND_RECOVERY_NOTIFICATIONS", "yes").lower()
config_checks.append(("Recovery notifications disabled", send_recovery == "no"))

delay = int(os.getenv("SELF_HEALING_DELAY_SECONDS", "0"))
config_checks.append(("1-minute delay configured", delay == 60))

healing_enabled = os.getenv("SELF_HEALING_ENABLED", "no").lower() == "yes"
config_checks.append(("Self-healing enabled", healing_enabled))

dry_run = os.getenv("SELF_HEALING_DRY_RUN", "yes").lower() == "yes"
config_checks.append(("Live mode (not dry-run)", not dry_run))

for check_name, passed in config_checks:
    icon = "✅" if passed else "❌"
    print(f"{icon} {check_name}")

print()
print("=" * 70)
print("Dashboard: http://127.0.0.1:63390")
print("=" * 70)
