import { Box, FileText, Network, RefreshCw } from "lucide-react";

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
  onBuildGraph: () => void;
}

export function SourceList({
  sources,
  activeSourceIds,
  busySourceId,
  disabled,
  onRefresh,
  onToggleSource,
  onIngest,
  onBuildGraph,
}: SourceListProps) {
  return (
    <Panel
      action={
        <Button icon={<RefreshCw className="h-4 w-4" />} onClick={onRefresh} variant="ghost">
          Làm mới
        </Button>
      }
      title="Tài liệu"
    >
      <p className="mb-3 rounded-md border border-cobalt/20 bg-cobalt/5 p-2 text-xs leading-5 text-muted">
        Không chọn tài liệu nào: chat và build graph dùng toàn bộ tài liệu đã ingest.
        Chọn một hoặc nhiều tài liệu: chỉ dùng đúng phạm vi đã chọn.
      </p>
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="text-sm text-muted">
          {sources.length} tài liệu, {activeSourceIds.length} đang chọn
        </span>
        <Button
          disabled={disabled || sources.length === 0}
          icon={<Network className="h-4 w-4" />}
          onClick={onBuildGraph}
          variant="secondary"
        >
          Dựng graph
        </Button>
      </div>
      <div className="max-h-[420px] space-y-2 overflow-auto pr-1">
        {sources.length === 0 ? (
          <div className="rounded-md border border-line bg-canvas p-3 text-sm text-muted">
            Chưa có tài liệu. Hãy tải tệp đầu tiên để bắt đầu.
          </div>
        ) : (
          sources.map((source) => {
            const selected = activeSourceIds.includes(source.id);
            return (
              <article
                className="rounded-md border border-line bg-white p-3"
                key={source.id}
              >
                <div className="flex items-start gap-2">
                  <FileText className="mt-0.5 h-4 w-4 shrink-0 text-cobalt" />
                  <div className="min-w-0 flex-1">
                    <div className="block w-full truncate text-left text-sm font-semibold text-ink">
                      {source.title}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                      <span>{source.source_type}</span>
                      <span>{formatBytes(source.size_bytes)}</span>
                      <span className={source.status === "ingested" ? "text-forest" : "text-amber"}>
                        {source.status === "ingested" ? "đã ingest" : "đã đăng ký"}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="mt-3 flex gap-2">
                  <Button
                    className="flex-1"
                    disabled={disabled || busySourceId === source.id}
                    icon={<Box className="h-4 w-4" />}
                    onClick={() => onIngest(source.id)}
                  >
                    {busySourceId === source.id ? "Đang ingest" : "Ingest"}
                  </Button>
                  <label className="flex min-h-9 flex-1 cursor-pointer items-center justify-center gap-2 rounded-md border border-line bg-canvas px-2 text-xs font-medium text-ink">
                    <input
                      checked={selected}
                      className="h-4 w-4 accent-forest"
                      disabled={source.status !== "ingested"}
                      onChange={() => onToggleSource(source.id)}
                      type="checkbox"
                    />
                    Dùng trong phạm vi
                  </label>
                </div>
              </article>
            );
          })
        )}
      </div>
    </Panel>
  );
}
