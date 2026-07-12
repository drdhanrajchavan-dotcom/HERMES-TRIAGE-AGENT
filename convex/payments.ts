import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

function authorize(internalApiSecret: string) {
  if (!process.env.INTERNAL_API_SECRET || internalApiSecret !== process.env.INTERNAL_API_SECRET) {
    throw new Error("Unauthorized payment-state request");
  }
}

export const createDepositIntent = mutation({
  args: {
    internalApiSecret: v.string(),
    externalEventId: v.string(),
    holdKey: v.string(),
    productId: v.string(),
    langfuseTraceId: v.string(),
  },
  handler: async (ctx, args) => {
    authorize(args.internalApiSecret);
    const existing = await ctx.db
      .query("bookingHolds")
      .withIndex("by_hold_key", (q) => q.eq("holdKey", args.holdKey))
      .unique();
    if (existing) return { holdId: existing._id, duplicate: true };
    const caseRecord = await ctx.db
      .query("cases")
      .withIndex("by_external_event", (q) => q.eq("externalEventId", args.externalEventId))
      .unique();
    if (!caseRecord) throw new Error("Case not found for deposit intent");
    const now = Date.now();
    const holdId = await ctx.db.insert("bookingHolds", {
      caseId: caseRecord._id,
      holdKey: args.holdKey,
      productId: args.productId,
      status: "pending",
      langfuseTraceId: args.langfuseTraceId,
      createdAt: now,
      updatedAt: now,
    });
    return { holdId, duplicate: false };
  },
});

export const markCheckoutCreated = mutation({
  args: {
    internalApiSecret: v.string(),
    holdKey: v.string(),
    checkoutSessionId: v.string(),
    checkoutUrl: v.string(),
    langfuseTraceId: v.string(),
  },
  handler: async (ctx, args) => {
    authorize(args.internalApiSecret);
    const hold = await ctx.db
      .query("bookingHolds")
      .withIndex("by_hold_key", (q) => q.eq("holdKey", args.holdKey))
      .unique();
    if (!hold) throw new Error("Deposit intent not found");
    if (hold.checkoutSessionId && hold.checkoutSessionId !== args.checkoutSessionId) {
      throw new Error("Deposit intent already belongs to another checkout session");
    }
    await ctx.db.patch(hold._id, {
      status: "checkout_created",
      checkoutSessionId: args.checkoutSessionId,
      checkoutUrl: args.checkoutUrl,
      langfuseTraceId: args.langfuseTraceId,
      updatedAt: Date.now(),
    });
    return { recorded: true };
  },
});

export const markCheckoutUncertain = mutation({
  args: {
    internalApiSecret: v.string(),
    holdKey: v.string(),
    langfuseTraceId: v.string(),
  },
  handler: async (ctx, args) => {
    authorize(args.internalApiSecret);
    const hold = await ctx.db
      .query("bookingHolds")
      .withIndex("by_hold_key", (q) => q.eq("holdKey", args.holdKey))
      .unique();
    if (!hold) throw new Error("Deposit intent not found");
    if (hold.status === "checkout_created" || hold.status === "paid") {
      return { recorded: false };
    }
    await ctx.db.patch(hold._id, {
      status: "uncertain",
      langfuseTraceId: args.langfuseTraceId,
      updatedAt: Date.now(),
    });
    return { recorded: true };
  },
});

export const getByHoldKey = query({
  args: { holdKey: v.string() },
  handler: async (ctx, { holdKey }) =>
    await ctx.db
      .query("bookingHolds")
      .withIndex("by_hold_key", (q) => q.eq("holdKey", holdKey))
      .unique(),
});
