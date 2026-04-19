"""MCP server wrapper for Kubernetes tools."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from k8s_mcp.auth import K8sAuthManager
from k8s_mcp.tools import K8sToolRegistry

logger = logging.getLogger(__name__)

# Tool definitions for MCP
TOOL_DEFINITIONS = [
    {
        "name": "list_pods",
        "description": "List pods in a namespace with status, restarts, age, and node",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "default"},
                "label_selector": {"type": "string", "description": "Label filter (e.g., 'app=nginx')"},
                "field_selector": {"type": "string", "description": "Field filter"},
            },
        },
    },
    {
        "name": "get_pod_details",
        "description": "Get full pod details: containers, conditions, labels, events",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "default": "default"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_pod_logs",
        "description": "Get logs from a pod (auto-truncated to prevent overflow)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "default": "default"},
                "container": {"type": "string", "description": "Specific container name"},
                "tail_lines": {"type": "integer", "description": "Number of lines from the end (default: 100)"},
                "since_seconds": {"type": "integer", "description": "Only logs newer than N seconds"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_previous_logs",
        "description": "Get logs from a crashed/restarted container's previous instance",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "default": "default"},
                "container": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_deployments",
        "description": "List deployments with replica counts, strategy, and age",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "default"},
            },
        },
    },
    {
        "name": "get_deployment_details",
        "description": "Get full deployment spec, containers, conditions, and selector",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Deployment name"},
                "namespace": {"type": "string", "default": "default"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_services",
        "description": "List services with type, cluster IP, external IP, and ports",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "default"},
            },
        },
    },
    {
        "name": "get_endpoints",
        "description": "Get endpoint addresses for a service (shows which pods back it)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Service name"},
                "namespace": {"type": "string", "default": "default"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_events",
        "description": "Get cluster events filtered by namespace, resource, or type (Warning/Normal)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "default"},
                "resource_name": {"type": "string", "description": "Filter by resource name"},
                "event_type": {"type": "string", "enum": ["Warning", "Normal"]},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "diagnose_pod",
        "description": "Auto-diagnose a pod: status + events + recent logs + issues summary",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "default": "default"},
                "label": {"type": "string", "description": "Label selector (alternative to name)"},
            },
        },
    },
    {
        "name": "list_namespaces",
        "description": "List all namespaces with status and age",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class K8sMCPServer:
    """MCP server that exposes Kubernetes read-only tools."""

    def __init__(
        self,
        auth_manager: K8sAuthManager,
        allowed_namespaces: list[str] | None = None,
        denied_namespaces: list[str] | None = None,
        log_lines: int = 100,
    ):
        self.auth = auth_manager
        self.allowed_ns = allowed_namespaces
        self.denied_ns = denied_namespaces
        self.log_lines = log_lines
        self.registry: K8sToolRegistry | None = None

    def initialize(self) -> None:
        """Initialize Kubernetes connection and tool registry."""
        self.auth.initialize()
        self.registry = K8sToolRegistry(
            core_v1=self.auth.core_v1,
            apps_v1=self.auth.apps_v1,
            networking_v1=self.auth.networking_v1,
            allowed_namespaces=self.allowed_ns,
            denied_namespaces=self.denied_ns,
            log_lines=self.log_lines,
        )
        logger.info("K8s MCP Server initialized (context: %s)", self.auth.get_current_context())

    def get_tools(self) -> list[dict]:
        """Return MCP tool definitions."""
        return TOOL_DEFINITIONS

    def handle_tool_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Execute a tool call."""
        if self.registry is None:
            return {"error": "Server not initialized"}

        method = getattr(self.registry, tool_name, None)
        if method is None:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return method(**arguments)
        except PermissionError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.exception("Tool call failed: %s", tool_name)
            return {"error": f"Failed: {type(e).__name__}: {e}"}
