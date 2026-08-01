from dotenv import load_dotenv
import os

load_dotenv()

dry_run_value = os.getenv('SELF_HEALING_DRY_RUN', 'NOT_SET')
print(f"SELF_HEALING_DRY_RUN from .env: {dry_run_value}")
print(f"Evaluated as boolean: {dry_run_value.strip().lower() == 'yes' if dry_run_value != 'NOT_SET' else 'N/A'}")

# Now check what self_healing module sees
from self_healing import SELF_HEALING_DRY_RUN
print(f"SELF_HEALING_DRY_RUN in module: {SELF_HEALING_DRY_RUN}")
