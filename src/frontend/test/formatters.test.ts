import { describe, it, expect } from "vitest";
import {
  formatearMoneda,
  formatearFechaLarga,
  formatearFechaCorta,
  formatearHora,
  formatearRangoHorario,
  formatearFechaHora,
  formatearDni,
  formatearDuracion,
} from "../src/shared/formatters";

describe("formatters de presentación", () => {
  describe("formatearMoneda", () => {
    it("formatea monto numérico válido en ARS", () => {
      const res = formatearMoneda(15000);
      expect(res).toContain("15.000,00");
    });

    it("maneja nulo, vacío y cero", () => {
      expect(formatearMoneda(null)).toBe("$ 0");
      expect(formatearMoneda("")).toBe("$ 0");
      expect(formatearMoneda(0)).toContain("0,00");
    });
  });

  describe("formatearFechaLarga y FechaCorta", () => {
    it("formatea fecha larga con día y mes en es-AR", () => {
      const res = formatearFechaLarga("2026-11-20T10:00:00Z");
      expect(res.toLowerCase()).toContain("noviembre");
      expect(res).toContain("2026");
    });

    it("formatea fecha corta en formato DD/MM/AAAA", () => {
      const res = formatearFechaCorta("2026-11-20T15:00:00Z");
      expect(res).toMatch(/\d{2}\/\d{2}\/2026/);
    });

    it("maneja string inválido sin romper", () => {
      expect(formatearFechaCorta("invalido")).toBe("invalido");
    });
  });

  describe("formatearHora y formatearRangoHorario", () => {
    it("formatea hora con sufijo hs", () => {
      const res = formatearHora("2026-11-20T14:30:00");
      expect(res).toContain("hs");
      expect(res).toMatch(/\d{2}:\d{2} hs/);
    });

    it("formatea rango horario de inicio a fin", () => {
      const res = formatearRangoHorario("2026-11-20T10:00:00", "2026-11-20T11:00:00");
      expect(res).toContain(" a ");
      expect(res).toContain("hs");
    });
  });

  describe("formatearFechaHora", () => {
    it("combina fecha larga y hora", () => {
      const res = formatearFechaHora("2026-11-20T10:00:00");
      expect(res).toContain("·");
      expect(res).toContain("hs");
    });

    it("tolera string inválido", () => {
      const res = formatearFechaHora("cadena-rota");
      expect(res).toContain("cadena-rota");
    });
  });

  describe("formatearDni", () => {
    it("formatea DNI de 8 dígitos con puntos", () => {
      expect(formatearDni("35123456")).toBe("35.123.456");
    });

    it("formatea DNI de 7 dígitos con un punto", () => {
      expect(formatearDni("8123456")).toBe("8.123.456");
    });

    it("devuelve sin puntos si es muy corto", () => {
      expect(formatearDni("1234")).toBe("1234");
    });
  });

  describe("formatearDuracion", () => {
    it("formatea minutos en horas y minutos", () => {
      expect(formatearDuracion(90)).toBe("1 h 30 min");
      expect(formatearDuracion(60)).toBe("1 h");
      expect(formatearDuracion(45)).toBe("45 min");
    });

    it("maneja duraciones cero o negativas", () => {
      expect(formatearDuracion(0)).toBe("0 min");
      expect(formatearDuracion(-10)).toBe("0 min");
    });
  });
});
