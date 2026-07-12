import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

export const ingestTelegram = mutation({
  args: {
    internalApiSecret: v.string(),
    externalEventId: v.string(),
    patientExternalId: v.string(),
    message: v.string(),
    mustEscalate: v.boolean(),
    redFlags: v.array(v.string()),
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
      taskKey: "ingest.telegram",
      inputDigest: args.externalEventId,
      status: args.mustEscalate ? "escalated" : "ok",
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

export const listRecent = query({
  args: { limit: v.optional(v.number()) },
  handler: async (ctx, { limit = 50 }) => {
    const safeLimit = Math.min(Math.max(limit, 1), 100);
    return await ctx.db.query("cases").order("desc").take(safeLimit);
  },
});
