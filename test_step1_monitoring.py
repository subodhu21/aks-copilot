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
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")

print(f"\n{'='*50}")
print("All namespaces scanned.")
