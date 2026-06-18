import type { GraphVisualization } from "../domain/models";

interface GraphCanvasProps {
  graph: GraphVisualization;
  onSelectNode: (nodeId: string, label: string) => void;
}

interface PositionedNode {
  id: string;
  label: string;
  node_type: string;
  x: number;
  y: number;
}

export function GraphCanvas({ graph, onSelectNode }: GraphCanvasProps) {
  const nodes = layoutNodes(graph);
  const nodeById = new Map(nodes.map((node) => [node.id, node]));

  if (graph.nodes.length === 0) {
    return (
      <div className="flex h-[360px] items-center justify-center rounded-md border border-line bg-canvas text-sm text-muted">
        Hãy dựng graph hoặc tìm kiếm để hiển thị các quan hệ.
      </div>
    );
  }

  return (
    <svg
      aria-label="Biểu đồ knowledge graph"
      className="h-[360px] w-full rounded-md border border-line bg-canvas"
      role="img"
      viewBox="0 0 720 360"
    >
      {graph.edges.map((edge) => {
        const source = nodeById.get(edge.source);
        const target = nodeById.get(edge.target);
        if (!source || !target) {
          return null;
        }
        const midX = (source.x + target.x) / 2;
        const midY = (source.y + target.y) / 2;
        return (
          <g key={edge.id}>
            <line
              stroke="#8a9388"
              strokeWidth="1.4"
              x1={source.x}
              x2={target.x}
              y1={source.y}
              y2={target.y}
            />
            <text
              className="fill-muted text-[10px]"
              textAnchor="middle"
              x={midX}
              y={midY - 5}
            >
              {truncate(edge.label, 22)}
            </text>
          </g>
        );
      })}
      {nodes.map((node) => (
        <g
          className="cursor-pointer"
          key={node.id}
          onClick={() => onSelectNode(node.id, node.label)}
        >
          <circle
            className={node.node_type === "entity" ? "fill-forest" : "fill-cobalt"}
            cx={node.x}
            cy={node.y}
            r={node.node_type === "entity" ? 17 : 13}
          />
          <text
            className="fill-ink text-[11px] font-medium"
            textAnchor="middle"
            x={node.x}
            y={node.y + 31}
          >
            {truncate(node.label, 24)}
          </text>
        </g>
      ))}
    </svg>
  );
}

function layoutNodes(graph: GraphVisualization): PositionedNode[] {
  const centerX = 360;
  const centerY = 180;
  const radiusX = 260;
  const radiusY = 120;
  return graph.nodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(graph.nodes.length, 1) - Math.PI / 2;
    return {
      ...node,
      x: Math.round(centerX + Math.cos(angle) * radiusX),
      y: Math.round(centerY + Math.sin(angle) * radiusY),
    };
  });
}

function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 1)}...`;
}
