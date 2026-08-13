#!/usr/bin/env python3
"""View detailed self-healing statistics and history"""

import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from self_healing import (
    get_self_healing_history,
    get_self_healing_stats,
    SELF_HEALING_ENABLED,
    SELF_HEALING_MODE,
    SELF_HEALING_DRY_RUN,
    SELF_HEALING_MAX_ACTIONS_PER_HOUR
)

print("=" * 80)
print("SELF-HEALING STATISTICS & HISTORY VIEWER")
print("=" * 80)
print()

# Configuration
print("Current Configuration:")
print(f"  Enabled: {SELF_HEALING_ENABLED}")
print(f"  Mode: {SELF_HEALING_MODE}")
print(f"  Dry Run: {SELF_HEALING_DRY_RUN}")
print(f"  Max Actions/Hour: {SELF_HEALING_MAX_ACTIONS_PER_HOUR}")
print()

# Statistics
print("=" * 80)
print("STATISTICS")
print("=" * 80)
stats = get_self_healing_stats()

print(f"\nOverall:")
print(f"  Total Actions: {stats['total_actions']}")
print(f"  Successful: {stats['successful']}")
print(f"  Failed: {stats['failed']}")
print(f"  Success Rate: {stats['success_rate']}")
print(f"  Recent Hour: {stats['recent_hour_count']} actions")
print(f"  Rate Limit Status: {stats['rate_limit']}")

print(f"\nBy Action Type:")
for action_type, counts in stats['by_action_type'].items():
    print(f"  {action_type}:")
    print(f"    Total: {counts['total']}")
    print(f"    Success: {counts['success']}")
    print(f"    Failed: {counts['failed']}")
    success_rate = (counts['success'] / counts['total'] * 100) if counts['total'] > 0 else 0
    print(f"    Success Rate: {success_rate:.1f}%")

# History
print()
print("=" * 80)
print("ACTION HISTORY (Last 20 Actions)")
print("=" * 80)

history = get_self_healing_history(limit=20)

if not history:
    print("\nNo actions in history yet.")
else:
    for i, action in enumerate(history, 1):
        # Format timestamp
        timestamp = action.get('timestamp')
        if isinstance(timestamp, (int, float)):
            dt = datetime.fromtimestamp(timestamp)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = str(timestamp)
        
        # Status icon
        status = action.get('status', 'unknown')
        if status == 'success':
            icon = '✓'
            color = ''
        elif status == 'dry_run':
            icon = '⚠'
            color = ''
        elif status in ['failed', 'error']:
            icon = '✗'
            color = ''
        elif status == 'rejected':
            icon = '○'
            color = ''
        else:
            icon = '?'
            color = ''
        
        print(f"\n{i}. [{time_str}] {icon} {action.get('action_type', 'Unknown')}")
        print(f"   Pod: {action.get('pod_name', 'N/A')}")
        print(f"   Namespace: {action.get('namespace', 'N/A')}")
        print(f"   Status: {status}")
        print(f"   Dry Run: {action.get('dry_run', False)}")
        
        # Safety check
        safety = action.get('safety_check', {})
        if safety:
            safe = safety.get('safe', False)
            reason = safety.get('reason', 'N/A')
            print(f"   Safety Check: {'PASS' if safe else 'FAIL'} - {reason}")

        # Confidence score
        confidence = action.get('confidence', {})
        if confidence:
            print(f"   Confidence: {confidence.get('score', 'N/A')}/100 ({confidence.get('level', 'N/A')})")

        # Message
        message = action.get('message', 'N/A')
        if len(message) > 100:
            message = message[:97] + "..."
        print(f"   Message: {message}")
        
        # Execution details
        if 'execution' in action:
            exec_result = action['execution']
            print(f"   Execution: {'Success' if exec_result.get('success') else 'Failed'}")
        
        # Verification details
        if 'verification' in action:
            verify_result = action['verification']
            print(f"   Verification: {'Pass' if verify_result.get('verified') else 'Fail'}")

print()
print("=" * 80)
print("END OF REPORT")
print("=" * 80)
print()

# Rate limit warning
if stats['recent_hour_count'] >= SELF_HEALING_MAX_ACTIONS_PER_HOUR * 0.8:
    print("⚠️  WARNING: Approaching rate limit!")
    print(f"   {stats['recent_hour_count']}/{SELF_HEALING_MAX_ACTIONS_PER_HOUR} actions in last hour")
    print()

# Recommendations
if stats['total_actions'] > 0:
    success_pct = (stats['successful'] / stats['total_actions']) * 100
    
    if success_pct < 50:
        print("⚠️  Low success rate detected!")
        print("   Review failed actions and check RBAC permissions, connectivity.")
    elif success_pct < 80:
        print("ℹ️  Moderate success rate.")
        print("   Some actions are failing - review history for patterns.")
    else:
        print("✓ Good success rate!")
        print("  Self-healing is working well.")
    print()
