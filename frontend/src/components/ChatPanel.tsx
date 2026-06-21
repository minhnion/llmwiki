import { FormEvent, useState } from "react";
import { Bot, Send, User } from "lucide-react";

import type { ChatMessage } from "../domain/models";
import { Button } from "./Button";
import { Panel } from "./Panel";

interface ChatPanelProps {
  messages: ChatMessage[];
  disabled: boolean;
  onAsk: (question: string) => void;
}

export function ChatPanel({ messages, disabled, onAsk }: ChatPanelProps) {
  const [question, setQuestion] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = question.trim();
    if (!value) return;
    onAsk(value);
    setQuestion("");
  }

  return (
    <Panel className="min-h-[680px]" title="Chat với Wiki Agent">
      <div className="mb-4 max-h-[560px] space-y-3 overflow-auto">
        {messages.length === 0 ? (
          <p className="rounded-md border border-line bg-canvas p-4 text-sm text-muted">
            Hỏi wiki. Agent sẽ tìm trang liên quan và có thể mở lại raw source khi cần.
          </p>
        ) : (
          messages.map((message) => (
            <article className="rounded-md border border-line bg-white p-3" key={message.id}>
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
                {message.role === "assistant" ? (
                  <Bot className="h-4 w-4 text-forest" />
                ) : (
                  <User className="h-4 w-4 text-cobalt" />
                )}
                {message.role === "assistant" ? "Wiki Agent" : "Bạn"}
                {message.result ? (
                  <span className="ml-auto text-xs font-normal text-muted">
                    {message.result.confidence}
                  </span>
                ) : null}
              </div>
              <p className="whitespace-pre-wrap text-sm leading-6 text-ink">{message.content}</p>
              {message.result?.citations.length ? (
                <div className="mt-3 space-y-2 border-t border-line pt-3">
                  {message.result.citations.map((citation, index) => (
                    <div className="rounded bg-canvas p-2 text-xs text-muted" key={`${citation.page_id}-${index}`}>
                      <div className="font-semibold text-ink">
                        {citation.page_id} · {citation.locator}
                      </div>
                      <div>{citation.quote_or_summary}</div>
                    </div>
                  ))}
                </div>
              ) : null}
            </article>
          ))
        )}
      </div>
      <form className="flex gap-2" onSubmit={submit}>
        <textarea
          className="min-h-20 flex-1 resize-none rounded-md border border-line px-3 py-2 text-sm focus:border-cobalt focus:outline-none"
          disabled={disabled}
          placeholder="Đặt câu hỏi..."
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <Button
          disabled={disabled || !question.trim()}
          icon={<Send className="h-4 w-4" />}
          type="submit"
        >
          Gửi
        </Button>
      </form>
    </Panel>
  );
}
