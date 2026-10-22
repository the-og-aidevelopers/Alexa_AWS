import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Dashboard from "../pages/Dashboard";
import MedicineDialog from "../components/MedicineDialog";
import { pageFor } from "../App";

const session = { identity: { household_name: "Test home" }, provider: "local", signOut: vi.fn() };

const board = {
  doses: [{ schedule_id: 1, person_name: "Raj", dose_label: "dopamine", time_local: "08:00", time_spoken: "8 AM", state: "overdue", minutes_late: 95 }],
  alerts: [{ schedule_id: 1, person_name: "Raj", dose_label: "dopamine", time_spoken: "8 AM", minutes_late: 95 }],
  people: ["Raj", "Mom"],
  schedules: [{ schedule_id: 1, person_name: "Raj", dose_label: "dopamine", time_local: "08:00", time_spoken: "8 AM", days: [0, 4], days_spoken: "on Monday and Friday" }],
};

let calls;
let reminders = [];

beforeEach(() => {
  calls = [];
  reminders = [];
  window.sessionStorage.clear();
  window.speechSynthesis = undefined;
  global.fetch = vi.fn(async (url, options = {}) => {
    calls.push({ url, method: options.method || "GET", body: options.body && JSON.parse(options.body) });
    if (url === "/api/reminders") return { ok: true, status: 200, json: async () => ({ reminders: reminders }) };
    if (url === "/api/today") return { ok: true, status: 200, json: async () => board };
    if (url === "/api/talk") return { ok: true, status: 200, json: async () => ({ speech: "Nothing is due.", tool: "list_due_doses", transport: "streamable-http", protocol: "2025-11-25", speaker: "older_adult" }) };
    if (url === "/api/people") return { ok: true, status: 200, json: async () => ({ ok: true, person_name: "Priya" }) };
    return { ok: true, status: 200, json: async () => ({}) };
  });
});

afterEach(() => vi.restoreAllMocks());

describe("routing", () => {
  it("maps paths to pages", () => {
    expect(pageFor("/")).toBe("dashboard");
    expect(pageFor("/agent")).toBe("agent");
    expect(pageFor("/login")).toBe("login");
  });
});

describe("Dashboard", () => {
  it("shows people with dose counts, the alert and today's doses", async () => {
    render(<Dashboard session={session} />);
    expect(await screen.findByText("Raj", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("Mom", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("1 dose is overdue.")).toBeInTheDocument();
    expect(screen.getByText("Overdue")).toBeInTheDocument();
    expect(screen.getByText("8 AM")).toBeInTheDocument();
  });

  it("sends a typed sentence to /api/talk and shows the reply with its tool trace", async () => {
    const user = userEvent.setup();
    render(<Dashboard session={session} />);
    await user.type(screen.getByLabelText("What to say"), "What's due now?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Nothing is due.")).toBeInTheDocument();
    expect(screen.getByText("Nothing is due.").closest("li")).toHaveAttribute("title", expect.stringContaining("MCP list_due_doses"));
    expect(calls.find((call) => call.url === "/api/talk").body).toEqual({ utterance: "What's due now?", speaker: "older_adult" });
  });

  it("adds a person from the modal and opens their details", async () => {
    const user = userEvent.setup();
    render(<Dashboard session={session} />);
    await user.click(screen.getByRole("button", { name: "+ Add person" }));
    await user.type(await screen.findByPlaceholderText("Raj"), "Priya");
    const dialog = screen.getByRole("dialog", { name: "Add a person", hidden: true });
    await user.click(within(dialog).getByRole("button", { name: "Add person", hidden: true }));
    await waitFor(() => expect(calls.some((call) => call.url === "/api/people" && call.body.name === "Priya")).toBe(true));
  });

  it("has no clear-log button; clearing is a chat action", async () => {
    render(<Dashboard session={session} />);
    await screen.findByText("1 dose is overdue.");
    expect(screen.queryByText(/Clear today's log/i, { selector: "button.btn" })).toBeNull();
  });
});

describe("MedicineDialog", () => {
  it("requires at least one day and saves times and days", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn(async () => "");
    render(<MedicineDialog open person="Raj" editing={null} onClose={() => {}} onSave={onSave} />);
    await user.type(screen.getByPlaceholderText("lisinopril"), "aspirin");
    await user.click(screen.getByRole("button", { name: "+ Another time" }));
    await user.click(screen.getByRole("button", { name: "Weekdays" }));
    await user.click(screen.getByRole("button", { name: "Add medicine" }));
    expect(onSave).toHaveBeenCalledWith({ dose_label: "aspirin", times: ["08:00", "20:00"], days: [0, 1, 2, 3, 4] });
  });

  it("refuses to save with no days picked", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn(async () => "");
    render(<MedicineDialog open person="Raj" editing={null} onClose={() => {}} onSave={onSave} />);
    await user.type(screen.getByPlaceholderText("lisinopril"), "aspirin");
    for (const name of ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]) await user.click(screen.getByLabelText(name));
    await user.click(screen.getByRole("button", { name: "Add medicine" }));
    expect(await screen.findByText("Pick at least one day.")).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });
});


describe("Reminders", () => {
  it("announces a dose that is about to start, once", async () => {
    reminders = [{ schedule_id: 1, person_name: "Mom", dose_label: "lisinopril", time_spoken: "8 AM", minutes_until: 10, speech: "Mom's lisinopril is due at 8 AM, in 10 minutes." }];
    render(<Dashboard session={session} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Mom's lisinopril is due at 8 AM, in 10 minutes.");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss reminder" }));
    expect(screen.queryByRole("alert")).toBeNull();
    // A later check for the same dose, same day, is not announced again.
    await userEvent.click(screen.getByRole("button", { name: "+ Add person" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("Cognito sign-in", () => {
  it("offers a Sign in button that goes to the server's login address", async () => {
    const { default: Login } = await import("../pages/Login");
    const assign = vi.fn();
    Object.defineProperty(window, "location", { value: { assign, pathname: "/login" }, writable: true });
    render(<Login session={{ loading: false, provider: "cognito", loginUrl: "/api/auth/cognito-login" }} />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(assign).toHaveBeenCalledWith("/api/auth/cognito-login");
    expect(screen.queryByLabelText(/Password/)).toBeNull();
  });
});
