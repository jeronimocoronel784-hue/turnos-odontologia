import { SuperficieDental, TipoEventoPieza } from "../../shared/api-types";

export const CUADRANTES_PERMANENTES = {
  superiorDerecho: [18, 17, 16, 15, 14, 13, 12, 11],
  superiorIzquierdo: [21, 22, 23, 24, 25, 26, 27, 28],
  inferiorDerecho: [48, 47, 46, 45, 44, 43, 42, 41],
  inferiorIzquierdo: [31, 32, 33, 34, 35, 36, 37, 38],
} as const;

export const CUADRANTES_DECIDUOS = {
  superiorDerecho: [55, 54, 53, 52, 51],
  superiorIzquierdo: [61, 62, 63, 64, 65],
  inferiorDerecho: [85, 84, 83, 82, 81],
  inferiorIzquierdo: [71, 72, 73, 74, 75],
} as const;

export const SUPERFICIES: readonly SuperficieDental[] = [
  "oclusal",
  "mesial",
  "distal",
  "vestibular",
  "palatina",
  "lingual",
  "cervical",
  "pieza_completa",
];

export const EVENTOS_PIEZA: readonly TipoEventoPieza[] = [
  "sano",
  "caries",
  "obturacion",
  "corona",
  "endodoncia",
  "extraccion_indicada",
  "ausente",
  "implante",
  "protesis",
  "sellador",
];

export const COLOR_EVENTO: Record<TipoEventoPieza, string> = {
  sano: "#10b981", // verde
  caries: "#ef4444", // rojo
  obturacion: "#3b82f6", // azul
  corona: "#f59e0b", // ambar
  endodoncia: "#8b5cf6", // violeta
  extraccion_indicada: "#b91c1c", // bordo
  ausente: "#64748b", // slate
  implante: "#06b6d4", // cian
  protesis: "#ec4899", // rosa
  sellador: "#14b8a6", // teal
};
