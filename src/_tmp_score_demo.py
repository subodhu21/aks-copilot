"""Read-only demo: detect the live crashloop pod and print its actual
diagnosis confidence score + factor breakdown. Does NOT send notifications
or execute self-healing. Deleted after use.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from tools import detect_failing_pods, calculate_diagnosis_confidence, _classify_issue

result = detect_failing_pods("default", "aks-ai-agent-demo")
print(f"Failing pods detected: {result['failing_pods_count']}")
print("=" * 70)

for pod in result["failing_pods"]:
    print(f"\nPod: {pod['pod_name']}")
    print(f"Reason: {pod['reason']}")
    print(f"Restart Count: {pod['restart_count']}")
    print(f"Error logs (first 200 chars): {pod['error_logs'][:200]!r}")

    issue_category, action_owner = _classify_issue(pod["reason"], pod["error_logs"], is_repo_managed=False)
    print(f"Issue Category: {issue_category}")

    confidence = calculate_diagnosis_confidence(
        reason=pod["reason"],
        error_logs=pod["error_logs"],
        is_repo_managed=False,
        issue_category=issue_category,
        restart_count=pod["restart_count"],
    )

    print("-" * 70)
    print(f"CONFIDENCE SCORE: {confidence['score']}/100 ({confidence['level']})")
    print("Factor breakdown:")
    for f in confidence["factors"]:
        print(f"   {f}")
    print("-" * 70)
