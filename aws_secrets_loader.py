"""
AWS Secrets Manager secret resolver.

Scans all environment variables for values prefixed with @awssecret: and
replaces them in-process with the real secret fetched from AWS Secrets Manager.

Format:
    @awssecret:<secret-name>              — plain string secret
    @awssecret:<secret-name>:<json-key>   — extract a key from a JSON secret

Usage:
    Mark any secret env var in .env like:
        AWS_ACCESS_KEY_ID=@awssecret:ai-copilot:AWS_ACCESS_KEY_ID
        AWS_SECRET_ACCESS_KEY=@awssecret:ai-copilot:AWS_SECRET_ACCESS_KEY

    Set AWS_SECRETS_REGION to override the region (defaults to AWS_REGION).
    Call resolve_aws_secret_refs() once at startup (done automatically by tools.py).

Authentication:
    Uses the standard boto3 credential chain:
      - AWS SSO profile (set AWS_PROFILE=<profile-name>)
      - Environment variables (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
      - ~/.aws/credentials file
      - IAM role (EC2 / ECS / EKS pod identity)
"""
import os
import json

_PREFIX = "@awssecret:"


def resolve_aws_secret_refs() -> None:
    """Resolve all @awssecret:<name>[:<key>] env var values from AWS Secrets Manager."""
    refs = {
        k: v for k, v in os.environ.items()
        if isinstance(v, str) and v.startswith(_PREFIX)
    }
    if not refs:
        return

    region = os.getenv("AWS_SECRETS_REGION", "") or os.getenv("AWS_REGION", "us-east-1")
    profile = os.getenv("AWS_PROFILE", "").strip() or None

    try:
        import boto3

        session = boto3.Session(profile_name=profile, region_name=region)
        client = session.client("secretsmanager")

        # Cache fetched secrets so we only call GetSecretValue once per secret name
        _cache = {}

        for env_key, ref_value in refs.items():
            ref_body = ref_value[len(_PREFIX):]  # e.g. "ai-copilot:AWS_ACCESS_KEY_ID"
            parts = ref_body.split(":", 1)
            secret_name = parts[0]
            json_key = parts[1] if len(parts) > 1 else None

            try:
                # Fetch (or reuse cached) secret value
                if secret_name not in _cache:
                    response = client.get_secret_value(SecretId=secret_name)
                    _cache[secret_name] = response.get("SecretString", "")

                secret_string = _cache[secret_name]

                # Extract a specific key from a JSON secret
                if json_key:
                    secret_obj = json.loads(secret_string)
                    if isinstance(secret_obj, dict) and json_key in secret_obj:
                        secret_string = secret_obj[json_key]
                    else:
                        print(f"[awssecret] WARNING: Key '{json_key}' not found in secret '{secret_name}'")
                        continue

                os.environ[env_key] = secret_string
                label = f"{secret_name}:{json_key}" if json_key else secret_name
                print(f"[awssecret] Resolved {env_key} from secret '{label}'")
            except Exception as e:
                print(f"[awssecret] WARNING: Could not fetch secret '{secret_name}' for {env_key}: {e}")

    except ImportError:
        print(
            "[awssecret] WARNING: boto3 not installed. "
            "Run: pip install boto3"
        )
    except Exception as e:
        print(f"[awssecret] WARNING: Failed to connect to AWS Secrets Manager (region={region}): {e}")
