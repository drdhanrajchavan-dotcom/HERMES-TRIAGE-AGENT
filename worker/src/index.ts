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

function judgeQuickstart(): Response {
  const body = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hermes Clinic Agent · Judge Quickstart</title><style>body{margin:0;background:#07111f;color:#e8f0fa;font:16px system-ui;line-height:1.55}main{max-width:760px;margin:auto;padding:64px 24px}h1{font-size:clamp(2.2rem,7vw,4.6rem);line-height:1;margin:.3em 0}.tag{color:#78d8c8;text-transform:uppercase;letter-spacing:.14em}.cta{display:inline-block;margin:24px 0;padding:14px 22px;border-radius:10px;background:#78d8c8;color:#07111f;text-decoration:none;font-weight:750}.card{background:#101d2e;border:1px solid #253851;border-radius:14px;padding:20px;margin:18px 0}small{color:#9fb0c5}</style><main><p class="tag">Hackathon judge quickstart</p><h1>Hermes clinic coordination agent</h1><p>Test safety-aware clinic intake, cited ClearSkin/HairMD information, escalation, and tentative appointment workflows in Telegram.</p><a class="cta" href="https://t.me/hermestriagent_bot">Open the Telegram agent</a><section class="card"><h2>Suggested synthetic prompts</h2><ol><li>What treatments does ClearSkin offer for acne scars?</li><li>I want a tentative appointment next Tuesday afternoon.</li><li>Synthetic test: I have difficulty breathing after a procedure.</li><li>Can you guarantee this will permanently cure hair loss?</li></ol></section><p><strong>Use synthetic data only.</strong> Do not enter real patient names, phone numbers, records, or images.</p><small>Deterministic red flags run before model reasoning. Outbound text passes deterministic compliance and exact-draft authorization.</small></main></html>`;
  return new Response(body, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "public, max-age=300",
      "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
    },
  });
}

export default {
  async scheduled(
    _controller: ScheduledController,
    env: Env,
    _ctx: ExecutionContext,
  ): Promise<void> {
    const response = await fetch(
      `${env.RUNNER_ORIGIN.replace(/\/$/, "")}/internal/calendar/expire`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Clinic-Edge-Secret": env.WEBHOOK_SHARED_SECRET,
        },
        body: JSON.stringify({ limit: 100 }),
      },
    );
    if (!response.ok) throw new Error(`Calendar expiry failed with HTTP ${response.status}`);
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/judge" && request.method === "GET") {
      return judgeQuickstart();
    }
    if ((url.pathname === "/" || url.pathname === "/health") && request.method === "GET") {
      return fetch(`${env.RUNNER_ORIGIN.replace(/\/$/, "")}${url.pathname}`, {
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
