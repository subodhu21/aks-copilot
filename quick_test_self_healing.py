#!/usr/bin/env python3
"""Quick direct test of self-healing functionality"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

print("=" * 70)
print("SELF-HEALING QUICK TEST")
print("=" * 70)
print()

# Import self-healing module
try:
    from self_healing import (
        evaluate_and_heal,
        get_self_healing_history,
        get_self_healing_stats,
        SELF_HEALING_ENABLED,
        SELF_HEALING_MODE,
        SELF_HEALING_DRY_RUN
    )
    print("✓ Self-healing module imported")
except Exception as e:
    print(f"✗ Failed to import self-healing: {e}")
    sys.exit(1)

# Display configuration
print()
print("Configuration:")
print(f"  Enabled: {SELF_HEALING_ENABLED}")
print(f"  Mode: {SELF_HEALING_MODE}")
print(f"  Dry Run: {SELF_HEALING_DRY_RUN}")
print()

# Get current statistics
print("Current Statistics:")
stats = get_self_healing_stats()
print(f"  Total actions: {stats['total_actions']}")
print(f"  Success rate: {stats['success_rate']}")
print(f"  Rate limit: {stats['rate_limit']}")
print(f"  Recent hour: {stats['recent_hour_count']} actions")
print()

# Get action history
print("Recent Action History (last 5):")
history = get_self_healing_history(limit=5)
if history:
    for i, action in enumerate(history, 1):
        print(f"\n  {i}. {action.get('action_type', 'Unknown')}")
        print(f"     Pod: {action.get('pod_name', 'N/A')}")
        print(f"     Status: {action.get('status', 'unknown')}")
        print(f"     Dry Run: {action.get('dry_run', False)}")
        print(f"     Message: {action.get('message', 'N/A')[:80]}")
else:
    print("  No actions in history yet")

print()
print("=" * 70)

# Now try to get failing pods from Kubernetes
print("Attempting to detect failing pods...")
print()

try:
    from tools import get_failing_pods
    
    namespace = os.getenv("K8S_NAMESPACE", "default")
    k8s_context = os.getenv("K8S_CONTEXT", "aks-ai-agent-demo")
    
    print(f"Namespace: {namespace}")
    print(f"Context: {k8s_context}")
    print()
    
    # Get failing pods
    failing_pods = get_failing_pods(namespace, k8s_context)
    
    print(f"Found {len(failing_pods)} failing pods:")
    for pod in failing_pods:
        print(f"  - {pod.get('pod_name', 'unknown')}: {pod.get('reason', 'unknown')}")
    print()
    
    if failing_pods and SELF_HEALING_ENABLED:
        print("=" * 70)
        print("EXECUTING SELF-HEALING EVALUATION")
        print("=" * 70)
        print()
        
        # Run self-healing
        result = evaluate_and_heal(failing_pods, namespace, k8s_context)
        
        print(f"Summary: {result.get('summary', 'N/A')}")
        print()
        
        actions_taken = result.get('actions_taken', [])
        if actions_taken:
            print(f"Actions Executed: {len(actions_taken)}")
            for action in actions_taken:
                icon = "✓" if action.get('status') == 'success' else "⚠" if action.get('status') == 'dry_run' else "✗"
                print(f"\n  {icon} {action.get('action_type', 'Unknown')}")
                print(f"     Pod: {action.get('pod_name', 'N/A')}")
                print(f"     Status: {action.get('status', 'unknown')}")
                print(f"     Message: {action.get('message', 'N/A')}")
                
                # Show safety check details
                safety = action.get('safety_check', {})
                if safety:
                    print(f"     Safety: {safety.get('safe', False)} - {safety.get('reason', 'N/A')}")
        
        actions_skipped = result.get('actions_skipped', [])
        if actions_skipped:
            print(f"\nActions Skipped: {len(actions_skipped)}")
            for action in actions_skipped:
                print(f"\n  - {action.get('action_type', 'Unknown')}")
                print(f"    Pod: {action.get('pod_name', 'N/A')}")
                print(f"    Reason: {action.get('message', action.get('reason', 'N/A'))}")
        
        print()
        print("=" * 70)
    elif not failing_pods:
        print("No failing pods found - nothing to heal!")
    elif not SELF_HEALING_ENABLED:
        print("Self-healing is disabled - set SELF_HEALING_ENABLED=yes to enable")
        
except Exception as e:
    print(f"Error during pod detection/healing: {e}")
    import traceback
    traceback.print_exc()

print()
print("Test complete!")
print()
