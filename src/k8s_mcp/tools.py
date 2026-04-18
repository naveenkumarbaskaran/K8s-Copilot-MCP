"""Kubernetes MCP tool implementations — all read-only."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from kubernetes.client import CoreV1Api, AppsV1Api, NetworkingV1Api

logger = logging.getLogger(__name__)

# Maximum log lines to return (prevents context overflow)
DEFAULT_LOG_LINES = 100
MAX_LOG_LINES = 1000


class K8sToolRegistry:
    """Registry of Kubernetes MCP tools — read-only operations."""

    def __init__(
        self,
        core_v1: CoreV1Api,
        apps_v1: AppsV1Api,
        networking_v1: NetworkingV1Api,
        allowed_namespaces: list[str] | None = None,
        denied_namespaces: list[str] | None = None,
        log_lines: int = DEFAULT_LOG_LINES,
    ):
        self.core = core_v1
        self.apps = apps_v1
        self.networking = networking_v1
        self.allowed_ns = allowed_namespaces
        self.denied_ns = denied_namespaces or ["kube-system", "kube-public"]
        self.log_lines = min(log_lines, MAX_LOG_LINES)

    def _check_namespace(self, namespace: str) -> None:
        """Enforce namespace allow/deny lists."""
        if self.allowed_ns and namespace not in self.allowed_ns:
            raise PermissionError(
                f"Namespace '{namespace}' is not in the allowlist"
            )
        if namespace in self.denied_ns:
            raise PermissionError(
                f"Namespace '{namespace}' is in the denylist"
            )

    # ── Pod Tools ───────────────────────────────────────────

    def list_pods(
        self,
        namespace: str = "default",
        label_selector: str | None = None,
        field_selector: str | None = None,
    ) -> list[dict[str, Any]]:
        """List pods with status, restarts, age, and node."""
        self._check_namespace(namespace)

        kwargs: dict[str, Any] = {}
        if label_selector:
            kwargs["label_selector"] = label_selector
        if field_selector:
            kwargs["field_selector"] = field_selector

        pods = self.core.list_namespaced_pod(namespace, **kwargs)
        results = []

        for pod in pods.items:
            restarts = 0
            ready_count = 0
            total = len(pod.spec.containers)

            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    restarts += cs.restart_count
                    if cs.ready:
                        ready_count += 1

            age = _format_age(pod.metadata.creation_timestamp)
            results.append({
                "name": pod.metadata.name,
                "namespace": namespace,
                "status": pod.status.phase,
                "ready": f"{ready_count}/{total}",
                "restarts": restarts,
                "age": age,
                "node": pod.spec.node_name or "Pending",
                "ip": pod.status.pod_ip or "None",
            })

        return results

    def get_pod_details(
        self, name: str, namespace: str = "default"
    ) -> dict[str, Any]:
        """Get full pod details including conditions and container statuses."""
        self._check_namespace(namespace)
        pod = self.core.read_namespaced_pod(name, namespace)

        containers = []
        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                state = "Unknown"
                reason = None
                if cs.state.running:
                    state = "Running"
                elif cs.state.waiting:
                    state = "Waiting"
                    reason = cs.state.waiting.reason
                elif cs.state.terminated:
                    state = "Terminated"
                    reason = cs.state.terminated.reason

                containers.append({
                    "name": cs.name,
                    "image": cs.image,
                    "state": state,
                    "reason": reason,
                    "restarts": cs.restart_count,
                    "ready": cs.ready,
                })

        conditions = []
        if pod.status.conditions:
            for c in pod.status.conditions:
                conditions.append({
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason,
                    "message": c.message,
                })

        return {
            "name": pod.metadata.name,
            "namespace": namespace,
            "phase": pod.status.phase,
            "node": pod.spec.node_name,
            "service_account": pod.spec.service_account_name,
            "containers": containers,
            "conditions": conditions,
            "labels": pod.metadata.labels or {},
            "created": str(pod.metadata.creation_timestamp),
        }

    def get_pod_logs(
        self,
        name: str,
        namespace: str = "default",
        container: str | None = None,
        tail_lines: int | None = None,
        since_seconds: int | None = None,
    ) -> str:
        """Get pod logs, truncated to prevent context overflow."""
        self._check_namespace(namespace)

        kwargs: dict[str, Any] = {}
        if container:
            kwargs["container"] = container
        kwargs["tail_lines"] = min(
            tail_lines or self.log_lines, MAX_LOG_LINES
        )
        if since_seconds:
            kwargs["since_seconds"] = since_seconds

        logs = self.core.read_namespaced_pod_log(name, namespace, **kwargs)
        return logs

    def get_previous_logs(
        self,
        name: str,
        namespace: str = "default",
        container: str | None = None,
    ) -> str:
        """Get logs from the previous (crashed) container instance."""
        self._check_namespace(namespace)

        kwargs: dict[str, Any] = {"previous": True}
        if container:
            kwargs["container"] = container
        kwargs["tail_lines"] = self.log_lines

        logs = self.core.read_namespaced_pod_log(name, namespace, **kwargs)
        return logs

    # ── Deployment Tools ────────────────────────────────────

    def list_deployments(
        self, namespace: str = "default"
    ) -> list[dict[str, Any]]:
        """List deployments with replica counts."""
        self._check_namespace(namespace)
        deploys = self.apps.list_namespaced_deployment(namespace)
        results = []

        for d in deploys.items:
            results.append({
                "name": d.metadata.name,
                "namespace": namespace,
                "ready": f"{d.status.ready_replicas or 0}/{d.spec.replicas or 0}",
                "up_to_date": d.status.updated_replicas or 0,
                "available": d.status.available_replicas or 0,
                "age": _format_age(d.metadata.creation_timestamp),
                "strategy": d.spec.strategy.type if d.spec.strategy else "Unknown",
            })

        return results

    def get_deployment_details(
        self, name: str, namespace: str = "default"
    ) -> dict[str, Any]:
        """Get full deployment details."""
        self._check_namespace(namespace)
        d = self.apps.read_namespaced_deployment(name, namespace)

        conditions = []
        if d.status.conditions:
            for c in d.status.conditions:
                conditions.append({
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason,
                    "message": c.message,
                })

        containers = []
        for c in d.spec.template.spec.containers:
            containers.append({
                "name": c.name,
                "image": c.image,
                "ports": [
                    {"container_port": p.container_port, "protocol": p.protocol}
                    for p in (c.ports or [])
                ],
            })

        return {
            "name": d.metadata.name,
            "replicas": d.spec.replicas,
            "ready_replicas": d.status.ready_replicas or 0,
            "strategy": d.spec.strategy.type if d.spec.strategy else None,
            "containers": containers,
            "conditions": conditions,
            "labels": d.metadata.labels or {},
            "selector": d.spec.selector.match_labels or {},
        }

    # ── Service Tools ───────────────────────────────────────

    def list_services(
        self, namespace: str = "default"
    ) -> list[dict[str, Any]]:
        """List services with type, IPs, and ports."""
        self._check_namespace(namespace)
        svcs = self.core.list_namespaced_service(namespace)
        results = []

        for s in svcs.items:
            ports = []
            for p in (s.spec.ports or []):
                ports.append(f"{p.port}/{p.protocol}")

            results.append({
                "name": s.metadata.name,
                "type": s.spec.type,
                "cluster_ip": s.spec.cluster_ip,
                "external_ip": _get_external_ip(s),
                "ports": ", ".join(ports),
                "age": _format_age(s.metadata.creation_timestamp),
            })

        return results

    def get_endpoints(
        self, name: str, namespace: str = "default"
    ) -> dict[str, Any]:
        """Get endpoint addresses for a service."""
        self._check_namespace(namespace)
        ep = self.core.read_namespaced_endpoints(name, namespace)

        addresses = []
        if ep.subsets:
            for subset in ep.subsets:
                for addr in (subset.addresses or []):
                    addresses.append({
                        "ip": addr.ip,
                        "target": addr.target_ref.name if addr.target_ref else None,
                    })

        return {
            "name": name,
            "namespace": namespace,
            "ready_addresses": len(addresses),
            "addresses": addresses,
        }

    # ── Events & Diagnostics ────────────────────────────────

    def get_events(
        self,
        namespace: str = "default",
        resource_name: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get cluster events, optionally filtered."""
        self._check_namespace(namespace)

        field_parts = []
        if resource_name:
            field_parts.append(f"involvedObject.name={resource_name}")
        if event_type:
            field_parts.append(f"type={event_type}")

        kwargs: dict[str, Any] = {"limit": limit}
        if field_parts:
            kwargs["field_selector"] = ",".join(field_parts)

        events = self.core.list_namespaced_event(namespace, **kwargs)
        results = []

        for e in events.items:
            results.append({
                "type": e.type,
                "reason": e.reason,
                "message": e.message,
                "object": f"{e.involved_object.kind}/{e.involved_object.name}",
                "count": e.count,
                "first_seen": str(e.first_timestamp),
                "last_seen": str(e.last_timestamp),
            })

        return results

    def diagnose_pod(
        self,
        name: str | None = None,
        namespace: str = "default",
        label: str | None = None,
    ) -> dict[str, Any]:
        """Auto-diagnose a pod: status + events + recent logs."""
        self._check_namespace(namespace)

        # Find pod by name or label
        if name:
            pod_detail = self.get_pod_details(name, namespace)
        elif label:
            pods = self.list_pods(namespace, label_selector=label)
            if not pods:
                return {"error": f"No pods found with label {label}"}
            name = pods[0]["name"]
            pod_detail = self.get_pod_details(name, namespace)
        else:
            return {"error": "Provide either 'name' or 'label'"}

        # Get events for this pod
        events = self.get_events(
            namespace, resource_name=name, limit=20
        )
        warning_events = [e for e in events if e["type"] == "Warning"]

        # Get last 30 lines of logs
        try:
            logs = self.get_pod_logs(name, namespace, tail_lines=30)
        except Exception as e:
            logs = f"[Could not retrieve logs: {e}]"

        # Build diagnosis
        issues: list[str] = []

        for c in pod_detail.get("containers", []):
            if c["state"] == "Waiting":
                issues.append(
                    f"Container '{c['name']}' is waiting: {c.get('reason', 'unknown')}"
                )
            if c["restarts"] > 5:
                issues.append(
                    f"Container '{c['name']}' has {c['restarts']} restarts (CrashLoopBackOff likely)"
                )

        for e in warning_events:
            issues.append(f"Warning: {e['reason']} — {e['message']}")

        return {
            "pod": pod_detail,
            "events": events[:10],
            "recent_logs": logs,
            "issues": issues,
            "issue_count": len(issues),
        }

    # ── Namespace Tools ─────────────────────────────────────

    def list_namespaces(self) -> list[dict[str, Any]]:
        """List all namespaces."""
        ns_list = self.core.list_namespace()
        return [
            {
                "name": ns.metadata.name,
                "status": ns.status.phase,
                "age": _format_age(ns.metadata.creation_timestamp),
            }
            for ns in ns_list.items
        ]


# ── Helpers ─────────────────────────────────────────────────


def _format_age(created: datetime | None) -> str:
    """Format a creation timestamp as a human-readable age."""
    if not created:
        return "Unknown"
    now = datetime.now(timezone.utc)
    delta = now - created.replace(tzinfo=timezone.utc)

    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60

    if days > 0:
        return f"{days}d{hours}h"
    if hours > 0:
        return f"{hours}h{minutes}m"
    return f"{minutes}m"


def _get_external_ip(service: Any) -> str:
    """Extract external IP from a service."""
    if service.spec.type == "LoadBalancer" and service.status.load_balancer.ingress:
        ingress = service.status.load_balancer.ingress[0]
        return ingress.ip or ingress.hostname or "Pending"
    if service.spec.external_i_ps:
        return ", ".join(service.spec.external_i_ps)
    return "None"
