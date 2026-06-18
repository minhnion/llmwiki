import { FormEvent, useMemo, useState } from "react";
import { Bot, Send, User } from "lucide-react";

import type { ChatMessage, SourceRef } from "../domain/models";
import { shortId } from "../utils/format";
import { Button } from "./Button";
import { Panel } from "./Panel";

interface ChatPanelProps {
  messages: ChatMessage[];
  sources: SourceRef[];
  activeSourceIds: string[];
  disabled: boolean;
  onAsk: (question: string) => Promise<void>;
}

export function ChatPanel({
  messages,
  sources,
  activeSourceIds,
  disabled,
  onAsk,
}: ChatPanelProps) {
  const [question, setQuestion] = useState("");
  const activeSourceTitles = useMemo(
    () =>
      sources
        .filter((source) => activeSourceIds.includes(source.id))
        .map((source) => source.title)
        .join(", "),
    [activeSourceIds, sources],
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) {
      return;
    }
    setQuestion("");
    await onAsk(trimmed);
  }

  return (
    <Panel
      action={
        <span className="max-w-[280px] truncate text-xs text-muted">
          {activeSourceTitles || "Toàn bộ tài liệu đã ingest"}
        </span>
      }
      className="flex min-h-[720px] flex-col"
      title="Hỏi đáp"
    >
      <div className="flex min-h-[560px] flex-1 flex-col gap-3 overflow-auto pr-1">
        {messages.length === 0 ? (
          <div className="flex h-full min-h-[420px] items-center justify-center rounded-md border border-line bg-canvas text-center text-sm text-muted">
            Hãy ingest ít nhất một tài liệu rồi đặt câu hỏi bám sát nguồn.
          </div>
        ) : (
          messages.map((message) => <ChatBubble key={message.id} message={message} />)
        )}
      </div>
      <form className="mt-4 flex gap-2" onSubmit={handleSubmit}>
        <textarea
          className="min-h-20 flex-1 resize-none rounded-md border border-line px-3 py-2 text-sm focus:border-cobalt focus:outline-none"
          placeholder="Đặt câu hỏi cho LLM Wiki..."
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <Button
          className="h-20 w-28"
          disabled={disabled || !question.trim()}
          icon={<Send className="h-4 w-4" />}
          type="submit"
          variant="primary"
        >
          Hỏi
        </Button>
      </form>
    </Panel>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isAssistant = message.role === "assistant";
  const Icon = isAssistant ? Bot : User;
  return (
    <article className="rounded-md border border-line bg-white p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
        <Icon className={isAssistant ? "h-4 w-4 text-forest" : "h-4 w-4 text-cobalt"} />
        {isAssistant ? "LLM Wiki" : "Bạn"}
        {message.result ? (
          <span className="ml-auto text-xs font-normal text-muted">
            độ tin cậy: {message.result.confidence}
          </span>
        ) : null}
      </div>
      <p className="whitespace-pre-wrap text-sm leading-6 text-ink">{message.content}</p>
      {message.result ? (
        <div className="mt-3 space-y-3 border-t border-line pt-3">
          {message.result.citations.length > 0 ? (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                Trích dẫn
              </h3>
              <div className="space-y-2">
                {message.result.citations.map((citation) => (
                  <div
                    className="rounded-md border border-line bg-canvas px-3 py-2 text-xs text-muted"
                    key={citation.evidence_id}
                  >
                    <div className="font-semibold text-ink">
                      {citation.source_title} | {citation.locator}
                    </div>
                    <div>{citation.quote_or_summary}</div>
                    <div className="mt-1 font-mono">{shortId(citation.evidence_id)}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {message.result.selected_evidence.length > 0 ? (
            <details className="text-xs text-muted">
              <summary className="cursor-pointer font-semibold text-ink">
                Dấu vết bằng chứng ({message.result.selected_evidence.length})
              </summary>
              <div className="mt-2 space-y-2">
                {message.result.selected_evidence.map((evidence) => (
                  <div className="rounded-md bg-canvas p-2" key={evidence.evidence_id}>
                    <div className="font-semibold text-ink">
                      {evidence.locator} | {evidence.retrieval_channels.join(", ")}
                    </div>
                    <div>{evidence.summary}</div>
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
