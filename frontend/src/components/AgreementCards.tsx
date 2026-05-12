import { Panel } from "./Panel";
import { Check, X } from "lucide-react";

interface Props {
  agreement?: string[];
  disagreement?: string[];
}

export function AgreementCards({ agreement, disagreement }: Props) {
  if (!agreement?.length && !disagreement?.length) return null;
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Panel title="Areas of Agreement">
        <List items={agreement ?? []} icon={<Check className="h-3.5 w-3.5 text-win" />} empty="No clear agreement items." />
      </Panel>
      <Panel title="Areas of Disagreement">
        <List items={disagreement ?? []} icon={<X className="h-3.5 w-3.5 text-loss" />} empty="No major disagreement items." />
      </Panel>
    </div>
  );
}

function List({ items, icon, empty }: { items: string[]; icon: React.ReactNode; empty: string }) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-500">{empty}</p>;
  }
  return (
    <ul className="space-y-2.5">
      {items.map((s, i) => (
        <li
          key={i}
          className="flex items-start gap-2 rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2 text-sm text-slate-200"
        >
          <span className="mt-1">{icon}</span>
          <span>{s}</span>
        </li>
      ))}
    </ul>
  );
}
