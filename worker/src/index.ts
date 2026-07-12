export interface Env {
  RUNNER_ORIGIN: string;
  TELEGRAM_WEBHOOK_SECRET: string;
  WEBHOOK_SHARED_SECRET: string;
}

const MAX_BODY_BYTES = 1_000_000;

async function digest(value: string): Promise<Uint8Array> {
  const bytes = new TextEncoder().encode(value);
  return new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
}

async function secretsMatch(left: string, right: string): Promise<boolean> {
  const [leftDigest, rightDigest] = await Promise.all([digest(left), digest(right)]);
  let difference = 0;
  for (let index = 0; index < leftDigest.length; index += 1) {
    difference |= leftDigest[index] ^ rightDigest[index];
  }
  return difference === 0;
}

function json(status: number, body: object): Response {
  return Response.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/health" && request.method === "GET") {
      return fetch(`${env.RUNNER_ORIGIN.replace(/\/$/, "")}/health`, {
        headers: { Accept: "application/json" },
      });
    }
    if (url.pathname !== "/webhooks/telegram" || request.method !== "POST") {
      return json(404, { error: "not_found" });
    }
    const suppliedSecret =
      request.headers.get("X-Telegram-Bot-Api-Secret-Token") ?? "";
    if (
      !suppliedSecret ||
      !(await secretsMatch(suppliedSecret, env.TELEGRAM_WEBHOOK_SECRET))
    ) {
      return json(401, { error: "unauthorized" });
    }
    const declaredLength = Number(request.headers.get("Content-Length") ?? 0);
    if (declaredLength > MAX_BODY_BYTES) {
      return json(413, { error: "payload_too_large" });
    }
    const body = await request.arrayBuffer();
    if (body.byteLength > MAX_BODY_BYTES) {
      return json(413, { error: "payload_too_large" });
    }
    const headers = new Headers();
    headers.set("Content-Type", "application/json");
    headers.set("X-Telegram-Bot-Api-Secret-Token", suppliedSecret);
    headers.set("X-Clinic-Edge-Secret", env.WEBHOOK_SHARED_SECRET);
    return fetch(
      new Request(
        `${env.RUNNER_ORIGIN.replace(/\/$/, "")}/webhooks/telegram`,
        { method: "POST", headers, body },
      ),
    );
  },
};
