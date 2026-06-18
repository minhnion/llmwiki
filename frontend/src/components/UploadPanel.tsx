import { FormEvent, useState } from "react";
import { FileUp, Upload } from "lucide-react";

import type { SourceRef } from "../domain/models";
import { Button } from "./Button";
import { Panel } from "./Panel";

interface UploadPanelProps {
  disabled: boolean;
  onUpload: (input: {
    file: File;
    title?: string;
    sourceType?: string;
    tags?: string[];
  }) => Promise<SourceRef>;
}

export function UploadPanel({ disabled, onUpload }: UploadPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [tags, setTags] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      return;
    }
    const form = event.currentTarget;
    await onUpload({
      file,
      title: title || undefined,
      sourceType: sourceType || undefined,
      tags: tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    });
    setFile(null);
    setTitle("");
    setSourceType("");
    setTags("");
    form.reset();
  }

  return (
    <Panel title="Tải tài liệu">
      <form className="space-y-3" onSubmit={handleSubmit}>
        <label className="flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-line bg-canvas px-3 text-center text-sm text-muted hover:border-cobalt">
          <FileUp className="mb-2 h-5 w-5 text-cobalt" />
          <span className="font-medium text-ink">
            {file ? file.name : "Chọn tệp tài liệu"}
          </span>
          <span>
            {file ? `${Math.ceil(file.size / 1024)} KB` : "PDF, ảnh scan, docs, bảng tính"}
          </span>
          <input
            aria-label="Chọn tệp tài liệu"
            className="sr-only"
            type="file"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <input
          className="h-9 w-full rounded-md border border-line px-3 text-sm focus:border-cobalt focus:outline-none"
          placeholder="Tiêu đề (không bắt buộc)"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
        <div className="grid grid-cols-2 gap-2">
          <input
            className="h-9 rounded-md border border-line px-3 text-sm focus:border-cobalt focus:outline-none"
            placeholder="Loại tài liệu"
            value={sourceType}
            onChange={(event) => setSourceType(event.target.value)}
          />
          <input
            className="h-9 rounded-md border border-line px-3 text-sm focus:border-cobalt focus:outline-none"
            placeholder="Nhãn, cách nhau bởi dấu phẩy"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
          />
        </div>
        <Button
          className="w-full"
          disabled={disabled || !file}
          icon={<Upload className="h-4 w-4" />}
          type="submit"
          variant="primary"
        >
          Tải lên
        </Button>
      </form>
    </Panel>
  );
}
