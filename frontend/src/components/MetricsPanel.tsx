import { Activity } from "lucide-react";
import { Trace } from "../api/client";

interface Props {
  traces: Trace[];
}

const COLORS = ["#0f766e", "#2563eb", "#9333ea", "#d97706", "#dc2626"];

export function MetricsPanel({ traces }: Props) {
  const latest = traces.at(-1);
  const maxTokens = Math.max(1, ...traces.map((trace) => trace.total_tokens));
  const layeredLatest = [...traces].reverse().find((trace) => trace.mode === "layered");
  const naiveLatest = [...traces].reverse().find((trace) => trace.mode === "naive");

  return (
    <section className="metrics-panel">
      <div className="pane-header">
        <h2>Metrics</h2>
        <Activity size={17} />
      </div>
      <div className="metric-grid">
        <div>
          <span>Prompt tokens</span>
          <strong>{latest?.total_tokens.toLocaleString() || "0"}</strong>
        </div>
        <div>
          <span>Latency</span>
          <strong>{latest ? `${latest.latency_ms} ms` : "0 ms"}</strong>
        </div>
        <div>
          <span>Cost estimate</span>
          <strong>{latest?.cost_estimate_usd || "n/a"}</strong>
        </div>
      </div>
      <div className="comparison">
        <span>Latest layered: {layeredLatest?.total_tokens.toLocaleString() || "none"}</span>
        <span>Latest naive: {naiveLatest?.total_tokens.toLocaleString() || "none"}</span>
      </div>
      <div className="chart" aria-label="Tokens per layer over turns">
        {traces.map((trace, index) => (
          <div className="chart-row" key={trace.turn_id}>
            <span>{index + 1}</span>
            <div className="stack-bar" title={`${trace.mode}: ${trace.total_tokens} prompt tokens`}>
              {trace.layers.map((layer, layerIndex) => (
                <i
                  key={`${trace.turn_id}-${layer.name}`}
                  style={{
                    width: `${Math.max(2, (layer.tokens / maxTokens) * 100)}%`,
                    background: COLORS[layerIndex % COLORS.length]
                  }}
                />
              ))}
            </div>
            <em>{trace.mode[0].toUpperCase()}</em>
          </div>
        ))}
      </div>
    </section>
  );
}

