#!/usr/bin/env python3
"""
Helm Chart Information for AKS Pod Monitoring

This file stores metadata about your Helm deployments so the AI can
provide accurate, deployment-specific remediation steps.

Configure this once, and the monitoring agent will use it for all pods.
"""

HELM_REPOS = {
    "api-gateway": {
        "namespace": "int",
        "chart": "api-gateway",
        "release_name": "api-gateway",
        "values_file": "values-int.yaml",  # Path to your values file
        "repo_url": "https://your-helm-repo.com/charts",  # Your Helm repo
        "critical_env_vars": [
            "GATEWAY_ENVIRONMENT",
            "ENVIRONMENT",
            "MONGO_CONNECTION_STRING",
            "MONGO_HOST",
            "MONGO_PORT",
        ],
        "config_maps": [
            "api-gateway-config",
        ],
        "secrets": [
            "api-gateway-secrets",
        ],
    },
    # Add more deployments as needed
    # "other-service": {
    #     "namespace": "other-ns",
    #     "chart": "other-service",
    #     ...
    # }
}

def get_helm_metadata(pod_name, namespace):
    """Get Helm metadata for a pod"""
    for key, config in HELM_REPOS.items():
        if key in pod_name or pod_name.startswith(key):
            return config
    # Return None if no matching config found
    return None

def get_helm_context(pod_name, namespace):
    """Get formatted Helm context for AI analysis"""
    metadata = get_helm_metadata(pod_name, namespace)
    if not metadata:
        return ""
    
    return f"""
## Helm Deployment Context
- Chart: {metadata.get('chart')}
- Release: {metadata.get('release_name')}
- Namespace: {metadata.get('namespace')}
- Values File: {metadata.get('values_file')}
- Critical Environment Variables: {', '.join(metadata.get('critical_env_vars', []))}
- ConfigMaps: {', '.join(metadata.get('config_maps', []))}
- Secrets: {', '.join(metadata.get('secrets', []))}
"""
