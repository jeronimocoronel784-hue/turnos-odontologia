// Utilidades de formateo para Argentina (R8: formateo visual, sin cálculo de montos).

export function formatearMoneda(valor: string | number | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") {
    return "$ 0";
  }
  const numero = typeof valor === "number" ? valor : parseFloat(valor);
  if (isNaN(numero)) {
    return `$ ${valor}`;
  }
  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "ARS",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numero);
}

export function formatearFechaLarga(isoString: string): string {
  try {
    const fecha = new Date(isoString);
    return new Intl.DateTimeFormat("es-AR", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(fecha);
  } catch {
    return isoString;
  }
}

export function formatearFechaCorta(isoString: string): string {
  try {
    const fecha = new Date(isoString);
    return new Intl.DateTimeFormat("es-AR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(fecha);
  } catch {
    return isoString;
  }
}

export function formatearHora(isoString: string): string {
  try {
    const fecha = new Date(isoString);
    const horas = fecha.getHours().toString().padStart(2, "0");
    const minutos = fecha.getMinutes().toString().padStart(2, "0");
    return `${horas}:${minutos} hs`;
  } catch {
    return isoString;
  }
}

/** Rango legible de un turno: "10:00 hs a 11:00 hs". */
export function formatearRangoHorario(inicioIso: string, finIso: string): string {
  return `${formatearHora(inicioIso)} a ${formatearHora(finIso)}`;
}

/** Fecha y hora en una sola línea: "lunes, 5 de diciembre de 2026 · 10:00 hs". */
export function formatearFechaHora(isoString: string): string {
  return `${formatearFechaLarga(isoString)} · ${formatearHora(isoString)}`;
}

export function formatearDni(valor: string): string {
  const soloNumeros = valor.replace(/\D/g, "").slice(0, 8);
  if (soloNumeros.length <= 4) return soloNumeros;
  if (soloNumeros.length <= 7) {
    return `${soloNumeros.slice(0, soloNumeros.length - 3)}.${soloNumeros.slice(-3)}`;
  }
  return `${soloNumeros.slice(0, 2)}.${soloNumeros.slice(2, 5)}.${soloNumeros.slice(5)}`;
}
