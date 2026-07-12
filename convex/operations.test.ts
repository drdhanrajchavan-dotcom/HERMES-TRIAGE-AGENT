import { describe, expect, it } from "vitest";
import {
  assertOperatorIdentity,
  buildEvalUrl,
  buildLangfuseTraceUrl,
  redactActivity,
  scheduleLifecycleTask,
  assignEscalation,
  resolveEscalation,
  requireOperatorRole,
} from "./operationsCore";

describe("operations authorization boundary", () => {
  it("rejects anonymous and non-operator identities", () => {
    expect(() => assertOperatorIdentity(null)).toThrow("Unauthenticated");
    expect(() => assertOperatorIdentity({ subject: "patient-1", role: "patient" })).toThrow("Forbidden");
  });

  it("accepts only explicit operator roles", () => {
    expect(assertOperatorIdentity({ subject: "ops-1", role: "operator" })).toEqual({ actorId: "ops-1", role: "operator" });
    expect(assertOperatorIdentity({ subject: "mgr-1", role: "manager" }).role).toBe("manager");
  });

  it("enforces permissions per operation", () => {
    expect(() =>
      requireOperatorRole({ actorId: "ops-1", role: "operator" }, ["clinician"]),
    ).toThrow("Forbidden");
    expect(
      requireOperatorRole({ actorId: "clinician-1", role: "clinician" }, ["clinician"]),
    ).toMatchObject({ role: "clinician" });
  });
});

describe("redacted activity", () => {
  it("never returns raw patient content", () => {
    const activity = redactActivity({ direction: "inbound", deliveryStatus: "received", createdAt: 1 });
    expect(activity).toEqual({ direction: "inbound", deliveryStatus: "received", createdAt: 1, preview: "Inbound patient message (redacted)" });
    expect(activity).not.toHaveProperty("content");
  });
});

describe("operations links", () => {
  it("encodes trace and eval identifiers", () => {
    expect(buildLangfuseTraceUrl("https://observe.example/", "trace/a b")).toBe("https://observe.example/trace/trace%2Fa%20b");
    expect(buildEvalUrl("https://observe.example", "trace/a b")).toBe("https://observe.example/project/evals?traceId=trace%2Fa%20b");
  });
});

describe("escalation lifecycle", () => {
  const open = { assignedTo: undefined, resolution: undefined, resolvedBy: undefined, resolvedAt: undefined };

  it("assigns an unresolved escalation", () => {
    expect(assignEscalation(open, "clinician-7")).toMatchObject({ assignedTo: "clinician-7" });
  });

  it("cannot assign or change an already resolved escalation", () => {
    const resolved = { ...open, resolution: "Called patient", resolvedBy: "ops-1", resolvedAt: 10 };
    expect(() => assignEscalation(resolved, "ops-2")).toThrow("already resolved");
    expect(() => resolveEscalation(resolved, "again", "ops-2", 11)).toThrow("already resolved");
  });

  it("treats an identical resolution retry as idempotent", () => {
    const resolved = { ...open, resolution: "Called patient", resolvedBy: "clinician-1", resolvedAt: 10 };

    expect(resolveEscalation(resolved, "Called patient", "clinician-1", 11)).toEqual({ duplicate: true });
  });

  it("requires meaningful resolution text", () => {
    expect(() => resolveEscalation(open, "  ", "ops-1", 10)).toThrow("Resolution is required");
    expect(resolveEscalation(open, "Patient contacted", "ops-1", 10)).toMatchObject({ resolution: "Patient contacted", resolvedBy: "ops-1", resolvedAt: 10 });
  });
});

describe("idempotent lifecycle scheduling", () => {
  it("returns the existing task for the same idempotency key", () => {
    const existing = { _id: "task-1", idempotencyKey: "followup:case-1:day-3" };
    expect(scheduleLifecycleTask(existing, { idempotencyKey: existing.idempotencyKey })).toEqual({ taskId: "task-1", duplicate: true });
  });

  it("requires a stable non-empty idempotency key", () => {
    expect(() => scheduleLifecycleTask(null, { idempotencyKey: " " })).toThrow("Idempotency key is required");
    expect(scheduleLifecycleTask(null, { idempotencyKey: "followup:case-1:day-3" })).toEqual({ duplicate: false });
  });
});
