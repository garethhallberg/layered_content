import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { LayerTrace, Trace } from "../api/client";

const DESCRIPTIONS: Record<string, string> = {
  L1_system: "Static system constraints.",
  L2_documents: "Currently loaded document context.",
  L3_summary: "Compressed older conversation turns.",
  L4_recent: "Recent verbatim turns, or full history in naive mode.",
  L5_working: "Per-turn planner state and current task scratchpad."
};

interface Props {
  traces: Trace[];
  selectedTurnId: string;
  onSelect: (turnId: string) => void;
}

export function LayerInspector({ traces, selectedTurnId, onSelect }: Props) {
  const trace = traces.find((item) => item.turn_id === selectedTurnId) || traces.at(-1);

  return (
    <section className="layer-inspector">
      <div className="pane-header">
        <h2>Layer Inspector</h2>
        <select
          value={trace?.turn_id || ""}
          onChange={(event) => onSelect(event.target.value)}
          disabled={traces.length === 0}
        >
          {traces.length === 0 && <option>No traces</option>}
          {traces.map((item, index) => (
            <option value={item.turn_id} key={item.turn_id}>
              Turn {index + 1} · {item.mode} · {item.total_tokens.toLocaleString()} tokens
            </option>
          ))}
        </select>
      </div>
      {!trace && <div className="empty">Trace data appears after the first message.</div>}
      {trace && (
        <>
          {trace.summariser_event && (
            <div className="summary-event">
              Summariser fired · {String(trace.summariser_event.pairs_summarised)} pairs ·{" "}
              {String(trace.summariser_event.latency_ms)} ms
            </div>
          )}
          <div className="layer-stack">
            {trace.layers.map((layer: LayerTrace) => (
              <LayerBlock layer={layer} key={layer.name} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function LayerBlock({ layer }: { layer: LayerTrace }) {
  const [open, setOpen] = useState(true);
  const covers = useMemo(() => {
    const ids = layer.metadata?.covers_turn_ids;
    return Array.isArray(ids) && ids.length > 0 ? `${Math.floor(ids.length / 2)} pairs covered` : "";
  }, [layer.metadata]);
  const atRiskIds = layer.metadata?.about_to_age_out_turn_ids;
  const planner = layer.metadata?.planner;

  return (
    <article className="layer-block">
      <button className="layer-title" type="button" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <div>
          <strong>{layer.name}</strong>
          <span>{DESCRIPTIONS[layer.name] || "Context layer"}</span>
        </div>
        <em>{layer.tokens.toLocaleString()} tokens</em>
      </button>
      {open && (
        <div className="layer-body">
          <div className="badge-row">
            <span>{layer.role}</span>
            {covers && <span>{covers}</span>}
            {Array.isArray(atRiskIds) && atRiskIds.length > 0 && (
              <span>{atRiskIds.length} turns about to age out</span>
            )}
          </div>
          {planner !== null && typeof planner === "object" && (
            <div className="planner-json">
              {Object.entries(planner as Record<string, unknown>).map(([key, value]) => (
                <div key={key}>
                  <strong>{key}</strong>
                  <span>{Array.isArray(value) ? value.join(", ") : String(value)}</span>
                </div>
              ))}
            </div>
          )}
          <pre>{layer.content}</pre>
        </div>
      )}
    </article>
  );
}
