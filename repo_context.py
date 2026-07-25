#!/usr/bin/env python3
"""
Azure DevOps Repository Context Loader

Fetches Helm chart configuration and deployment details from your
Azure DevOps repository to provide accurate remediation steps.
Also supports creating branches, committing Helm fixes, and raising PRs.

Configuration:
- AZURE_DEVOPS_PAT: Personal Access Token (required for write operations)
- Context-to-repo mapping is defined in CONTEXT_REPO_MAP below.
"""

import os
import json
import base64
import requests
from datetime import datetime
from urllib.parse import quote

# Maps Kubernetes context names to their Azure DevOps repo details.
# org, project, repo — all other config (PAT, branch) is shared.
# In-process cache for repo tree listings — avoids repeated API calls within one run
_tree_cache: dict = {}

CONTEXT_REPO_MAP = {
    "ent-api-gw-west-eu-np-k8s":      ("techdatacorp", "Enterprise Distributed Development", "devops-api-gw"),
    "ent-api-gw-west-eu-p-k8s":       ("techdatacorp", "Enterprise Distributed Development", "devops-api-gw"),
    "fus2edge-west-eu-prod-k8s":       ("techdatacorp", "Enterprise Distributed Development", "devops"),
    "fus2edge-west-eu-nonprod-k8s":    ("techdatacorp", "Enterprise Distributed Development", "devops"),
    "s1integration-east-us-nonprod-k8s": ("techdatacorp", "StreamOne", "devops"),
    "s1integration-east-us-prod-k8s":   ("techdatacorp", "StreamOne", "devops"),
}

def _repo_config_for_context(k8s_context):
    """Return (org, project, repo) for a given k8s context, falling back to .env values."""
    if k8s_context and k8s_context in CONTEXT_REPO_MAP:
        return CONTEXT_REPO_MAP[k8s_context]
    # Fall back to .env
    return (
        os.getenv("AZURE_DEVOPS_ORG", "techdatacorp"),
        os.getenv("AZURE_DEVOPS_PROJECT", "Enterprise Distributed Development"),
        os.getenv("AZURE_DEVOPS_REPO", "devops-api-gw"),
    )


