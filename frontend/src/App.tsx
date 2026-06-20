import { useCallback, useEffect, useState } from "react";
import { Library } from "lucide-react";

import { ChatPanel } from "./components/ChatPanel";
import { SourceList } from "./components/SourceList";
import { StatusBanner, type BusyState } from "./components/StatusBanner";
import { UploadPanel } from "./components/UploadPanel";
import { WikiBrowser } from "./components/WikiBrowser";
import type {
  ChatMessage,
  SourceRef,
  WikiPage,
  WikiPageSummary,
} from "./domain/models";
import type { UploadSourceInput } from "./services/apiClient";
import { useWorkbenchService } from "./services/useWorkbenchService";

interface OperationStatus {
  state: BusyState;
  message: string;
}

export default function App() {
  const service = useWorkbenchService();
  const [sources, setSources] = useState<SourceRef[]>([]);
  const [activeSourceIds, setActiveSourceIds] = useState<string[]>([]);
  const [pages, setPages] = useState<WikiPageSummary[]>([]);
  const [selectedPage, setSelectedPage] = useState<WikiPage | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busySourceId, setBusySourceId] = useState<string | null>(null);
  const [status, setStatus] = useState<OperationStatus>({ state: "idle", message: "" });
  const busy = status.state === "busy";

  const loadSources = useCallback(async () => {
    setSources(await service.listSources());
  }, [service]);

  const loadPages = useCallback(async () => {
    setPages(await service.listPages());
  }, [service]);

  useEffect(() => {
    Promise.all([loadSources(), loadPages()]).catch((error) => {
      setStatus({ state: "error", message: errorMessage(error) });
    });
  }, [loadPages, loadSources]);

  async function handleUpload(input: UploadSourceInput): Promise<SourceRef> {
    setStatus({ state: "busy", message: `Đang tải ${input.file.name}...` });
    try {
      const source = await service.uploadSource(input);
      await loadSources();
      setStatus({ state: "success", message: `Đã đăng ký “${source.title}”.` });
      return source;
    } catch (error) {
      setStatus({ state: "error", message: errorMessage(error) });
      throw error;
    }
  }

  async function handleIngest(sourceId: string) {
    setBusySourceId(sourceId);
    setStatus({ state: "busy", message: "Wiki Agent đang hiểu nguồn và duy trì wiki..." });
    try {
      const result = await service.ingestSource(sourceId);
      await Promise.all([loadSources(), loadPages()]);
      setStatus({
        state: "success",
        message: result.skipped
          ? "Nguồn không thay đổi; đã dùng cache."
          : `${result.changed_page_ids.length} trang thay đổi, ${result.model_calls} model calls.`,
      });
    } catch (error) {
      setStatus({ state: "error", message: errorMessage(error) });
    } finally {
      setBusySourceId(null);
    }
  }

  async function handleAsk(question: string) {
    setMessages((current) => [
      ...current,
      {
        id: `user-${Date.now()}`,
        role: "user",
        content: question,
        createdAt: new Date().toISOString(),
      },
    ]);
    setStatus({ state: "busy", message: "Wiki Agent đang tìm, đọc và trả lời..." });
    try {
      const result = await service.ask({
        question,
        mode: "deep",
        sourceIds: activeSourceIds,
      });
      setMessages((current) => [
        ...current,
        {
          id: result.query_id,
          role: "assistant",
          content: result.answer,
          result,
          createdAt: result.created_at,
        },
      ]);
      setStatus({
        state: "success",
        message: `${result.pages_read.length} trang đã đọc, ${result.citations.length} citation.`,
      });
    } catch (error) {
      setStatus({ state: "error", message: errorMessage(error) });
    }
  }

  async function handleSelectPage(pageId: string) {
    try {
      setSelectedPage(await service.getPage(pageId));
    } catch (error) {
      setStatus({ state: "error", message: errorMessage(error) });
    }
  }

  async function handleRebuild() {
    setStatus({ state: "busy", message: "Đang validate và đồng bộ wiki..." });
    try {
      setPages(await service.rebuildWiki());
      setStatus({ state: "success", message: "Wiki và SQLite đã đồng bộ." });
    } catch (error) {
      setStatus({ state: "error", message: errorMessage(error) });
    }
  }

  return (
    <main className="min-h-screen bg-canvas text-ink">
      <header className="border-b border-line bg-panel px-6 py-4">
        <div className="mx-auto flex max-w-[1600px] items-center gap-3">
          <Library className="h-6 w-6 text-forest" />
          <div>
            <h1 className="text-lg font-semibold">LLM Wiki Agent</h1>
            <p className="text-xs text-muted">
              LLM quyết định tri thức; code bảo vệ provenance và tính toàn vẹn.
            </p>
          </div>
        </div>
      </header>
      <div className="mx-auto max-w-[1600px] space-y-4 p-4">
        <StatusBanner message={status.message} state={status.state} />
        <div className="grid gap-4 xl:grid-cols-[320px_minmax(480px,1fr)_420px]">
          <aside className="space-y-4">
            <UploadPanel disabled={busy} onUpload={handleUpload} />
            <SourceList
              activeSourceIds={activeSourceIds}
              busySourceId={busySourceId}
              disabled={busy}
              onIngest={handleIngest}
              onRefresh={() => void loadSources()}
              onToggleSource={(sourceId) =>
                setActiveSourceIds((current) =>
                  current.includes(sourceId)
                    ? current.filter((id) => id !== sourceId)
                    : [...current, sourceId],
                )
              }
              sources={sources}
            />
          </aside>
          <ChatPanel disabled={busy} messages={messages} onAsk={handleAsk} />
          <WikiBrowser
            disabled={busy}
            onRebuild={handleRebuild}
            onSelect={handleSelectPage}
            pages={pages}
            selectedPage={selectedPage}
          />
        </div>
      </div>
    </main>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Đã xảy ra lỗi không xác định.";
}
