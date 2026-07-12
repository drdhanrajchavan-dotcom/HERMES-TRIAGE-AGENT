export type OperatorRole = "operator" | "manager" | "clinician";
export type OperatorIdentity = { subject?: string; role?: unknown };

const OPERATOR_ROLES = new Set<OperatorRole>(["operator", "manager", "clinician"]);

export function assertOperatorIdentity(identity: OperatorIdentity | null) {
  if (!identity?.subject) throw new Error("Unauthenticated");
  if (typeof identity.role !== "string" || !OPERATOR_ROLES.has(identity.role as OperatorRole)) {
    throw new Error("Forbidden");
  }
  return { actorId: identity.subject, role: identity.role as OperatorRole };
}

export function requireOperatorRole<T extends { role: OperatorRole }>(
  actor: T,
  allowed: readonly OperatorRole[],
) {
  if (!allowed.includes(actor.role)) throw new Error("Forbidden");
  return actor;
}

export function redactActivity(message: {
  direction: "inbound" | "outbound";
  deliveryStatus: string;
  createdAt: number;
}) {
  return {
    direction: message.direction,
    deliveryStatus: message.deliveryStatus,
    createdAt: message.createdAt,
    preview:
      message.direction === "inbound"
        ? "Inbound patient message (redacted)"
        : "Outbound clinic message (redacted)",
  };
}

function base(url: string) {
  return url.replace(/\/$/, "");
}
export function buildLangfuseTraceUrl(url: string, traceId: string) {
  return `${base(url)}/trace/${encodeURIComponent(traceId)}`;
}
export function buildEvalUrl(url: string, traceId: string) {
  return `${base(url)}/project/evals?traceId=${encodeURIComponent(traceId)}`;
}

type EscalationState = {
  assignedTo?: string;
  resolution?: string;
  resolvedBy?: string;
  resolvedAt?: number;
};
function assertOpen(escalation: EscalationState) {
  if (escalation.resolvedAt !== undefined) throw new Error("Escalation is already resolved");
}
export function assignEscalation(escalation: EscalationState, assignee: string) {
  assertOpen(escalation);
  if (!assignee.trim()) throw new Error("Assignee is required");
  return { assignedTo: assignee.trim() };
}
export function resolveEscalation(escalation: EscalationState, resolution: string, actorId: string, now: number) {
  const normalized = resolution.trim();
  if (!normalized) throw new Error("Resolution is required");
  if (escalation.resolvedAt !== undefined) {
    if (escalation.resolution === normalized && escalation.resolvedBy === actorId) {
      return { duplicate: true as const };
    }
    throw new Error("Escalation is already resolved");
  }
  return { resolution: normalized, resolvedBy: actorId, resolvedAt: now };
}

export function scheduleLifecycleTask(
  existing: { _id: string; idempotencyKey: string } | null,
  input: { idempotencyKey: string },
) {
  if (!input.idempotencyKey.trim()) throw new Error("Idempotency key is required");
  if (input.idempotencyKey.length > 128) throw new Error("Idempotency key is too long");
  if (existing) return { taskId: existing._id, duplicate: true as const };
  return { duplicate: false as const };
}
