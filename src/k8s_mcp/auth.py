"""Kubernetes authentication manager — kubeconfig and in-cluster."""

from __future__ import annotations

import logging
import os

from kubernetes import client, config
from kubernetes.client import CoreV1Api, AppsV1Api, NetworkingV1Api

logger = logging.getLogger(__name__)


class K8sAuthManager:
    """Manages Kubernetes API authentication."""

    def __init__(
        self,
        kubeconfig: str | None = None,
        context: str | None = None,
        in_cluster: bool = False,
    ):
        self.kubeconfig = kubeconfig
        self.context = context
        self.in_cluster = in_cluster
        self._core_v1: CoreV1Api | None = None
        self._apps_v1: AppsV1Api | None = None
        self._networking_v1: NetworkingV1Api | None = None

    def initialize(self) -> None:
        """Load kubeconfig or in-cluster config."""
        if self.in_cluster:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        else:
            config_file = self.kubeconfig or os.path.expanduser(
                "~/.kube/config"
            )
            config.load_kube_config(
                config_file=config_file,
                context=self.context,
            )
            logger.info(
                "Loaded kubeconfig from %s (context: %s)",
                config_file,
                self.context or "default",
            )

    @property
    def core_v1(self) -> CoreV1Api:
        """Core V1 API client (pods, services, namespaces, events)."""
        if self._core_v1 is None:
            self._core_v1 = CoreV1Api()
        return self._core_v1

    @property
    def apps_v1(self) -> AppsV1Api:
        """Apps V1 API client (deployments, statefulsets, daemonsets)."""
        if self._apps_v1 is None:
            self._apps_v1 = AppsV1Api()
        return self._apps_v1

    @property
    def networking_v1(self) -> NetworkingV1Api:
        """Networking V1 API client (ingresses)."""
        if self._networking_v1 is None:
            self._networking_v1 = NetworkingV1Api()
        return self._networking_v1

    def get_current_context(self) -> str:
        """Return the active kubeconfig context name."""
        try:
            _, context = config.list_kube_config_contexts()
            return context.get("name", "unknown")
        except Exception:
            return "in-cluster" if self.in_cluster else "unknown"
