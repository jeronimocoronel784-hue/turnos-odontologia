import { describe, it, expect } from "vitest";
import {
  formatearMontoARS,
  normalizarDecimalDosPosiciones,
  compararMontosDecimales,
  clasificarDiferenciaCaja,
} from "../src/shared/formattersMonto";

describe("shared/formattersMonto (1.3)", () => {
  it("normalizarDecimalDosPosiciones normaliza 0.00, negativos y 3 decimales del servidor", () => {
    expect(normalizarDecimalDosPosiciones("0")).toBe("0.00");
    expect(normalizarDecimalDosPosiciones("0.000")).toBe("0.00");
    expect(normalizarDecimalDosPosiciones("-1500.5")).toBe("-1500.50");
    expect(normalizarDecimalDosPosiciones("12345.678")).toBe("12345.68");
  });

  it("formatearMontoARS formatea en moneda es-AR desde string decimal y casos borde", () => {
    const cero = formatearMontoARS("0.00");
    expect(cero).toMatch(/\$\s?0,00/);

    const miles = formatearMontoARS("25000.50");
    expect(miles).toContain("25.000,50");

    const negativo = formatearMontoARS("-1200.00");
    expect(negativo).toContain("1.200,00");
    expect(negativo).toContain("-");
  });

  it("compararMontosDecimales compara con precisión a 2 decimales", () => {
    expect(compararMontosDecimales("0.00", "0.000")).toBe(0);
    expect(compararMontosDecimales("1500.00", "999.99")).toBe(1);
    expect(compararMontosDecimales("-10.00", "0.00")).toBe(-1);
  });

  it("clasificarDiferenciaCaja clasifica cuadrada, sobrante y faltante", () => {
    expect(clasificarDiferenciaCaja("0.00")).toBe("cuadrada");
    expect(clasificarDiferenciaCaja("0.000")).toBe("cuadrada");
    expect(clasificarDiferenciaCaja("500.00")).toBe("sobrante");
    expect(clasificarDiferenciaCaja("-250.00")).toBe("faltante");
  });
});
