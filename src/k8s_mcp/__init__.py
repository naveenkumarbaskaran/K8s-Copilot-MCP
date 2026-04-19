"""K8s Copilot MCP — Give your LLM eyes into your Kubernetes cluster."""

__version__ = "0.1.0"

from k8s_mcp.server import K8sMCPServer
from k8s_mcp.auth import K8sAuthManager
from k8s_mcp.tools import K8sToolRegistry

__all__ = ["K8sMCPServer", "K8sAuthManager", "K8sToolRegistry"]
