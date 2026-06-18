import { useCallback, useEffect, useMemo, useState } from "react";
import { Database, Network, PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { Button } from "./components/Button";
import { ChatPanel } from "./components/ChatPanel";
import { ContradictionsPanel } from "./components/ContradictionsPanel";
import { GraphPanel } from "./components/GraphPanel";
import { SourceList } from "./components/SourceList";
import { StatusBanner, type BusyState } from "./components/StatusBanner";
import { UploadPanel } from "./components/UploadPanel";
import type {
  ChatMessage,
  Contradiction,
  GraphEntityDetail,
  GraphVisualization,
  SourceRef,
} from "./domain/models";
import type { UploadSourceInput } from "./services/apiClient";
import { useWorkbenchService } from "./services/useWorkbenchService";

const EMPTY_GRAPH: GraphVisualization = { nodes: [], edges: [] };

interface OperationStatus {
  state: BusyState;
  message: string;
}

export default function App() {
  const service = useWorkbenchService();
  const [sources, setSources] = useState<SourceRef[]>([]);
  const [activeSourceIds, setActiveSourceIds] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [graph, setGraph] = useState<GraphVisualization>(EMPTY_GRAPH);
  const [contradictions, setContradictions] = useState<Contradiction[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<GraphEntityDetail | null>(null);
  const [status, setStatus] = useState<OperationStatus>({ state: "idle", message: "" });
  const [busySourceId, setBusySourceId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const busy = status.state === "busy";
  const ingestedSources = useMemo(
    () => sources.filter((source) => source.status === "ingested"),
    [sources],
  );

  const loadSources = useCallback(async () => {
    try {
      setSources(await service.listSources());
    } catch (error) {
      setStatus({ state: "error", message: errorMessage(error) });
    }
  }, [service]);

  const loadGraph = useCallback(
    async (query = "") => {
      try {
        setGraph(await service.graph(query));
      } catch (error) {
        setStatus({ state: "error", message: errorMessage(error) });
      }
    },
    [service],
  );

  const loadContradictions = useCallback(async () => {
    try {
      setContradictions(await service.contradictions());
    } catch (error) {
      setStatus({ state: "error", message: errorMessage(error) });
    }
  }, [service]);

  useEffect(() => {
    void Promise.all([loadSources(), loadGraph(), loadContradictions()]);
  }, [loadContradictions, loadGraph, loadSources]);

  async function handleUpload(input: UploadSourceInput): Promise<SourceRef> {
    setStatus({ state: "busy", message: `Đang tải lên ${input.file.name}...` });
    try {
      const source = await service.uploadSource(input);
      await loadSources();
      setStatus({
        state: "success",
        message: `Đã tải lên và đăng ký tài liệu “${source.title}”.`,
      });
      return source;
    } catch (error) {
      setStatus({ state: "error", message: errorMessage(error) });
      throw error;
    }
  }

  async function handleIngest(sourceId: string) {
    const source = sources.find((item) => item.id === sourceId);
    setBusySourceId(sourceId);
    setStatus({
      state: "busy",
      message: `Đang ingest ${source?.title ?? sourceId}...`,
    });
    try {
      const result = await service.ingestSource(sourceId);
      await loadSources();
      setStatus({
        state: "success",
        message: (
          `${result.source.title}: ${result.evidence_count} bằng chứng, ` +
          `${result.claim_count} mệnh đề, ${result.entity_count} thực thể.`
        ),
      });
    } catch (error) {
      setStatus({ state: "error", message: errorMessage(error) });
    } finally {
      setBusySourceId(null);
    }
  }

  async function handleBuildGraph() {
    setStatus({ state: "busy", message: "Đang xây dựng knowledge graph..." });
    try {
      const result = await service.buildGraph(
        activeSourceIds.length > 0 ? activeSourceIds : [],
      );
      await Promise.all([loadGraph(), loadContradictions()]);
      setStatus({
        state: "success",
        message: (
          `Đã dựng graph: ${result.relation_count} quan hệ, ` +
          `${result.contradiction_count} mâu thuẫn, ` +
          `${result.entity_page_count} trang thực thể.`
        ),
      });
    } catch (error) {
      setStatus({ state: "error", message: errorMessage(error) });
    }
  }

  async function handleAsk(question: string) {
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: question,
      createdAt: new Date().toISOString(),
    };
    setMessages((current) => [...current, userMessage]);
    setStatus({
      state: "busy",
      message: "Đang lập kế hoạch, truy xuất và tổng hợp câu trả lời...",
    });
    try {
      const result = await service.ask({
        question,
        sourceIds: activeSourceIds,
        mode: "deep",
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
        message: (
          `Câu trả lời dùng ${result.citations.length} trích dẫn từ ` +
          `${result.candidate_count} candidate.`
        ),
      });
    } catch (error) {
      const message = errorMessage(error);
      setMessages((current) => [
        ...current,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: `Truy vấn thất bại: ${message}`,
          createdAt: new Date().toISOString(),
        },
      ]);
      setStatus({ state: "error", message });
    }
  }

  async function handleSelectEntity(nodeId: string, label: string) {
    if (nodeId.startsWith("literal:") || nodeId.startsWith("subject:")) {
      setStatus({ state: "success", message: `Đã chọn giá trị graph: ${label}` });
      return;
    }
    try {
      setSelectedEntity(await service.entity(nodeId));
    } catch (error) {
      setStatus({ state: "error", message: errorMessage(error) });
    }
  }

  function toggleSource(sourceId: string) {
    setActiveSourceIds((current) =>
      current.includes(sourceId)
        ? current.filter((id) => id !== sourceId)
        : [...current, sourceId],
    );
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-20 border-b border-line bg-panel/95 backdrop-blur">
        <div className="mx-auto flex min-h-16 max-w-[1800px] items-center gap-3 px-4 lg:px-6">
          <Button
            aria-label={sidebarOpen ? "Đóng thanh tài liệu" : "Mở thanh tài liệu"}
            className="w-9 px-0 lg:hidden"
            onClick={() => setSidebarOpen((open) => !open)}
            variant="ghost"
          >
            {sidebarOpen ? (
              <PanelLeftClose className="h-4 w-4" />
            ) : (
              <PanelLeftOpen className="h-4 w-4" />
            )}
          </Button>
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-forest text-white">
            <Database className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-base font-semibold">LLM Wiki</h1>
            <p className="text-xs text-muted">Không gian tri thức bám sát nguồn</p>
          </div>
          <div className="ml-auto flex items-center gap-4 text-xs text-muted">
            <span>{sources.length} tài liệu</span>
            <span>{ingestedSources.length} đã ingest</span>
            <span className="hidden items-center gap-1 sm:flex">
              <Network className="h-3.5 w-3.5" />
              {graph.nodes.length} nút
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1800px] px-4 py-4 lg:px-6">
        <StatusBanner message={status.message} state={status.state} />
        <div className="mt-4 grid items-start gap-4 lg:grid-cols-[300px_minmax(420px,1fr)_minmax(380px,0.9fr)]">
          <aside className={sidebarOpen ? "space-y-4" : "hidden space-y-4 lg:block"}>
            <UploadPanel disabled={busy} onUpload={handleUpload} />
            <SourceList
              activeSourceIds={activeSourceIds}
              busySourceId={busySourceId}
              disabled={busy}
              onBuildGraph={handleBuildGraph}
              onIngest={handleIngest}
              onRefresh={loadSources}
              onToggleSource={toggleSource}
              sources={sources}
            />
          </aside>

          <ChatPanel
            activeSourceIds={activeSourceIds}
            disabled={busy}
            messages={messages}
            onAsk={handleAsk}
            sources={sources}
          />

          <aside className="space-y-4">
            <GraphPanel
              disabled={busy}
              graph={graph}
              onBuildGraph={handleBuildGraph}
              onRefresh={loadGraph}
              onSelectEntity={handleSelectEntity}
              selectedEntity={selectedEntity}
            />
            <ContradictionsPanel
              contradictions={contradictions}
              disabled={busy}
              onRefresh={loadContradictions}
            />
          </aside>
        </div>
      </main>
    </div>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Ứng dụng gặp lỗi không xác định.";
}
