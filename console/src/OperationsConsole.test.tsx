import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OperationsConsole } from "./OperationsConsole";

afterEach(cleanup);

const cases = [{ id: "case-1", status: "escalated" as const, patientLabel: "Synthetic patient 0042", openedAt: 1, traceId: "trace-1", activity: [{ direction: "inbound" as const, deliveryStatus: "received", createdAt: 1, preview: "Inbound patient message (redacted)" }] }];
const escalations = [{ id: "esc-1", caseId: "case-1", summary: "Potential clinical red flag", recommendedAction: "Prompt clinician review", matchedRedFlags: ["breathing difficulty"], createdAt: 1 }];
const noop = async () => undefined;

describe("OperationsConsole", () => {
  it("renders the inbox and redacted activity without raw patient messages", () => {
    render(<OperationsConsole cases={cases} escalations={escalations} langfuseBaseUrl="https://observe.example" authenticated onAssign={noop} onResolve={noop} />);
    expect(screen.getByRole("heading", { name: "Case inbox" })).toBeInTheDocument();
    expect(screen.getByText("Inbound patient message (redacted)")).toBeInTheDocument();
    expect(screen.queryByText(/raw patient/i)).not.toBeInTheDocument();
  });

  it("provides Langfuse trace and eval deep links", () => {
    render(<OperationsConsole cases={cases} escalations={escalations} langfuseBaseUrl="https://observe.example" authenticated onAssign={noop} onResolve={noop} />);
    expect(screen.getByRole("link", { name: "Open trace" })).toHaveAttribute("href", "https://observe.example/trace/trace-1");
    expect(screen.getByRole("link", { name: "Open evals" })).toHaveAttribute("href", "https://observe.example/project/evals?traceId=trace-1");
  });

  it("assigns and resolves an escalation", async () => {
    const assign = vi.fn().mockResolvedValue(undefined);
    const resolve = vi.fn().mockResolvedValue(undefined);
    render(<OperationsConsole cases={cases} escalations={escalations} langfuseBaseUrl="https://observe.example" authenticated onAssign={assign} onResolve={resolve} />);
    fireEvent.change(screen.getByLabelText("Assignee for esc-1"), { target: { value: "clinician-7" } });
    fireEvent.click(screen.getByRole("button", { name: "Assign escalation" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("esc-1", "clinician-7"));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.change(screen.getByLabelText("Resolution for esc-1"), { target: { value: "Patient contacted" } });
    fireEvent.click(screen.getByRole("button", { name: "Resolve escalation" }));
    expect(resolve).toHaveBeenCalledWith("esc-1", "Patient contacted");
  });
});
