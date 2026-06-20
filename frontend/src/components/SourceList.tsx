import { FileText, RefreshCw, WandSparkles } from "lucide-react";

import type { SourceRef } from "../domain/models";
import { formatBytes } from "../utils/format";
import { Button } from "./Button";
import { Panel } from "./Panel";

interface SourceListProps {
  sources: SourceRef[];
  activeSourceIds: string[];
  busySourceId: string | null;
  disabled: boolean;
  onRefresh: () => void;
  onToggleSource: (sourceId: string) => void;
  onIngest: (sourceId: string) => void;
}

export function SourceList({
  sources,
  activeSourceIds,
  busySourceId,
  disabled,
  onRefresh,
  onToggleSource,
  onIngest,
}: SourceListProps) {
  return (
    <Panel
      action={
        <Button icon={<RefreshCw className="h-4 w-4" />} onClick={onRefresh} variant="ghost">
          Làm mới
        </Button>
      }
      title="Nguồn"
    >
      <p className="mb-3 text-xs leading-5 text-muted">
        Chọn nguồn chỉ để giới hạn query. Ingest luôn tích hợp nguồn vào wiki chung.
      </p>
      <div className="max-h-[420px] space-y-2 overflow-auto pr-1">
        {sources.length === 0 ? (
          <p className="rounded-md border border-line bg-canvas p-3 text-sm text-muted">
            Chưa có nguồn.
          </p>
        ) : (
          sources.map((source) => (
            <article className="rounded-md border border-line bg-white p-3" key={source.id}>
              <div className="flex items-start gap-2">
                <FileText className="mt-0.5 h-4 w-4 text-cobalt" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-ink">{source.title}</div>
                  <div className="mt-1 text-xs text-muted">
                    {source.source_type} · {formatBytes(source.size_bytes)} · {source.status}
                  </div>
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <Button
                  className="flex-1"
                  disabled={disabled || busySourceId === source.id}
                  icon={<WandSparkles className="h-4 w-4" />}
                  onClick={() => onIngest(source.id)}
                >
                  {busySourceId === source.id ? "Đang chạy" : "Wiki Agent"}
                </Button>
                <label className="flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-md border border-line bg-canvas px-2 text-xs">
                  <input
                    checked={activeSourceIds.includes(source.id)}
                    className="h-4 w-4 accent-forest"
                    onChange={() => onToggleSource(source.id)}
                    type="checkbox"
                  />
                  Query scope
                </label>
              </div>
            </article>
          ))
        )}
      </div>
    </Panel>
  );
}
