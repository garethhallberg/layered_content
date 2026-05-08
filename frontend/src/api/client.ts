export type Mode = "layered" | "naive";

export interface DocumentRecord {
  id: string;
  name: string;
  token_count: number;
  uploaded_at: string;
}

export interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  token_count: number;
  created_at: string;
}

export interface LayerTrace {
  name: string;
  role: "system" | "user" | "assistant";
  content: string;
  tokens: number;
  metadata: Record<string, unknown>;
}

export interface Trace {
  id?: string;
  turn_id: string;
  mode: Mode;
  provider: string;
  model: string;
  layers: LayerTrace[];
  total_tokens: number;
  latency_ms: number;
  cost_estimate_usd: string | null;
  summariser_event?: Record<string, unknown> | null;
  created_at?: string;
}

export interface AppSession {
  id: string;
  mode: Mode;
  provider: string;
  model: string;
  documents: DocumentRecord[];
  turns: Turn[];
  traces: Trace[];
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    }
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return response.json() as Promise<T>;
}

export const api = {
  createSession: () => request<AppSession>("/sessions", { method: "POST", body: "{}" }),
  getSession: (id: string) => request<AppSession>(`/sessions/${id}`),
  patchSession: (id: string, payload: Partial<Pick<AppSession, "mode" | "provider" | "model">>) =>
    request<AppSession>(`/sessions/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  uploadDocument: (id: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<DocumentRecord>(`/sessions/${id}/documents`, { method: "POST", body });
  },
  deleteDocument: (sessionId: string, documentId: string) =>
    request<{ status: string }>(`/sessions/${sessionId}/documents/${documentId}`, { method: "DELETE" }),
  sendMessage: (id: string, content: string) =>
    request<{ turn_id: string; assistant_message: string; trace: Trace; assistant_turn: Turn }>(
      `/sessions/${id}/messages`,
      { method: "POST", body: JSON.stringify({ content }) }
    ),
  getTraces: (id: string) => request<Trace[]>(`/sessions/${id}/traces`)
};

