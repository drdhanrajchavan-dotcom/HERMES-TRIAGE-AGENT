import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

function authorize(internalApiSecret: string) {
  if (!process.env.INTERNAL_API_SECRET || internalApiSecret !== process.env.INTERNAL_API_SECRET) {
    throw new Error("Unauthorized calendar-state request");
  }
}

export const get = query({
  args: { internalApiSecret: v.string(), holdKey: v.string() },
  handler: async (ctx, args) => {
    authorize(args.internalApiSecret);
    return await ctx.db.query("calendarHolds").withIndex("by_hold_key", q => q.eq("holdKey", args.holdKey)).unique();
  },
});

export const expired = query({
  args: { internalApiSecret: v.string(), now: v.number() },
  handler: async (ctx, args) => {
    authorize(args.internalApiSecret);
    return await ctx.db.query("calendarHolds").withIndex("by_status_expiry", q => q.eq("status", "tentative").lte("expiresAt", args.now)).collect();
  },
});

export const save = mutation({
  args: {
    internalApiSecret: v.string(), holdKey: v.string(), caseExternalId: v.string(),
    calendarEventId: v.string(), startAt: v.number(), endAt: v.number(),
    expiresAt: v.number(), langfuseTraceId: v.string(),
  },
  handler: async (ctx, args) => {
    authorize(args.internalApiSecret);
    const existing = await ctx.db.query("calendarHolds").withIndex("by_hold_key", q => q.eq("holdKey", args.holdKey)).unique();
    if (existing) {
      const same = existing.caseExternalId === args.caseExternalId && existing.calendarEventId === args.calendarEventId && existing.startAt === args.startAt && existing.endAt === args.endAt;
      if (!same) throw new Error("Calendar hold key already belongs to another slot");
      return { holdId: existing._id, duplicate: true };
    }
    const now = Date.now();
    const { internalApiSecret: _secret, ...record } = args;
    const holdId = await ctx.db.insert("calendarHolds", { ...record, status: "tentative", createdAt: now, updatedAt: now });
    return { holdId, duplicate: false };
  },
});

export const release = mutation({
  args: { internalApiSecret: v.string(), holdKey: v.string(), releasedAt: v.number(), langfuseTraceId: v.string() },
  handler: async (ctx, args) => {
    authorize(args.internalApiSecret);
    const hold = await ctx.db.query("calendarHolds").withIndex("by_hold_key", q => q.eq("holdKey", args.holdKey)).unique();
    if (!hold || hold.status === "released") return { recorded: false };
    await ctx.db.patch(hold._id, { status: "released", releasedAt: args.releasedAt, updatedAt: Date.now(), langfuseTraceId: args.langfuseTraceId });
    return { recorded: true };
  },
});