class AzureDevOpsRepoLoader:
    def __init__(self, k8s_context=None):
        self.org, self.project, self.repo = _repo_config_for_context(k8s_context)
        self.pat = os.getenv("AZURE_DEVOPS_PAT", "")
        self.base_url = f"https://dev.azure.com/{self.org}/{quote(self.project)}/_apis/git/repositories/{self.repo}"

    def _get_headers(self):
        """Get headers with authentication if PAT is provided"""
        headers = {"Content-Type": "application/json"}
        if self.pat:
            import base64
            auth = base64.b64encode(f":{self.pat}".encode()).decode()
            headers["Authorization"] = f"Basic {auth}"
        return headers
    
    def get_file_content(self, path, branch="master"):
        """Fetch raw file content from the repository."""
        try:
            url = (
                f"{self.base_url}/items?path={quote(path)}"
                f"&versionDescriptor.version={branch}&versionDescriptor.versionType=Branch"
                f"&api-version=7.0&$format=text"
            )
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            return f"Error fetching {path}: {str(e)}"

    def browse_tree(self, folder_path="/", branch="master"):
        """List all file paths in the repository."""
        cache_key = f"{self.base_url}::{branch}"
        if cache_key in _tree_cache:
            return _tree_cache[cache_key]
        try:
            url = (
                f"{self.base_url}/items?scopePath={quote(folder_path)}"
                f"&recursionLevel=full"
                f"&versionDescriptor.version={branch}&versionDescriptor.versionType=Branch"
                f"&api-version=7.0"
            )
            response = requests.get(url, headers=self._get_headers(), timeout=20)
            if response.status_code != 200:
                return []
            result = [
                item["path"] for item in response.json().get("value", [])
                if item.get("gitObjectType") == "blob"
            ]
            _tree_cache[cache_key] = result
            return result
        except Exception:
            return []

    def find_helm_values_path(self, deployment_name, namespace, branch="master"):
        """
        Search the repo tree to find the config file for a deployment in a given namespace.
        Returns the path of the best matching file.
        """
        all_files = self.browse_tree("/", branch)
        if all_files:
            env_files = [
                f for f in all_files
                if f"/env/{namespace}/" in f and f.endswith((".yaml", ".yml"))
            ]

            # 1. Exact filename match: <deployment_name>.yaml
            exact = [f for f in env_files if f.split("/")[-1].replace(".yaml", "").replace(".yml", "") == deployment_name]
            if exact:
                return exact[0]

            # 2. Filename starts with deployment name (e.g. api-gateway-portal → api-gateway)
            prefix = [f for f in env_files if f.split("/")[-1].startswith(deployment_name + ".") or f.split("/")[-1].startswith(deployment_name + "-")]
            # Prefer shortest (most specific) match
            if prefix:
                return sorted(prefix, key=lambda x: len(x))[0]

            # 3. Deployment name anywhere in path within that namespace
            broad = [f for f in env_files if deployment_name in f]
            if broad:
                return sorted(broad, key=lambda x: len(x))[0]

        # Fallback to repo convention path
        return f"/api-factory/02-k8s-services/env/{namespace}/services/{deployment_name}.yaml"

    def get_helm_values(self, deployment_name, namespace):
        """Fetch the config/values file for a deployment, using tree discovery."""
        path = self.find_helm_values_path(deployment_name, namespace)
        content = self.get_file_content(path)
        if content and not content.startswith("Error"):
            return {"path": path, "content": content}
        return None
    
    def get_helm_chart(self, deployment_name):
        """Fetch Helm Chart.yaml for a deployment"""
        possible_paths = [
            f"/helm/{deployment_name}/Chart.yaml",
            f"/charts/{deployment_name}/Chart.yaml",
        ]
        
        for path in possible_paths:
            content = self.get_file_content(path)
            if content and "Error" not in content:
                return {"path": path, "content": content}
        
        return None
    
    def get_deployment_config(self, deployment_name, namespace):
        """Fetch Kubernetes deployment configuration"""
        possible_paths = [
            f"/k8s/{namespace}/deployment-{deployment_name}.yaml",
            f"/k8s/{namespace}/{deployment_name}.yaml",
            f"/deployments/{namespace}/{deployment_name}.yaml",
        ]
        
        for path in possible_paths:
            content = self.get_file_content(path)
            if content and "Error" not in content:
                return {"path": path, "content": content}
        
        return None


    # ------------------------------------------------------------------ #
    #  WRITE OPERATIONS  (require AZURE_DEVOPS_PAT with write access)     #
    # ------------------------------------------------------------------ #

    def _require_pat(self):
        if not self.pat:
            raise ValueError(
                "AZURE_DEVOPS_PAT is required for write operations. "
                "Add it to your .env file."
            )

    def get_branch_ref(self, branch="master"):
        """Return the latest commit objectId for a branch."""
        self._require_pat()
        url = (
            f"{self.base_url}/refs"
            f"?filter=heads/{branch}&api-version=7.0"
        )
        response = requests.get(url, headers=self._get_headers(), timeout=10)
        response.raise_for_status()
        values = response.json().get("value", [])
        if not values:
            raise ValueError(f"Branch '{branch}' not found in repository.")
        return values[0]["objectId"]

    def create_branch(self, branch_name, from_branch="master"):
        """Create a new branch from an existing branch."""
        self._require_pat()
        base_oid = self.get_branch_ref(from_branch)
        url = f"{self.base_url}/refs?api-version=7.0"
        payload = [
            {
                "name": f"refs/heads/{branch_name}",
                "newObjectId": base_oid,
                "oldObjectId": "0000000000000000000000000000000000000000",
            }
        ]
        response = requests.post(url, headers=self._get_headers(), json=payload, timeout=10)
        response.raise_for_status()
        return {"branch": branch_name, "from": from_branch, "base_commit": base_oid}

    def commit_file(self, file_path, new_content, branch, commit_message, old_content=None):
        """Create or update a file on a branch via a push commit."""
        self._require_pat()
        base_oid = self.get_branch_ref(branch)

        # Determine change type: edit if file exists, add if new
        existing = self.get_file_content(file_path, branch)
        change_type = "edit" if existing and "Error" not in str(existing) else "add"

        url = f"{self.base_url}/pushes?api-version=7.0"
        payload = {
            "refUpdates": [
                {"name": f"refs/heads/{branch}", "oldObjectId": base_oid}
            ],
            "commits": [
                {
                    "comment": commit_message,
                    "changes": [
                        {
                            "changeType": change_type,
                            "item": {"path": file_path},
                            "newContent": {
                                "content": new_content,
                                "contentType": "rawtext",
                            },
                        }
                    ],
                }
            ],
        }
        response = requests.post(url, headers=self._get_headers(), json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def create_pull_request(self, source_branch, title, description, target_branch="master"):
        """Open a PR from source_branch into target_branch."""
        self._require_pat()
        url = f"{self.base_url}/pullrequests?api-version=7.0"
        payload = {
            "title": title,
            "description": description,
            "sourceRefName": f"refs/heads/{source_branch}",
            "targetRefName": f"refs/heads/{target_branch}",
        }
        response = requests.post(url, headers=self._get_headers(), json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        pr_id = data.get("pullRequestId")
        pr_url = (
            f"https://dev.azure.com/{self.org}/{quote(self.project)}"
            f"/_git/{self.repo}/pullrequest/{pr_id}"
        )
        return {"pr_id": pr_id, "url": pr_url, "title": title, "branch": source_branch}


def get_repo_context(pod_name, namespace, k8s_context=None):
    """Get Helm and deployment context from the correct Azure DevOps repo for the given k8s context."""
    loader = AzureDevOpsRepoLoader(k8s_context=k8s_context)

    # Extract deployment name from pod name (e.g., api-gateway-d455c65cd-kq8q4 -> api-gateway)
    deployment_name = "-".join(pod_name.split("-")[:-2])

    context = {
        "deployment_name": deployment_name,
        "namespace": namespace,
        "repo_url": f"https://dev.azure.com/{loader.org}/{quote(loader.project)}/_git/{loader.repo}",
    }

    # Fetch Helm values
    values = loader.get_helm_values(deployment_name, namespace)
    if values:
        context["helm_values"] = values

    # Fetch Chart.yaml
    chart = loader.get_helm_chart(deployment_name)
    if chart:
        context["helm_chart"] = chart

    # Fetch deployment config
    deployment = loader.get_deployment_config(deployment_name, namespace)
    if deployment:
        context["deployment_config"] = deployment
    
    return context


def format_repo_context_for_ai(repo_context):
    """Format repository context for AI analysis"""
    if not repo_context:
        return ""
    
    lines = ["\n## Repository Context from Azure DevOps"]
    lines.append(f"- Repository: {repo_context.get('repo_url')}")
    lines.append(f"- Deployment: {repo_context.get('deployment_name')}")
    lines.append(f"- Namespace: {repo_context.get('namespace')}")
    
    if "helm_chart" in repo_context:
        lines.append(f"\n### Helm Chart\nPath: {repo_context['helm_chart'].get('path')}")
        lines.append("```yaml\n" + repo_context['helm_chart'].get('content', '')[:500] + "\n```")
    
    if "helm_values" in repo_context:
        lines.append(f"\n### Helm Values\nPath: {repo_context['helm_values'].get('path')}")
        lines.append("```yaml\n" + repo_context['helm_values'].get('content', '')[:1000] + "\n```")
    
    if "deployment_config" in repo_context:
        lines.append(f"\n### Deployment Configuration\nPath: {repo_context['deployment_config'].get('path')}")
        lines.append("```yaml\n" + repo_context['deployment_config'].get('content', '')[:1000] + "\n```")
    
    return "\n".join(lines)
