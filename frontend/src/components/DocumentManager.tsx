import { FileText, Trash2, Upload } from "lucide-react";
import { DocumentRecord } from "../api/client";

interface Props {
  documents: DocumentRecord[];
  disabled: boolean;
  onUpload: (file: File) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

export function DocumentManager({ documents, disabled, onUpload, onDelete }: Props) {
  return (
    <aside className="documents-pane">
      <div className="pane-header">
        <h2>Documents</h2>
        <label className="upload-button" title="Upload PDF, text, or Markdown">
          <Upload size={16} />
          <input
            type="file"
            accept=".pdf,.txt,.md,.markdown"
            disabled={disabled}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void onUpload(file);
              event.currentTarget.value = "";
            }}
          />
        </label>
      </div>
      <div className="document-list">
        {documents.length === 0 && <div className="empty">No documents loaded.</div>}
        {documents.map((document) => (
          <div className="document-row" key={document.id}>
            <FileText size={18} />
            <div>
              <strong>{document.name}</strong>
              <span>{document.token_count.toLocaleString()} tokens</span>
            </div>
            <button
              className="icon-button danger"
              type="button"
              disabled={disabled}
              title={`Remove ${document.name}`}
              onClick={() => void onDelete(document.id)}
            >
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}

