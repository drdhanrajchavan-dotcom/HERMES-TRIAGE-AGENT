import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

const autonomy = v.union(v.literal("auto"), v.literal("review"), v.literal("draft-only"));
const actor = v.union(v.literal("human"), v.literal("manager"), v.literal("system"));

export default defineSchema({
  roles: defineTable({
    name: v.string(),
    mission: v.string(),
    promptVersionId: v.optional(v.id("promptVersions")),
    model: v.string(),
    tools: v.array(v.string()),
    guardrails: v.object({
      maxCostUsd: v.number(),
      escalationTriggers: v.array(v.string()),
    }),
    autonomy,
    createdBy: actor,
    template: v.optional(v.boolean()),
    active: v.boolean(),
  }).index("by_name", ["name"]),

  promptVersions: defineTable({
    roleId: v.id("roles"),
    text: v.string(),
    version: v.number(),
    evalScore: v.optional(v.number()),
    status: v.union(v.literal("draft"), v.literal("published"), v.literal("blocked")),
  }).index("by_role_version", ["roleId", "version"]),

  patients: defineTable({
    externalId: v.string(),
    synthetic: v.boolean(),
    name: v.string(),
    language: v.string(),
    history: v.array(
      v.object({
        visit: v.string(),
        procedure: v.optional(v.string()),
        notes: v.string(),
        date: v.string(),
      }),
    ),
    flags: v.array(v.string()),
  }).index("by_external_id", ["externalId"]),

  cases: defineTable({
    externalEventId: v.string(),
    channel: v.string(),
    patientExternalId: v.string(),
    status: v.union(
      v.literal("open"),
      v.literal("escalated"),
      v.literal("closed"),
      v.literal("failed"),
    ),
    message: v.string(),
    mustEscalate: v.boolean(),
    redFlags: v.array(v.string()),
    plan: v.array(v.string()),
    openedAt: v.number(),
    closedAt: v.optional(v.number()),
  })
    .index("by_external_event", ["externalEventId"])
    .index("by_status_opened", ["status", "openedAt"]),

  steps: defineTable({
    caseId: v.id("cases"),
    parentStepId: v.optional(v.id("steps")),
    roleId: v.optional(v.id("roles")),
    taskKey: v.string(),
    inputDigest: v.string(),
    outputDigest: v.optional(v.string()),
    model: v.optional(v.string()),
    tokensIn: v.optional(v.number()),
    tokensOut: v.optional(v.number()),
    costUsd: v.optional(v.number()),
    latencyMs: v.optional(v.number()),
    status: v.union(
      v.literal("running"),
      v.literal("ok"),
      v.literal("bounced"),
      v.literal("failed"),
      v.literal("escalated"),
    ),
    bounceNotes: v.optional(v.array(v.string())),
    createdAt: v.number(),
  })
    .index("by_case_created", ["caseId", "createdAt"])
    .index("by_status", ["status"]),

  messages: defineTable({
    caseId: v.id("cases"),
    direction: v.union(v.literal("inbound"), v.literal("outbound")),
    channel: v.string(),
    content: v.string(),
    draftHash: v.optional(v.string()),
    complianceReviewId: v.optional(v.id("reviews")),
    deliveryStatus: v.union(
      v.literal("received"),
      v.literal("draft"),
      v.literal("approved"),
      v.literal("sent"),
      v.literal("failed"),
    ),
    externalMessageId: v.optional(v.string()),
    createdAt: v.number(),
  }).index("by_case_created", ["caseId", "createdAt"]),

  reviews: defineTable({
    caseId: v.id("cases"),
    draftHash: v.string(),
    reviewerRoleId: v.optional(v.id("roles")),
    promptVersionId: v.optional(v.id("promptVersions")),
    verdict: v.union(v.literal("pass"), v.literal("fail")),
    violations: v.array(v.string()),
    notes: v.array(v.string()),
    createdAt: v.number(),
  }).index("by_case_created", ["caseId", "createdAt"]),

  kbEntries: defineTable({
    category: v.string(),
    procedureTags: v.array(v.string()),
    language: v.string(),
    title: v.string(),
    body: v.string(),
    approved: v.boolean(),
    sourceUrl: v.optional(v.string()),
    approvedBy: v.optional(v.string()),
    approvedAt: v.optional(v.number()),
  }).index("by_approved_category", ["approved", "category"]),

  escalations: defineTable({
    caseId: v.id("cases"),
    brief: v.object({
      summary: v.string(),
      patientHistory: v.array(v.string()),
      stepsTried: v.array(v.string()),
      recommendedAction: v.string(),
      matchedRedFlags: v.array(v.string()),
    }),
    assignedTo: v.optional(v.string()),
    resolution: v.optional(v.string()),
    resolvedBy: v.optional(v.string()),
    createdAt: v.number(),
    resolvedAt: v.optional(v.number()),
  }).index("by_case", ["caseId"]),

  scheduledTasks: defineTable({
    caseId: v.optional(v.id("cases")),
    patientExternalId: v.string(),
    type: v.string(),
    dueAt: v.number(),
    status: v.union(
      v.literal("pending"),
      v.literal("running"),
      v.literal("complete"),
      v.literal("failed"),
      v.literal("cancelled"),
    ),
    idempotencyKey: v.string(),
  })
    .index("by_due_status", ["status", "dueAt"])
    .index("by_idempotency_key", ["idempotencyKey"]),

  settings: defineTable({
    key: v.string(),
    value: v.any(),
    updatedBy: actor,
    updatedAt: v.number(),
  }).index("by_key", ["key"]),
});
