import { describe, expect, it, vi } from "vitest";
import worker from "../src/index";

const env = {
  RUNNER_ORIGIN: "https://runner.example",
  TELEGRAM_WEBHOOK_SECRET: "telegram-secret",
  WEBHOOK_SHARED_SECRET: "edge-secret",
};

describe("clinic agency edge", () => {
  it("forwards the public root to the runner status endpoint", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ service: "clinic-agency-runner", status: "ready" }),
    );

    const response = await worker.fetch(new Request("https://edge.example/"), env);

    expect(response.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledWith(
      "https://runner.example/",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
    fetchSpy.mockRestore();
  });

  it("rejects invalid Telegram secrets without reaching the runner", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const response = await worker.fetch(
      new Request("https://edge.example/webhooks/telegram", {
        method: "POST",
        headers: { "X-Telegram-Bot-Api-Secret-Token": "wrong" },
        body: "{}",
      }),
      env,
    );

    expect(response.status).toBe(401);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("forwards an authenticated bounded request to the runner", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response('{"status":"accepted"}', {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const response = await worker.fetch(
      new Request("https://edge.example/webhooks/telegram", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": "2",
          "X-Telegram-Bot-Api-Secret-Token": "telegram-secret",
        },
        body: "{}",
      }),
      env,
    );

    expect(response.status).toBe(202);
    expect(fetchSpy).toHaveBeenCalledOnce();
    expect((fetchSpy.mock.calls[0][0] as Request).url).toBe(
      "https://runner.example/webhooks/telegram",
    );
    expect(
      (fetchSpy.mock.calls[0][0] as Request).headers.get("X-Clinic-Edge-Secret"),
    ).toBe("edge-secret");
    fetchSpy.mockRestore();
  });
});
