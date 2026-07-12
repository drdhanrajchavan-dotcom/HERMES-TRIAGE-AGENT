import { v } from "convex/values";
import { mutation, query } from "./_generated/server";
import { assertOperatorIdentity } from "./operationsCore";

async function authorizeOperator(ctx: { auth: { getUserIdentity(): Promise<any> } }) {
  return assertOperatorIdentity(await ctx.auth.getUserIdentity());
}

export const ingestTelegram = mutation({
  args: {
    internalApiSecret: v.string(),
    externalEventId: v.string(),
    patientExternalId: v.string(),
    message: v.string(),
    mustEscalate: v.boolean(),
    redFlags: v.array(v.string()),
    langfuseTraceId: v.string(),
    openedAt: v.number(),
  },
  handler: async (ctx, args) => {
    const expectedSecret = process.env.INTERNAL_API_SECRET;
    if (!expectedSecret || args.internalApiSecret !== expectedSecret) {
      throw new Error("Unauthorized ingestion request");
    }
    const existing = await ctx.db
      .query("cases")
      .withIndex("by_external_event", (q) => q.eq("externalEventId", args.externalEventId))
      .unique();
    if (existing) return { caseId: existing._id, duplicate: true };

    const status = args.mustEscalate ? "escalated" : "open";
    const { internalApiSecret: _, ...caseInput } = args;
    const caseId = await ctx.db.insert("cases", {
      ...caseInput,
      channel: "telegram",
      status,
      plan: [],
    });
    await ctx.db.insert("messages", {
      caseId,
      direction: "inbound",
      channel: "telegram",
      content: args.message,
      deliveryStatus: "received",
      createdAt: args.openedAt,
    });
    await ctx.db.insert("steps", {
      caseId,
      status: args.mustEscalate ? "escalated" : "ok",
      langfuseTraceId: args.langfuseTraceId,
      costRunning: 0,
      createdAt: args.openedAt,
    });
    if (args.mustEscalate) {
      await ctx.db.insert("escalations", {
        caseId,
        brief: {
          summary: "Potential clinical red flag detected during intake.",
          patientHistory: [],
          stepsTried: ["Deterministic red-flag precheck"],
          recommendedAction: "A clinic team member should review and contact the patient promptly.",
          matchedRedFlags: args.redFlags,
        },
        createdAt: args.openedAt,
      });
    }
    return { caseId, duplicate: false };
  },
});

export const recordPlan = mutation({
  args: {
    internalApiSecret: v.string(),
    externalEventId: v.string(),
    langfuseTraceId: v.string(),
    steps: v.array(
      v.object({
        key: v.string(),
        role: v.string(),
        dependsOn: v.array(v.string()),
      }),
    ),
  },
  handler: async (ctx, args) => {
    const expectedSecret = process.env.INTERNAL_API_SECRET;
    if (!expectedSecret || args.internalApiSecret !== expectedSecret) {
      throw new Error("Unauthorized ingestion request");
    }
    const caseRecord = await ctx.db
      .query("cases")
      .withIndex("by_external_event", (q) => q.eq("externalEventId", args.externalEventId))
      .unique();
    if (!caseRecord) throw new Error("Case not found for manager plan");
    await ctx.db.patch(caseRecord._id, { plan: args.steps });
    await ctx.db.insert("steps", {
      caseId: caseRecord._id,
      status: "ok",
      langfuseTraceId: args.langfuseTraceId,
      costRunning: 0,
      createdAt: Date.now(),
    });
    return { recorded: true };
  },
});

export const recordApprovedDelivery = mutation({
  args: {
    internalApiSecret: v.string(),
    externalEventId: v.string(),
    text: v.string(),
    draftHash: v.string(),
    reviewDraftHash: v.string(),
    violations: v.array(v.string()),
    externalMessageId: v.string(),
    langfuseTraceId: v.string(),
  },
  handler: async (ctx, args) => {
    const expectedSecret = process.env.INTERNAL_API_SECRET;
    if (!expectedSecret || args.internalApiSecret !== expectedSecret) {
      throw new Error("Unauthorized ingestion request");
    }
    if (args.draftHash !== args.reviewDraftHash || args.violations.length > 0) {
      throw new Error("Outbound delivery lacks an exact passing review");
    }
    const existingDelivery = await ctx.db
      .query("messages")
      .withIndex("by_external_message", (q) =>
        q.eq("externalMessageId", args.externalMessageId),
      )
      .unique();
    if (existingDelivery) return { recorded: false, duplicate: true };

    const caseRecord = await ctx.db
      .query("cases")
      .withIndex("by_external_event", (q) => q.eq("externalEventId", args.externalEventId))
      .unique();
    if (!caseRecord) throw new Error("Case not found for outbound delivery");

    const createdAt = Date.now();
    const reviewId = await ctx.db.insert("reviews", {
      caseId: caseRecord._id,
      draftHash: args.reviewDraftHash,
      verdict: "pass",
      violations: [],
      notes: [],
      createdAt,
    });
    await ctx.db.insert("messages", {
      caseId: caseRecord._id,
      direction: "outbound",
      channel: "telegram",
      content: args.text,
      draftHash: args.draftHash,
      complianceReviewId: reviewId,
      deliveryStatus: "sent",
      externalMessageId: args.externalMessageId,
      createdAt,
    });
    await ctx.db.insert("steps", {
      caseId: caseRecord._id,
      status: "ok",
      langfuseTraceId: args.langfuseTraceId,
      costRunning: 0,
      createdAt,
    });
    return { recorded: true, duplicate: false };
  },
});

export const listCaseSteps = query({
  args: { externalEventId: v.string() },
  handler: async (ctx, { externalEventId }) => {
    await authorizeOperator(ctx);
    const caseRecord = await ctx.db
      .query("cases")
      .withIndex("by_external_event", (q) => q.eq("externalEventId", externalEventId))
      .unique();
    if (!caseRecord) return [];
    return await ctx.db
      .query("steps")
      .withIndex("by_case_created", (q) => q.eq("caseId", caseRecord._id))
      .collect();
  },
});

export const listRecent = query({
  args: { limit: v.optional(v.number()) },
  handler: async (ctx, { limit = 50 }) => {
    await authorizeOperator(ctx);
    const safeLimit = Math.min(Math.max(limit, 1), 100);
    const records = await ctx.db.query("cases").order("desc").take(safeLimit);
    return records.map(record => ({
      id: record._id,
      status: record.status,
      patientLabel: `Patient …${record.patientExternalId.slice(-4)}`,
      openedAt: record.openedAt,
      closedAt: record.closedAt,
      mustEscalate: record.mustEscalate,
      langfuseTraceId: record.langfuseTraceId,
    }));
  },
});
