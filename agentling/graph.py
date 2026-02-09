from __future__ import annotations

from collections import defaultdict, deque

from agentling.models import GraphConfig, NodeSpec


class GraphValidationError(ValueError):
    pass


class AgentGraph:
    def __init__(self, config: GraphConfig) -> None:
        self.nodes: dict[str, NodeSpec] = {n.id: n for n in config.nodes if n.enabled}
        self._validate()

    def _validate(self) -> None:
        for node in self.nodes.values():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    raise GraphValidationError(f"Node '{node.id}' depends on missing node '{dep}'")
        self.topological_order()

    def topological_order(self) -> list[str]:
        indegree = {node_id: 0 for node_id in self.nodes}
        edges: dict[str, list[str]] = defaultdict(list)

        for node in self.nodes.values():
            for dep in node.depends_on:
                edges[dep].append(node.id)
                indegree[node.id] += 1

        q = deque([node_id for node_id, degree in indegree.items() if degree == 0])
        ordered: list[str] = []
        while q:
            n = q.popleft()
            ordered.append(n)
            for neighbor in edges[n]:
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    q.append(neighbor)

        if len(ordered) != len(self.nodes):
            raise GraphValidationError("Cycle detected in agent graph")
        return ordered

    def ready_nodes(self, completed: set[str], scheduled: set[str]) -> list[NodeSpec]:
        ready: list[NodeSpec] = []
        for node in self.nodes.values():
            if node.id in completed or node.id in scheduled:
                continue
            if all(dep in completed for dep in node.depends_on):
                ready.append(node)
        return ready
