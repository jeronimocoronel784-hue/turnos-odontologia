/**
 * Formateo y comparación decimal de importes monetarios del servidor (D3, R8).
 *
 * El cliente NUNCA suma ni resta montos de negocio: solo formatea los strings
 * decimales provenientes del backend y compara el signo/magnitud a 2 decimales
 * para etiquetas de presentación ("cuadrada", "sobrante", "faltante").
 */

const formateadorARS = new Intl.NumberFormat("es-AR", {
  style: "currency",
  currency: "ARS",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function parsearCentavos(valor: string | number | null | undefined): bigint {
  if (valor === null || valor === undefined || valor === "") {
    return 0n;
  }
  const str = typeof valor === "number" ? valor.toFixed(4) : String(valor).trim();
  if (!str) return 0n;

  const num = Number(str);
  if (Number.isNaN(num)) return 0n;

  const centavosRedondeados = Math.round(num * 100);
  return BigInt(centavosRedondeados);
}

/**
 * Normaliza un importe decimal en string a exactamente 2 posiciones decimales
 * (ej: `"0"` -> `"0.00"`, `"-1500.5"` -> `"-1500.50"`, `"12345.678"` -> `"12345.68"`).
 */
export function normalizarDecimalDosPosiciones(
  valor: string | number | null | undefined,
): string {
  const centavos = parsearCentavos(valor);
  if (centavos === 0n) return "0.00";

  const negativo = centavos < 0n;
  const abs = negativo ? -centavos : centavos;
  const enteros = abs / 100n;
  const resto = abs % 100n;
  const decStr = resto.toString().padStart(2, "0");
  return `${negativo ? "-" : ""}${enteros.toString()}.${decStr}`;
}

/**
 * Formatea un string decimal del servidor en formato moneda es-AR (`$ 25.000,50`).
 */
export function formatearMontoARS(valor: string | number | null | undefined): string {
  const centavos = parsearCentavos(valor);
  const numero = Number(centavos) / 100;
  return formateadorARS.format(numero);
}

/**
 * Compara dos importes decimales a 2 posiciones: devuelve `-1` si `a < b`, `0` si `a == b`, `1` si `a > b`.
 */
export function compararMontosDecimales(
  a: string | number | null | undefined,
  b: string | number | null | undefined,
): -1 | 0 | 1 {
  const ca = parsearCentavos(a);
  const cb = parsearCentavos(b);
  if (ca < cb) return -1;
  if (ca > cb) return 1;
  return 0;
}

/**
 * Clasifica la diferencia de cierre de caja (`total_contado - total_sistema`) sin sumar dinero propio.
 */
export function clasificarDiferenciaCaja(
  diferencia: string | number | null | undefined,
): "cuadrada" | "sobrante" | "faltante" {
  const cmp = compararMontosDecimales(diferencia, "0.00");
  if (cmp === 0) return "cuadrada";
  return cmp > 0 ? "sobrante" : "faltante";
}
