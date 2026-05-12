import { Panel } from "./Panel";

interface Props {
  reasoning?: string;
  valueAssessment?: string;
}

export function ReasoningCards({ reasoning, valueAssessment }: Props) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Panel title="Reasoning">
        <p className="whitespace-pre-line text-sm leading-relaxed text-slate-200">
          {reasoning?.trim() || "No reasoning provided."}
        </p>
      </Panel>
      <Panel title="Value Assessment">
        <p className="whitespace-pre-line text-sm leading-relaxed text-slate-200">
          {valueAssessment?.trim() || "No value commentary provided."}
        </p>
      </Panel>
    </div>
  );
}
