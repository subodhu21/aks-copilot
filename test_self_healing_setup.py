#!/usr/bin/env python3
"""Quick test to verify self-healing setup"""

import os
import sys

print("=" * 60)
print("Self-Healing Setup Verification")
print("=" * 60)
print()

# Check 1: .env file exists
if os.path.exists(".env"):
    print("✓ .env file found")
    
    # Check if self-healing config exists
    with open(".env", "r") as f:
        env_content = f.read()
        if "SELF_HEALING_ENABLED" in env_content:
            print("✓ Self-healing configuration found in .env")
        else:
            print("✗ Self-healing configuration NOT found in .env")
            sys.exit(1)
else:
    print("✗ .env file not found")
    sys.exit(1)

print()

# Check 2: Load environment variables
from dotenv import load_dotenv
load_dotenv()

self_healing_enabled = os.getenv("SELF_HEALING_ENABLED", "no").strip().lower()
self_healing_mode = os.getenv("SELF_HEALING_MODE", "ask").strip().lower()
self_healing_dry_run = os.getenv("SELF_HEALING_DRY_RUN", "no").strip().lower()

print("Configuration:")
print(f"  SELF_HEALING_ENABLED: {self_healing_enabled}")
print(f"  SELF_HEALING_MODE: {self_healing_mode}")
print(f"  SELF_HEALING_DRY_RUN: {self_healing_dry_run}")
print()

# Check 3: Try importing self_healing module
try:
    import self_healing
    print("✓ self_healing module imported successfully")
except ImportError as e:
    print(f"✗ Failed to import self_healing module: {e}")
    sys.exit(1)

# Check 4: Try importing python-dateutil
try:
    from dateutil import parser as date_parser
    print("✓ python-dateutil module found")
except ImportError:
    print("✗ python-dateutil not installed")
    print("  Install with: pip install python-dateutil>=2.8.0")
    sys.exit(1)

print()

# Check 5: Verify self-healing functions exist
try:
    from self_healing import (
        evaluate_and_heal,
        get_self_healing_history,
        get_self_healing_stats,
        RestartCrashLoopPod,
        ScaleUpOnResourcePressure,
        RetryImagePull
    )
    print("✓ All self-healing functions available")
except ImportError as e:
    print(f"✗ Missing self-healing functions: {e}")
    sys.exit(1)

print()

# Check 6: Test state file creation
try:
    stats = get_self_healing_stats()
    print("✓ Self-healing state system working")
    print(f"  Current stats: {stats}")
except Exception as e:
    print(f"✗ Self-healing state system error: {e}")
    sys.exit(1)

print()
print("=" * 60)
print("✓ All checks passed! Self-healing is ready to use.")
print("=" * 60)
print()

if self_healing_dry_run == "yes":
    print("⚠️  DRY RUN MODE is enabled (safe for testing)")
    print("   Actions will be logged but not executed.")
    print()
    print("To enable live execution, edit .env and set:")
    print("   SELF_HEALING_DRY_RUN=no")
else:
    print("⚠️  LIVE EXECUTION MODE is enabled!")
    print("   Actions will be executed for real.")
    print()
    print("To test safely first, edit .env and set:")
    print("   SELF_HEALING_DRY_RUN=yes")

print()
print("Run the monitoring test:")
print("  C:\\Python311\\python.exe -u test_step1_monitoring.py")
print()
