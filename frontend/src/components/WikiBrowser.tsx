import { BookOpen, RefreshCw } from "lucide-react";

import type { WikiPage, WikiPageSummary } from "../domain/models";
import { Button } from "./Button";
import { Panel } from "./Panel";

interface WikiBrowserProps {
  pages: WikiPageSummary[];
  selectedPage: WikiPage | null;
  disabled: boolean;
  onSelect: (pageId: string) => void;
  onRebuild: () => void;
}

export function WikiBrowser({
  pages,
  selectedPage,
  disabled,
  onSelect,
  onRebuild,
}: WikiBrowserProps) {
  return (
    <Panel
      action={
        <Button
          disabled={disabled}
          icon={<RefreshCw className="h-4 w-4" />}
          onClick={onRebuild}
          variant="ghost"
        >
          Đồng bộ
        </Button>
      }
      title="Wiki"
    >
      <div className="max-h-64 space-y-2 overflow-auto pr-1">
        {pages.length === 0 ? (
          <p className="rounded-md border border-line bg-canvas p-3 text-sm text-muted">
            Wiki chưa có trang generated.
          </p>
        ) : (
          pages.map((page) => (
            <button
              className="block w-full rounded-md border border-line bg-canvas p-3 text-left hover:border-cobalt"
              key={page.id}
              onClick={() => onSelect(page.id)}
              type="button"
            >
              <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                <BookOpen className="h-4 w-4 text-forest" />
                {page.title}
              </span>
              <span className="mt-1 block text-xs text-muted">
                {page.page_type} · {page.source_ids.length} nguồn
              </span>
              <span className="mt-1 block text-xs leading-5 text-muted">{page.summary}</span>
            </button>
          ))
        )}
      </div>
      {selectedPage ? (
        <article className="mt-4 border-t border-line pt-4">
          <h3 className="text-base font-semibold text-ink">{selectedPage.title}</h3>
          <div className="mt-1 text-xs text-muted">
            {selectedPage.page_type} · {selectedPage.path}
          </div>
          <pre className="mt-3 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-md bg-canvas p-3 font-sans text-sm leading-6 text-ink">
            {selectedPage.body}
          </pre>
        </article>
      ) : null}
    </Panel>
  );
}
