import { AlertTriangle, RefreshCw } from "lucide-react";

import type { Contradiction } from "../domain/models";
import { shortId } from "../utils/format";
import { Button } from "./Button";
import { Panel } from "./Panel";

interface ContradictionsPanelProps {
  contradictions: Contradiction[];
  disabled: boolean;
  onRefresh: () => void;
}

export function ContradictionsPanel({
  contradictions,
  disabled,
  onRefresh,
}: ContradictionsPanelProps) {
  return (
    <Panel
      action={
        <Button disabled={disabled} icon={<RefreshCw className="h-4 w-4" />} onClick={onRefresh} variant="ghost">
          Làm mới
        </Button>
      }
      title="Mâu thuẫn"
    >
      <div className="max-h-64 space-y-2 overflow-auto pr-1">
        {contradictions.length === 0 ? (
          <div className="rounded-md border border-line bg-canvas p-3 text-sm text-muted">
            Không có mâu thuẫn đang mở.
          </div>
        ) : (
          contradictions.map((item) => (
            <article className="rounded-md border border-line bg-canvas p-3" key={item.id}>
              <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-rose">
                <AlertTriangle className="h-4 w-4" />
                {item.relationship}
                <span className="ml-auto text-xs font-normal">
                  {Math.round(item.confidence * 100)}%
                </span>
              </div>
              <p className="text-sm text-ink">{item.reason}</p>
              <div className="mt-2 text-xs text-muted">
                {shortId(item.claim_a_id)} <span className="mx-1">/</span>{" "}
                {shortId(item.claim_b_id)}
              </div>
            </article>
          ))
        )}
      </div>
    </Panel>
  );
}
