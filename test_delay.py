#!/usr/bin/env python3
"""Quick test to verify the 1-minute delay is working"""

import os
from dotenv import load_dotenv

load_dotenv()

delay_seconds = int(os.getenv("SELF_HEALING_DELAY_SECONDS", "60"))

print("=" * 70)
print("Testing Self-Healing Delay Configuration")
print("=" * 70)
print()
print(f"Current Setting: SELF_HEALING_DELAY_SECONDS = {delay_seconds}")
print()

if delay_seconds == 60:
    print("✅ DEMO MODE: 1-minute delay configured")
    print()
    print("This will give you time to:")
    print("  1. Show the failure notification in Slack/Teams")
    print("  2. Explain what's happening in the dashboard")
    print("  3. Build anticipation for the auto-healing")
    print("  4. Watch the countdown")
    print("  5. See the healing execute")
elif delay_seconds == 0:
    print("⚡ PRODUCTION MODE: No delay (immediate healing)")
    print()
    print("Auto-healing will execute immediately after detection.")
    print("Best for 24/7 production operations.")
else:
    print(f"⏱️  CUSTOM MODE: {delay_seconds}-second delay")
    print()
    print(f"Auto-healing will wait {delay_seconds} seconds after notification.")

print()
print("=" * 70)
print("To change the delay, edit .env file:")
print("=" * 70)
print()
print("# For demo (1 minute wait):")
print("SELF_HEALING_DELAY_SECONDS=60")
print()
print("# For production (immediate):")
print("SELF_HEALING_DELAY_SECONDS=0")
print()
print("# For custom delay:")
print("SELF_HEALING_DELAY_SECONDS=120  # 2 minutes")
print()
