import { FormEvent, useState } from "react";
import { Network, RefreshCw, Search } from "lucide-react";

import type { GraphEntityDetail, GraphVisualization } from "../domain/models";
import { shortId } from "../utils/format";
import { Button } from "./Button";
import { GraphCanvas } from "./GraphCanvas";
import { Panel } from "./Panel";

interface GraphPanelProps {
  graph: GraphVisualization;
  selectedEntity: GraphEntityDetail | null;
  disabled: boolean;
  onRefresh: (query?: string) => void;
  onBuildGraph: () => void;
  onSelectEntity: (nodeId: string, label: string) => void;
}

export function GraphPanel({
  graph,
  selectedEntity,
  disabled,
  onRefresh,
  onBuildGraph,
  onSelectEntity,
}: GraphPanelProps) {
  const [query, setQuery] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onRefresh(query);
  }

  return (
    <Panel
      action={
        <Button
          disabled={disabled}
          icon={<Network className="h-4 w-4" />}
          onClick={onBuildGraph}
          variant="secondary"
        >
          Dựng
        </Button>
      }
      title="Knowledge Graph"
    >
      <form className="mb-3 flex gap-2" onSubmit={handleSubmit}>
        <input
          className="h-9 flex-1 rounded-md border border-line px-3 text-sm focus:border-cobalt focus:outline-none"
          placeholder="Tìm trong graph"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button
          disabled={disabled}
          icon={<Search className="h-4 w-4" />}
          type="submit"
          variant="secondary"
        >
          Tìm
        </Button>
        <Button
          disabled={disabled}
          icon={<RefreshCw className="h-4 w-4" />}
          onClick={() => onRefresh("")}
          type="button"
          variant="ghost"
        >
          Tất cả
        </Button>
      </form>
      <GraphCanvas graph={graph} onSelectNode={onSelectEntity} />
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted">
        <div className="rounded-md border border-line bg-canvas p-2">
          <span className="font-semibold text-ink">{graph.nodes.length}</span> nút
        </div>
        <div className="rounded-md border border-line bg-canvas p-2">
          <span className="font-semibold text-ink">{graph.edges.length}</span> cạnh
        </div>
      </div>
      {selectedEntity ? (
        <div className="mt-3 rounded-md border border-line bg-canvas p-3 text-sm">
          <div className="font-semibold text-ink">{selectedEntity.entity.canonical_name}</div>
          <div className="mt-1 text-muted">{selectedEntity.entity.description}</div>
          <div className="mt-2 text-xs text-muted">
            {selectedEntity.outgoing_relations.length} quan hệ đi |{" "}
            {selectedEntity.incoming_relations.length} quan hệ đến
          </div>
          {selectedEntity.outgoing_relations.slice(0, 4).map((relation) => (
            <div className="mt-2 rounded bg-white p-2 text-xs" key={relation.id}>
              <span className="font-semibold">{relation.predicate}</span>{" "}
              {relation.object_value}
              <div className="font-mono text-muted">{shortId(relation.evidence_id)}</div>
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}
