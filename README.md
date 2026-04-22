<p align="center">
  <img src="assets/banner.svg" alt="K8s Copilot MCP" width="700">
</p>

# K8s Copilot MCP

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-1.0-green.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Give your LLM eyes into your Kubernetes cluster through the Model Context Protocol.**

Query pods, read logs, check deployments, inspect events — all through natural language. No more context-switching between `kubectl` and your AI assistant.

```
"Why is my pod crashing?"
  ↓
Claude/GPT → K8s Copilot MCP → kubectl API → Pod status + events + logs
  ↓
"Pod web-api-7f8d9 is in CrashLoopBackOff. Last log: 'connection refused on port 5432'.
 The postgres service in the same namespace has 0 ready endpoints."
```

## Quick Start

```bash
# Install
pip install k8s-copilot-mcp

# Or from source
git clone https://github.com/naveenkumarbaskaran/K8s-Copilot-MCP.git
cd K8s-Copilot-MCP
pip install -e .

# Run (uses ~/.kube/config by default)
k8s-mcp
```

### Claude Desktop Config

```json
{
  "mcpServers": {
    "kubernetes": {
      "command": "k8s-mcp",
      "args": ["--context", "my-cluster", "--namespaces", "default,staging"]
    }
  }
}
```

## Features

### Pod Operations

| Tool | Description |
|------|-------------|
| `list_pods` | List pods with status, restarts, age, node |
| `get_pod_details` | Full pod spec, conditions, container statuses |
| `get_pod_logs` | Stream/tail logs from any container |
| `get_previous_logs` | Logs from crashed/restarted containers |

### Deployment Operations

| Tool | Description |
|------|-------------|
| `list_deployments` | All deployments with replicas, ready count, age |
| `get_deployment_details` | Full spec, strategy, conditions |
| `get_rollout_status` | Current rollout progress |
| `get_deployment_history` | Revision history with change causes |

### Service & Networking

| Tool | Description |
|------|-------------|
| `list_services` | Services with type, cluster IP, external IP, ports |
| `get_endpoints` | Endpoint addresses for a service |
| `list_ingresses` | Ingress rules and backends |

### Events & Diagnostics

| Tool | Description |
|------|-------------|
| `get_events` | Cluster events filtered by namespace/resource/type |
| `get_node_status` | Node conditions, capacity, allocatable |
| `get_resource_usage` | CPU/memory requests vs limits vs actual |
| `diagnose_pod` | Auto-diagnosis: status + events + logs + related resources |

### Namespace Tools

| Tool | Description |
|------|-------------|
| `list_namespaces` | All namespaces |
| `get_namespace_resources` | Resource summary per namespace |

## Architecture

```
┌────────────────────────────────────────────┐
│               MCP Client                    │
│          (Claude, GPT, Cursor, etc.)        │
└────────────────────┬───────────────────────┘
                     │ MCP Protocol (stdio)
                     ▼
┌────────────────────────────────────────────┐
│           K8s Copilot MCP Server            │
│                                            │
│  ┌──────────────┐  ┌───────────────────┐  │
│  │   Auth        │  │   Tool Registry   │  │
│  │   Manager     │  │   (18 tools)      │  │
│  │  (kubeconfig  │  └────────┬──────────┘  │
│  │   in-cluster) │           │             │
│  └──────┬───────┘  ┌────────▼──────────┐  │
│         │          │   Response        │  │
│         │          │   Formatter       │  │
│         │          │   (tables, JSON)  │  │
│         │          └────────┬──────────┘  │
│         ▼                   │             │
│  ┌──────────────────────────▼──────────┐  │
│  │      Kubernetes Python Client        │  │
│  │      (kubernetes >= 29.0)            │  │
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
```

## Safety Features

### Read-Only by Default

The server only exposes **read** operations. No `kubectl apply`, no `kubectl delete`, no mutations. Your cluster is safe.

### Namespace Allowlisting

```bash
# Only expose pods/services from these namespaces
k8s-mcp --namespaces default,staging,production

# Deny specific namespaces
k8s-mcp --deny-namespaces kube-system,kube-public
```

### Log Truncation

Logs are automatically truncated to prevent context overflow:

```bash
# Default: last 100 lines
k8s-mcp --log-lines 100

# Custom limit  
k8s-mcp --log-lines 500
```

### Secret Redaction

Secrets are **never** returned in full. Only secret names and keys (not values) are shown:

```json
{
  "name": "db-credentials",
  "type": "Opaque",
  "keys": ["username", "password", "host"],
  "values": "[REDACTED]"
}
```

## Advanced Usage

### In-Cluster Mode

For running inside a Kubernetes cluster (e.g., as a sidecar):

```bash
k8s-mcp --in-cluster
```

Uses the service account token mounted at `/var/run/secrets/kubernetes.io/serviceaccount`.

### Multiple Contexts

```bash
# Use specific kubeconfig context
k8s-mcp --context production-cluster

# Use custom kubeconfig path
k8s-mcp --kubeconfig /path/to/kubeconfig
```

### Resource Filtering

```bash
# Only pod and deployment tools
k8s-mcp --resources pods,deployments

# Everything except secrets
k8s-mcp --deny-resources secrets
```

## Example Conversations

**"What's happening in the staging namespace?"**
→ `list_pods(namespace="staging")` + `get_events(namespace="staging", type="Warning")`

**"Why is the payment service unhealthy?"**
→ `diagnose_pod(namespace="production", label="app=payment-service")`

**"Show me the last deploy for the API gateway"**
→ `get_deployment_history(namespace="production", name="api-gateway")`

**"Which pods are using the most memory?"**
→ `get_resource_usage(namespace="all", sort_by="memory", top=10)`

## Testing

```bash
pytest tests/ -v

# Integration tests (requires running cluster)
pytest tests/test_integration.py -v --live
```

## License

MIT
