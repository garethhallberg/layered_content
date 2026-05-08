import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { RefreshCw } from "lucide-react";
import { api, AppSession, Mode, Trace } from "./api/client";
import { ChatPane } from "./components/ChatPane";
import { DocumentManager } from "./components/DocumentManager";
import { LayerInspector } from "./components/LayerInspector";
import { MetricsPanel } from "./components/MetricsPanel";
import { ModeToggle } from "./components/ModeToggle";
import "./styles/app.css";

const PROVIDER_OPTIONS = [
  { value: "openai:gpt-5-mini", label: "OpenAI / GPT-5 mini" },
  { value: "openai:gpt-5.2", label: "OpenAI / GPT-5.2" },
  { value: "anthropic:claude-sonnet-4-20250514", label: "Anthropic / Claude Sonnet 4" },
  { value: "anthropic:claude-opus-4-1-20250805", label: "Anthropic / Claude Opus 4.1" },
  { value: "mistral:mistral-small-2603", label: "Mistral / Small 4" },
  { value: "mistral:mistral-medium-3-5", label: "Mistral / Medium 3.5" },
  { value: "mistral:mistral-large-2512", label: "Mistral / Large 3" }
];

function sessionIdFromLocation(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get("session") || localStorage.getItem("layered-context-session");
}

function persistSessionId(id: string) {
  localStorage.setItem("layered-context-session", id);
  const url = new URL(window.location.href);
  url.searchParams.set("session", id);
  window.history.replaceState({}, "", url);
}

function App() {
  const [session, setSession] = useState<AppSession | null>(null);
  const [selectedTraceId, setSelectedTraceId] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const existingId = sessionIdFromLocation();
        const loaded = existingId ? await api.getSession(existingId) : await api.createSession();
        persistSessionId(loaded.id);
        setSession(loaded);
        setSelectedTraceId(loaded.traces.at(-1)?.turn_id || "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load session");
      }
    };
    void load();
  }, []);

  const selectedTrace = useMemo<Trace | undefined>(() => {
    if (!session) return undefined;
    return session.traces.find((trace) => trace.turn_id === selectedTraceId) || session.traces.at(-1);
  }, [session, selectedTraceId]);

  const providerValue = session ? `${session.provider}:${session.model}` : "";
  const providerOptionExists = PROVIDER_OPTIONS.some((option) => option.value === providerValue);

  const refresh = async () => {
    if (!session) return;
    const loaded = await api.getSession(session.id);
    setSession(loaded);
    setSelectedTraceId(loaded.traces.at(-1)?.turn_id || "");
  };

  const changeMode = async (mode: Mode) => {
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.patchSession(session.id, { mode });
      setSession(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mode change failed");
    } finally {
      setBusy(false);
    }
  };

  const changeProvider = async (provider: string, model: string) => {
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.patchSession(session.id, { provider, model });
      setSession(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Provider change failed");
    } finally {
      setBusy(false);
    }
  };

  const uploadDocument = async (file: File) => {
    if (!session) return;
    setBusy(true);
    try {
      await api.uploadDocument(session.id, file);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const deleteDocument = async (documentId: string) => {
    if (!session) return;
    setBusy(true);
    try {
      await api.deleteDocument(session.id, documentId);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const sendMessage = async (content: string) => {
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.sendMessage(session.id, content);
      setSession({
        ...session,
        turns: [...session.turns, result.user_turn, result.assistant_turn],
        traces: [...session.traces, result.trace]
      });
      setSelectedTraceId(result.turn_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Message failed");
      try {
        const refreshed = await api.getSession(session.id);
        setSession(refreshed);
      } catch {
        // Keep the original provider error visible.
      }
    } finally {
      setBusy(false);
    }
  };

  if (!session) {
    return <main className="loading">{error || "Loading session..."}</main>;
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">Layered Context Document Analyst</div>
          <div className="session-id">Session {session.id.slice(0, 8)}</div>
        </div>
        <ModeToggle mode={session.mode} disabled={busy} onChange={changeMode} />
        <label className="provider-control">
          Provider
          <select
            value={providerValue}
            disabled={busy}
            onChange={(event) => {
              const [provider, model] = event.target.value.split(":");
              void changeProvider(provider, model);
            }}
          >
            {!providerOptionExists && (
              <option value={providerValue}>
                Current: {session.provider} / {session.model}
              </option>
            )}
            {PROVIDER_OPTIONS.map((option) => (
              <option value={option.value} key={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <span className="provider-current">
            Active: {session.provider} / {session.model}
          </span>
        </label>
        <button className="icon-button" type="button" onClick={() => void refresh()} title="Refresh session">
          <RefreshCw size={18} />
        </button>
      </header>

      {error && <div className="error-strip">{error}</div>}

      <section className="workspace">
        <DocumentManager
          documents={session.documents}
          disabled={busy}
          onUpload={uploadDocument}
          onDelete={deleteDocument}
        />
        <ChatPane turns={session.turns} disabled={busy} onSend={sendMessage} />
        <aside className="inspector-column">
          <LayerInspector
            traces={session.traces}
            selectedTurnId={selectedTrace?.turn_id || ""}
            onSelect={setSelectedTraceId}
          />
          <MetricsPanel traces={session.traces} />
        </aside>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
