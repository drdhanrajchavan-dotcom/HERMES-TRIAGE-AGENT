import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

function authorize(secret: string) {
  if (!process.env.INTERNAL_API_SECRET || secret !== process.env.INTERNAL_API_SECRET) throw new Error("Unauthorized calendar-state request");
}
const holdArgs = {
  internalApiSecret: v.string(), holdKey: v.string(), caseExternalId: v.string(),
  calendarEventId: v.string(), startAt: v.number(), endAt: v.number(),
  expiresAt: v.number(), langfuseTraceId: v.string(),
};
function validateClaim(args: { holdKey: string; caseExternalId: string; startAt: number; endAt: number; expiresAt: number }) {
  if (!args.holdKey.trim() || args.holdKey.length > 128) throw new Error("Invalid hold key");
  if (!args.caseExternalId.trim() || args.caseExternalId.length > 128) throw new Error("Invalid case id");
  if (!Number.isFinite(args.startAt) || !Number.isFinite(args.endAt) || args.endAt <= args.startAt) throw new Error("Invalid slot");
  if (!Number.isFinite(args.expiresAt) || args.expiresAt > args.startAt) throw new Error("Invalid expiry");
}

export const get = query({
  args: { internalApiSecret: v.string(), holdKey: v.string() },
  handler: async (ctx, args) => { authorize(args.internalApiSecret); return await ctx.db.query("calendarHolds").withIndex("by_hold_key", q => q.eq("holdKey", args.holdKey)).unique(); },
});

export const expired = query({
  args: { internalApiSecret: v.string(), now: v.number(), limit: v.number() },
  handler: async (ctx, args) => {
    authorize(args.internalApiSecret);
    if (!Number.isInteger(args.limit) || args.limit < 1 || args.limit > 100) throw new Error("Invalid expiry batch limit");
    return await ctx.db.query("calendarHolds").withIndex("by_status_expiry", q => q.eq("status", "active").lte("expiresAt", args.now)).take(args.limit);
  },
});

export const claim = mutation({
  args: holdArgs,
  handler: async (ctx, args) => {
    authorize(args.internalApiSecret); validateClaim(args);
    const existing = await ctx.db.query("calendarHolds").withIndex("by_hold_key", q => q.eq("holdKey", args.holdKey)).unique();
    if (existing) {
      const same = existing.caseExternalId === args.caseExternalId && existing.calendarEventId === args.calendarEventId && existing.startAt === args.startAt && existing.endAt === args.endAt;
      return { outcome: same ? "existing" : "key_conflict", hold: existing };
    }
    const slot = await ctx.db.query("calendarHolds").withIndex("by_slot", q => q.eq("startAt", args.startAt).eq("endAt", args.endAt)).filter(q => q.or(q.eq(q.field("status"), "creating"), q.eq(q.field("status"), "active"), q.eq(q.field("status"), "releasing"))).first();
    if (slot) return { outcome: "slot_conflict", hold: slot };
    const now = Date.now(); const { internalApiSecret: _secret, ...record } = args;
    const id = await ctx.db.insert("calendarHolds", { ...record, status: "creating", attempts: 0, createdAt: now, updatedAt: now });
    return { outcome: "claimed", hold: await ctx.db.get(id) };
  },
});

export const activate = mutation({
  args: { internalApiSecret: v.string(), holdKey: v.string(), langfuseTraceId: v.string() },
  handler: async (ctx, args) => { authorize(args.internalApiSecret); const h = await ctx.db.query("calendarHolds").withIndex("by_hold_key", q => q.eq("holdKey", args.holdKey)).unique(); if (!h || (h.status !== "creating" && h.status !== "active")) throw new Error("Invalid activate transition"); if (h.status === "creating") await ctx.db.patch(h._id, { status: "active", updatedAt: Date.now(), langfuseTraceId: args.langfuseTraceId }); return { hold: await ctx.db.get(h._id) }; },
});

export const recordError = mutation({
  args: { internalApiSecret: v.string(), holdKey: v.string(), error: v.string(), langfuseTraceId: v.string() },
  handler: async (ctx, args) => { authorize(args.internalApiSecret); const h = await ctx.db.query("calendarHolds").withIndex("by_hold_key", q => q.eq("holdKey", args.holdKey)).unique(); if (h) await ctx.db.patch(h._id, { lastError: args.error, attempts: h.attempts + 1, updatedAt: Date.now(), langfuseTraceId: args.langfuseTraceId }); },
});

export const fail = mutation({
  args: { internalApiSecret: v.string(), holdKey: v.string(), error: v.string(), langfuseTraceId: v.string() },
  handler: async (ctx, args) => { authorize(args.internalApiSecret); const h = await ctx.db.query("calendarHolds").withIndex("by_hold_key", q => q.eq("holdKey", args.holdKey)).unique(); if (!h || h.status !== "creating") throw new Error("Invalid fail transition"); await ctx.db.patch(h._id, { status: "failed", lastError: args.error, attempts: h.attempts + 1, updatedAt: Date.now(), langfuseTraceId: args.langfuseTraceId }); },
});

export const claimRelease = mutation({
  args: { internalApiSecret: v.string(), holdKey: v.string(), releasedAt: v.number(), langfuseTraceId: v.string() },
  handler: async (ctx, args) => { authorize(args.internalApiSecret); const h = await ctx.db.query("calendarHolds").withIndex("by_hold_key", q => q.eq("holdKey", args.holdKey)).unique(); if (!h || ["released", "expired", "failed"].includes(h.status)) return { hold: null }; if (h.status !== "active" && h.status !== "releasing") throw new Error("Invalid release transition"); if (h.status === "active") await ctx.db.patch(h._id, { status: "releasing", releaseRequestedAt: args.releasedAt, updatedAt: Date.now(), langfuseTraceId: args.langfuseTraceId }); return { hold: await ctx.db.get(h._id) }; },
});

export const finalizeRelease = mutation({
  args: { internalApiSecret: v.string(), holdKey: v.string(), releasedAt: v.number(), expired: v.boolean(), langfuseTraceId: v.string() },
  handler: async (ctx, args) => { authorize(args.internalApiSecret); const h = await ctx.db.query("calendarHolds").withIndex("by_hold_key", q => q.eq("holdKey", args.holdKey)).unique(); if (!h || h.status === "released" || h.status === "expired") return { recorded: false }; if (h.status !== "releasing") throw new Error("Invalid finalize transition"); await ctx.db.patch(h._id, { status: args.expired ? "expired" : "released", releasedAt: args.releasedAt, updatedAt: Date.now(), langfuseTraceId: args.langfuseTraceId }); return { recorded: true }; },
});
