#!/usr/bin/env python3
"""Quick check of demo status"""
import json
import subprocess
import os

print("=" * 70)
print("DEMO STATUS CHECK")
print("=" * 70)

# Check state file for latest actions
try:
    with open('self_healing_state.json', 'r') as f:
        state = json.load(f)
    
    recent = [a for a in state.get('history', [])[-5:] if not a.get('dry_run', False)]
    
    print(f"\nLatest {len(recent)} self-healing actions:")
    for action in recent:
        status = action.get('status', 'unknown')
        icon = "✅" if status == "success" else "⚠️"
        print(f"{icon} {action.get('action_type', 'Unknown')}: {action.get('pod_name', 'N/A')}")
        print(f"   Status: {status}")
    
except Exception as e:
    print(f"Error reading state: {e}")

# Check pods
print("\n" + "=" * 70)
print("CURRENT PODS")
print("=" * 70)
try:
    result = subprocess.run(
        "kubectl get pods --context aks-ai-agent-demo",
        shell=True,
        capture_output=True,
        text=True,
        timeout=10
    )
    print(result.stdout)
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 70)
print("CHECK SLACK FOR NOTIFICATIONS:")
print("=" * 70)
print("1. ❌ Failure detection (should have 4 pods)")
print("2. 🤖 Healing success (NEW - should show healed pods!)")
print("\nDashboard: http://127.0.0.1:63390")
print("=" * 70)
