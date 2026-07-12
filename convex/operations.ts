import { v } from "convex/values";
import { mutation, query } from "./_generated/server";
import {
  assertOperatorIdentity,
  assignEscalation as assignmentPatch,
  redactActivity,
  requireOperatorRole,
  resolveEscalation as resolutionPatch,
  scheduleLifecycleTask,
} from "./operationsCore";

async function operator(ctx: { auth: { getUserIdentity(): Promise<any> } }) {
  return assertOperatorIdentity(await ctx.auth.getUserIdentity());
}

export const listCases = query({
  args: { limit: v.optional(v.number()) },
  handler: async (ctx, { limit = 50 }) => {
    await operator(ctx);
    const records = await ctx.db.query("cases").order("desc").take(Math.min(Math.max(limit, 1), 100));
    return Promise.all(records.map(async (record) => {
      const messages = await ctx.db.query("messages").withIndex("by_case_created", q => q.eq("caseId", record._id)).collect();
      return {
        id: record._id,
        status: record.status,
        patientLabel: `Patient …${record.patientExternalId.slice(-4)}`,
        openedAt: record.openedAt,
        traceId: record.langfuseTraceId,
        mustEscalate: record.mustEscalate,
        redFlags: record.redFlags,
        activity: messages.map(redactActivity),
      };
    }));
  },
});

export const listEscalations = query({
  args: { includeResolved: v.optional(v.boolean()) },
  handler: async (ctx, { includeResolved = false }) => {
    await operator(ctx);
    const rows = await ctx.db.query("escalations").order("desc").collect();
    return rows.filter(row => includeResolved || row.resolvedAt === undefined).map(row => ({
      id: row._id,
      caseId: row.caseId,
      summary: row.brief.summary,
      recommendedAction: row.brief.recommendedAction,
      matchedRedFlags: row.brief.matchedRedFlags,
      assignedTo: row.assignedTo,
      resolution: row.resolution,
      resolvedBy: row.resolvedBy,
      createdAt: row.createdAt,
      resolvedAt: row.resolvedAt,
    }));
  },
});

export const assignEscalation = mutation({
  args: { escalationId: v.id("escalations"), assignedTo: v.string() },
  handler: async (ctx, args) => {
    const actor = await operator(ctx);
    requireOperatorRole(actor, ["operator", "manager"]);
    const escalation = await ctx.db.get(args.escalationId);
    if (!escalation) throw new Error("Escalation not found");
    await ctx.db.patch(args.escalationId, assignmentPatch(escalation, args.assignedTo));
    return { assigned: true };
  },
});

export const resolveEscalation = mutation({
  args: { escalationId: v.id("escalations"), resolution: v.string() },
  handler: async (ctx, args) => {
    const actor = await operator(ctx);
    requireOperatorRole(actor, ["clinician", "manager"]);
    const escalation = await ctx.db.get(args.escalationId);
    if (!escalation) throw new Error("Escalation not found");
    const now = Date.now();
    const patch = resolutionPatch(escalation, args.resolution, actor.actorId, now);
    if ("duplicate" in patch) return { resolved: true, duplicate: true };
    await ctx.db.patch(args.escalationId, patch);
    const unresolved = (
      await ctx.db
        .query("escalations")
        .withIndex("by_case", q => q.eq("caseId", escalation.caseId))
        .collect()
    ).some(row => row._id !== args.escalationId && row.resolvedAt === undefined);
    const caseRecord = await ctx.db.get(escalation.caseId);
    if (!unresolved && caseRecord?.status === "escalated") {
      await ctx.db.patch(escalation.caseId, { status: "closed", closedAt: now });
    }
    return { resolved: true, duplicate: false };
  },
});

export const scheduleLifecycle = mutation({
  args: {
    caseId: v.id("cases"),
    type: v.union(
      v.literal("post_treatment_checkin"),
      v.literal("missed_appointment_recovery"),
      v.literal("lead_followup"),
    ),
    dueAt: v.number(),
    idempotencyKey: v.string(),
  },
  handler: async (ctx, args) => {
    const actor = await operator(ctx);
    requireOperatorRole(actor, ["operator", "manager"]);
    const caseRecord = await ctx.db.get(args.caseId);
    if (!caseRecord) throw new Error("Case not found");
    if (caseRecord.status === "closed" || caseRecord.status === "failed") {
      throw new Error("Cannot schedule lifecycle work for a terminal case");
    }
    const now = Date.now();
    if (args.dueAt < now || args.dueAt > now + 180 * 24 * 60 * 60 * 1000) {
      throw new Error("Lifecycle dueAt is outside the allowed scheduling window");
    }
    const existing = await ctx.db.query("scheduledTasks").withIndex("by_idempotency_key", q => q.eq("idempotencyKey", args.idempotencyKey)).unique();
    const decision = scheduleLifecycleTask(existing, args);
    if (decision.duplicate) return decision;
    const taskId = await ctx.db.insert("scheduledTasks", {
      ...args,
      patientExternalId: caseRecord.patientExternalId,
      status: "pending",
    });
    return { taskId, duplicate: false };
  },
});
