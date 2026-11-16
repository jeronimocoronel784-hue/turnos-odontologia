import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

function SmokeComponent() {
  return <div>Consultorio Odontológico</div>;
}

describe("Smoke test", () => {
  it("renderiza un componente trivial", () => {
    render(<SmokeComponent />);
    expect(screen.getByText("Consultorio Odontológico")).toBeInTheDocument();
  });
});
