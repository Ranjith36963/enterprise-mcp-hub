import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("renders title", () => {
    render(<EmptyState title="No jobs found" />);
    expect(screen.getByText("No jobs found")).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    render(<EmptyState title="No results" description="Try adjusting your filters." />);
    expect(screen.getByText("Try adjusting your filters.")).toBeInTheDocument();
  });

  it("renders icon when provided", () => {
    render(<EmptyState title="Empty" icon="🔍" />);
    expect(screen.getByText("🔍")).toBeInTheDocument();
  });

  it("renders action slot when provided", () => {
    render(
      <EmptyState
        title="Empty"
        action={<button>Reset filters</button>}
      />
    );
    expect(screen.getByRole("button", { name: "Reset filters" })).toBeInTheDocument();
  });

  it("has role=status with accessible label", () => {
    render(<EmptyState title="No jobs" />);
    const el = screen.getByRole("status");
    expect(el).toHaveAttribute("aria-label", "No jobs");
  });

  it("does not render description element when omitted", () => {
    render(<EmptyState title="Empty" />);
    // Should not render a <p> with description
    expect(screen.queryByText(/try/i)).not.toBeInTheDocument();
  });
});
