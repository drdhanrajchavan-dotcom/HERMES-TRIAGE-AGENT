import { useMutation, useQuery } from "convex/react";
import type { Id } from "../../convex/_generated/dataModel";
import { api } from "../../convex/_generated/api";

import { OperationsConsole } from "./OperationsConsole";

const APPROVED_LANGFUSE_ORIGIN = "https://us.cloud.langfuse.com";

function langfuseOrigin(): string {
  const configured = import.meta.env.VITE_LANGFUSE_BASE_URL;
  if (!configured) throw new Error("VITE_LANGFUSE_BASE_URL is required");
  const url = new URL(configured);
  if (url.protocol !== "https:" || url.origin !== APPROVED_LANGFUSE_ORIGIN) {
    throw new Error("VITE_LANGFUSE_BASE_URL is not an approved Langfuse origin");
  }
  return url.origin;
}

export function LiveOperationsConsole() {
  const cases = useQuery(api.operations.listCases, { limit: 50 });
  const escalations = useQuery(api.operations.listEscalations, { includeResolved: false });
  const assign = useMutation(api.operations.assignEscalation);
  const resolve = useMutation(api.operations.resolveEscalation);

  if (cases === undefined || escalations === undefined) {
    return <main className="auth-state"><p>Loading redacted operations data…</p></main>;
  }

  return <OperationsConsole
    cases={cases}
    escalations={escalations}
    langfuseBaseUrl={langfuseOrigin()}
    authenticated
    onAssign={(id, assignedTo) => assign({ escalationId: id as Id<"escalations">, assignedTo }).then(() => undefined)}
    onResolve={(id, resolution) => resolve({ escalationId: id as Id<"escalations">, resolution }).then(() => undefined)}
  />;
}
