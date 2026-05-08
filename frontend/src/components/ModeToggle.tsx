import { Layers, Rows3 } from "lucide-react";
import { Mode } from "../api/client";

interface Props {
  mode: Mode;
  disabled: boolean;
  onChange: (mode: Mode) => void;
}

export function ModeToggle({ mode, disabled, onChange }: Props) {
  return (
    <div className="segmented" aria-label="Mode">
      <button
        type="button"
        disabled={disabled}
        className={mode === "layered" ? "active" : ""}
        onClick={() => onChange("layered")}
      >
        <Layers size={16} /> Layered
      </button>
      <button
        type="button"
        disabled={disabled}
        className={mode === "naive" ? "active" : ""}
        onClick={() => onChange("naive")}
      >
        <Rows3 size={16} /> Naive
      </button>
    </div>
  );
}

