import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  TablaAccesible,
  CampoFormulario,
  DialogoConfirmacion,
} from "../src/shared/ComponentesUI";

describe("shared/ComponentesUI (1.5)", () => {
  it("TablaAccesible renderiza encabezados con scope=col y filas", () => {
    render(
      <TablaAccesible
        caption="Movimientos de caja"
        columnas={["Concepto", "Medio", "Monto"]}
      >
        <tr>
          <td>Consulta general</td>
          <td>Efectivo</td>
          <td>$ 10.000,00</td>
        </tr>
      </TablaAccesible>,
    );

    expect(screen.getByRole("table", { name: "Movimientos de caja" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Concepto" })).toHaveAttribute(
      "scope",
      "col",
    );
    expect(screen.getByText("Consulta general")).toBeInTheDocument();
  });

  it("CampoFormulario asocia label con input y anuncia error con role=alert", () => {
    render(
      <CampoFormulario
        id="campo-concepto"
        label="Concepto del movimiento"
        obligatorio
        error="El concepto es obligatorio."
      >
        <input id="campo-concepto" type="text" aria-invalid="true" />
      </CampoFormulario>,
    );

    expect(screen.getByLabelText(/Concepto del movimiento/i)).toBeInTheDocument();
    const alerta = screen.getByRole("alert");
    expect(alerta).toHaveTextContent("El concepto es obligatorio.");
  });

  it("DialogoConfirmacion exige confirmar antes de ejecutar y permite cancelar", async () => {
    const user = userEvent.setup();
    const onConfirmar = vi.fn();
    const onCancelar = vi.fn();

    render(
      <DialogoConfirmacion
        abierto={true}
        titulo="Confirmar cierre con diferencia"
        descripcion="Existe un faltante de $ 500,00 en la caja."
        textoConfirmar="Confirmar cierre"
        onConfirmar={onConfirmar}
        onCancelar={onCancelar}
      />,
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onConfirmar).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /cancelar/i }));
    expect(onCancelar).toHaveBeenCalledTimes(1);
    expect(onConfirmar).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /confirmar cierre/i }));
    expect(onConfirmar).toHaveBeenCalledTimes(1);
  });
});
