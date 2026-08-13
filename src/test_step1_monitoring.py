#!/usr/bin/env python3
"""Test Step 1: Monitor and Notify Failures"""

import os
from dotenv import load_dotenv
load_dotenv()

from agent import monitor_and_notify_failures

print("Testing Step 1: Monitor and Notify Failures")
print("=" * 50)

NAMESPACES = [os.getenv("K8S_NAMESPACE", "default")]

for namespace in NAMESPACES:
    print(f"\n{'='*50}")
    print(f"Namespace: {namespace.upper()}")
    print(f"{'='*50}")

    result = monitor_and_notify_failures(namespace)  # uses K8S_CONTEXT and RAISE_PR from .env

    print(f"Status: {result['status']}")
    print(f"Summary: {result['summary']}")

    if result["status"] == "success":
        detection = result["data"]["detection"]
        print(f"Failing pods detected: {detection['failing_pods_count']}")

        if detection["failing_pods"]:
            print("\nFailing pods:")
            for pod in detection["failing_pods"][:3]:
                print(f"  - {pod['pod_name']}: {pod['reason']}")
        else:
            print("No failing pods detected (good news!)")

        notifications = result["data"]["notifications"]
        print(f"\nNotifications sent/attempted: {len(notifications)}")
        for notif in notifications:
            if isinstance(notif, dict):
                print(f"  - Status: {notif.get('status', 'unknown')}")
                print(f"    Message: {notif.get('message', notif.get('error', 'N/A'))}")
                confidence = notif.get("confidence")
                if confidence:
                    print(f"    Diagnosis Confidence: {confidence.get('score')}/100 ({confidence.get('level')})")

        pr_results = result["data"].get("pr_results", [])
        if pr_results:
            print(f"\nPRs raised: {len(pr_results)}")
            for pr in pr_results:
                if isinstance(pr, dict):
                    if pr.get("status") == "success":
                        print(f"  - PR #{pr.get('pr_id')}: {pr.get('pr_url')}")
                        print(f"    Branch: {pr.get('branch')}")
                    elif pr.get("status") == "skipped":
                        print(f"  - Skipped (system pod): {pr.get('summary', pr.get('reason', ''))}")
                    else:
                        print(f"  - PR failed: {pr.get('error', 'unknown error')}")

        # Display self-healing results
        self_healing = result["data"].get("self_healing")
        if self_healing:
            print(f"\n{'='*50}")
            print("SELF-HEALING ACTIONS")
            print(f"{'='*50}")
            print(f"Enabled: {self_healing.get('enabled', False)}")
            print(f"Mode: {self_healing.get('mode', 'unknown')}")
            print(f"Dry Run: {self_healing.get('dry_run', False)}")
            print(f"Summary: {self_healing.get('summary', 'N/A')}")
            
            actions_taken = self_healing.get("actions_taken", [])
            if actions_taken:
                print(f"\nActions Executed: {len(actions_taken)}")
                for action in actions_taken:
                    status_icon = "✓" if action.get("status") == "success" else "⚠"
                    print(f"  {status_icon} {action.get('action_type', 'Unknown')}")
                    print(f"    Pod: {action.get('pod_name', 'N/A')}")
                    print(f"    Status: {action.get('status', 'unknown')}")
                    print(f"    Message: {action.get('message', 'N/A')}")
                    confidence = action.get("confidence")
                    if confidence:
                        print(f"    Confidence: {confidence.get('score')}/100 ({confidence.get('level')})")
            
            actions_skipped = self_healing.get("actions_skipped", [])
            if actions_skipped:
                print(f"\nActions Skipped: {len(actions_skipped)}")
                for action in actions_skipped:
                    print(f"  - {action.get('action_type', 'Unknown')}")
                    print(f"    Pod: {action.get('pod_name', 'N/A')}")
                    print(f"    Reason: {action.get('message', action.get('reason', 'N/A'))}")
                    confidence = action.get("confidence")
                    if confidence:
                        print(f"    Confidence: {confidence.get('score')}/100 ({confidence.get('level')})")
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")

print(f"\n{'='*50}")
print("All namespaces scanned.")
