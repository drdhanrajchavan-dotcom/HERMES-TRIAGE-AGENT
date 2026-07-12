import type { AuthConfig } from "convex/server";

const issuer = process.env.CLERK_JWT_ISSUER_DOMAIN;
if (!issuer) throw new Error("CLERK_JWT_ISSUER_DOMAIN is required");

export default {
  providers: [{ domain: issuer, applicationID: "convex" }],
} satisfies AuthConfig;
