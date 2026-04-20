"""Tests for K8s MCP tool registry."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from k8s_mcp.tools import K8sToolRegistry, _format_age


class TestFormatAge:
    """Test age formatting helper."""

    def test_minutes(self):
        now = datetime.now(timezone.utc)
        created = now - timedelta(minutes=5)
        assert _format_age(created) == "5m"

    def test_hours(self):
        now = datetime.now(timezone.utc)
        created = now - timedelta(hours=3, minutes=15)
        assert _format_age(created) == "3h15m"

    def test_days(self):
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=7, hours=2)
        assert _format_age(created) == "7d2h"

    def test_none(self):
        assert _format_age(None) == "Unknown"


class TestNamespaceGuard:
    """Test namespace allow/deny enforcement."""

    def _make_registry(
        self, allowed=None, denied=None
    ) -> K8sToolRegistry:
        return K8sToolRegistry(
            core_v1=MagicMock(),
            apps_v1=MagicMock(),
            networking_v1=MagicMock(),
            allowed_namespaces=allowed,
            denied_namespaces=denied or [],
        )

    def test_allowed_namespace_passes(self):
        reg = self._make_registry(allowed=["staging", "default"])
        reg._check_namespace("staging")  # Should not raise

    def test_disallowed_namespace_blocked(self):
        reg = self._make_registry(allowed=["staging"])
        with pytest.raises(PermissionError, match="not in the allowlist"):
            reg._check_namespace("production")

    def test_denied_namespace_blocked(self):
        reg = self._make_registry(denied=["kube-system"])
        with pytest.raises(PermissionError, match="denylist"):
            reg._check_namespace("kube-system")

    def test_no_restrictions_passes(self):
        reg = self._make_registry(allowed=None, denied=[])
        reg._check_namespace("anything")  # Should not raise


class TestListPods:
    """Test pod listing tool."""

    def _make_pod_item(self, name, phase, restarts=0, ready=True):
        pod = MagicMock()
        pod.metadata.name = name
        pod.metadata.creation_timestamp = datetime.now(timezone.utc) - timedelta(hours=2)
        pod.status.phase = phase
        pod.status.pod_ip = "10.0.0.1"
        pod.spec.node_name = "node-1"
        pod.spec.containers = [MagicMock(), MagicMock()]

        cs = MagicMock()
        cs.restart_count = restarts
        cs.ready = ready
        pod.status.container_statuses = [cs, cs]

        return pod

    def test_list_pods_basic(self):
        core = MagicMock()
        pod_list = MagicMock()
        pod_list.items = [
            self._make_pod_item("web-1", "Running"),
            self._make_pod_item("web-2", "Pending", restarts=3, ready=False),
        ]
        core.list_namespaced_pod.return_value = pod_list

        reg = K8sToolRegistry(
            core_v1=core,
            apps_v1=MagicMock(),
            networking_v1=MagicMock(),
            denied_namespaces=[],
        )
        result = reg.list_pods(namespace="default")

        assert len(result) == 2
        assert result[0]["name"] == "web-1"
        assert result[0]["status"] == "Running"
        assert result[1]["restarts"] == 6  # 3 per container × 2 containers

    def test_list_pods_with_label_selector(self):
        core = MagicMock()
        pod_list = MagicMock()
        pod_list.items = []
        core.list_namespaced_pod.return_value = pod_list

        reg = K8sToolRegistry(
            core_v1=core,
            apps_v1=MagicMock(),
            networking_v1=MagicMock(),
            denied_namespaces=[],
        )
        reg.list_pods(namespace="default", label_selector="app=nginx")
        core.list_namespaced_pod.assert_called_once_with(
            "default", label_selector="app=nginx"
        )


class TestDiagnose:
    """Test the diagnose_pod composite tool."""

    def test_diagnose_no_args_returns_error(self):
        reg = K8sToolRegistry(
            core_v1=MagicMock(),
            apps_v1=MagicMock(),
            networking_v1=MagicMock(),
            denied_namespaces=[],
        )
        result = reg.diagnose_pod(namespace="default")
        assert "error" in result
