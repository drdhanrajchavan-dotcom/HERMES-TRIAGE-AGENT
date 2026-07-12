import { FormEvent, useState } from "react";

export type Activity = { direction: "inbound" | "outbound"; deliveryStatus: string; createdAt: number; preview: string };
export type CaseSummary = { id: string; status: "open" | "escalated" | "closed" | "failed"; patientLabel: string; openedAt: number; traceId?: string; activity: Activity[] };
export type EscalationSummary = { id: string; caseId: string; summary: string; recommendedAction: string; matchedRedFlags: string[]; assignedTo?: string; createdAt: number };

type Props = {
  cases: CaseSummary[];
  escalations: EscalationSummary[];
  langfuseBaseUrl: string;
  authenticated: boolean;
  onAssign: (id: string, assignee: string) => Promise<void>;
  onResolve: (id: string, resolution: string) => Promise<void>;
};

const trimBase = (url: string) => url.replace(/\/$/, "");
const traceUrl = (base: string, id: string) => `${trimBase(base)}/trace/${encodeURIComponent(id)}`;
const evalUrl = (base: string, id: string) => `${trimBase(base)}/project/evals?traceId=${encodeURIComponent(id)}`;

function EscalationCard({ item, onAssign, onResolve }: { item: EscalationSummary; onAssign: Props["onAssign"]; onResolve: Props["onResolve"] }) {
  const [assignee, setAssignee] = useState(item.assignedTo ?? "");
  const [resolution, setResolution] = useState("");
  const [pending, setPending] = useState<"assign" | "resolve" | null>(null);
  const [error, setError] = useState("");
  const submit = (kind: "assign" | "resolve", fn: () => Promise<void>) => async (event: FormEvent) => {
    event.preventDefault();
    if (pending) return;
    if (kind === "resolve" && !window.confirm("Resolve this escalation with the reviewed text?")) return;
    setPending(kind);
    setError("");
    try {
      await fn();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Operation failed");
    } finally {
      setPending(null);
    }
  };
  return <article className="escalation-card">
    <div><span className="eyebrow">Case {item.caseId}</span><h3>{item.summary}</h3></div>
    <p>{item.recommendedAction}</p>
    <div className="flags">{item.matchedRedFlags.map(flag => <span key={flag}>{flag}</span>)}</div>
    {error && <p role="alert">{error}</p>}
    <form onSubmit={submit("assign", () => onAssign(item.id, assignee))}>
      <label>Assignee <input aria-label={`Assignee for ${item.id}`} value={assignee} onChange={e => setAssignee(e.target.value)} required /></label>
      <button type="submit" disabled={pending !== null}>{pending === "assign" ? "Assigning…" : "Assign escalation"}</button>
    </form>
    <form onSubmit={submit("resolve", () => onResolve(item.id, resolution))}>
      <label>Resolution <input aria-label={`Resolution for ${item.id}`} value={resolution} onChange={e => setResolution(e.target.value)} required /></label>
      <button type="submit" className="primary" disabled={pending !== null}>{pending === "resolve" ? "Resolving…" : "Resolve escalation"}</button>
    </form>
  </article>;
}

export function OperationsConsole({ cases, escalations, langfuseBaseUrl, authenticated, onAssign, onResolve }: Props) {
  return <main>
    <header className="topbar"><div><span className="brand-mark">H</span><strong>Hermes Operations</strong></div><span className="secure">{authenticated ? "Authenticated · redacted view" : "Synthetic preview · not connected"}</span></header>
    <section className="hero"><div><span className="eyebrow">Clinical coordination</span><h1>Operations console</h1><p>Manage active cases and safety escalations without exposing patient message content.</p></div><div className="metrics"><b>{cases.length}</b><span>Cases</span><b>{escalations.length}</b><span>Escalations</span></div></section>
    <div className="grid">
      <section><div className="section-title"><h2>Case inbox</h2><span>{cases.length} active</span></div>
        <div className="case-list">{cases.map(item => <article className="case-card" key={item.id}>
          <div className="case-head"><div><span className="eyebrow">{item.id}</span><h3>{item.patientLabel}</h3></div><span className={`status ${item.status}`}>{item.status}</span></div>
          <ul>{item.activity.map((activity, index) => <li key={`${activity.createdAt}-${index}`}><span className="dot"/><div><b>{activity.preview}</b><small>{activity.deliveryStatus}</small></div></li>)}</ul>
          {item.traceId && <div className="links"><a href={traceUrl(langfuseBaseUrl, item.traceId)} target="_blank" rel="noreferrer">Open trace</a><a href={evalUrl(langfuseBaseUrl, item.traceId)} target="_blank" rel="noreferrer">Open evals</a></div>}
        </article>)}</div>
      </section>
      <section><div className="section-title"><h2>Escalation queue</h2><span className="urgent">Needs review</span></div>{escalations.map(item => <EscalationCard key={item.id} item={item} onAssign={onAssign} onResolve={onResolve}/>)}</section>
    </div>
  </main>;
}
