"""
Azure Key Vault secret resolver.

Scans all environment variables for values prefixed with @keyvault:<secret-name>
and replaces them in-process with the real secret fetched from Azure Key Vault.

Usage:
    Set AZURE_KEY_VAULT_URL in your .env, then mark any secret env var like:
        AZURE_API_KEY=@keyvault:azure-api-key

    Call resolve_keyvault_refs() once at startup (done automatically by tools.py).
    All subsequent os.getenv() calls will return the resolved value.

Authentication:
    Uses DefaultAzureCredential — works with:
      - Azure CLI login (local dev: az login)
      - Managed Identity (AKS workload identity / pod identity)
      - Environment variables (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
"""
import os


def resolve_keyvault_refs() -> None:
    """Resolve all @keyvault:<name> env var values from Azure Key Vault."""
    vault_url = os.getenv("AZURE_KEY_VAULT_URL", "").strip()
    if not vault_url:
        return

    refs = {
        k: v for k, v in os.environ.items()
        if isinstance(v, str) and v.startswith("@keyvault:")
    }
    if not refs:
        return

    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())

        for env_key, ref_value in refs.items():
            secret_name = ref_value[len("@keyvault:"):]
            try:
                secret = client.get_secret(secret_name)
                os.environ[env_key] = secret.value
                print(f"[keyvault] Resolved {env_key} from secret '{secret_name}'")
            except Exception as e:
                # Keep the warning short — suppress verbose credential chain output
                msg = str(e).split("\n")[0]
                print(f"[keyvault] WARNING: Could not resolve {env_key}: {msg}")

    except ImportError:
        print(
            "[keyvault] WARNING: azure-keyvault-secrets / azure-identity not installed. "
            "Run: pip install azure-keyvault-secrets azure-identity"
        )
    except Exception as e:
        msg = str(e).split("\n")[0]
        print(f"[keyvault] WARNING: Key Vault unavailable: {msg}")
