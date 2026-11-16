/**
 * Sanitiza errores reportados por proveedores de mensajería (WhatsApp Cloud, SMTP)
 * para asegurar que no se exponga PHI (teléfonos, emails, documentos) ni credenciales en pantalla (R9).
 */
export function sanitizarErrorProveedor(errorRaw?: string | null): string {
  if (!errorRaw) return "";
  let texto = errorRaw;
  // Sanitizar números telefónicos internacionales o locales (+54 9 11..., 11-4567-8901)
  texto = texto.replace(/(\+?\d{1,4}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}/g, "[TEL_PROTEGIDO]");
  // Sanitizar correos electrónicos
  texto = texto.replace(/[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+/g, "[EMAIL_PROTEGIDO]");
  // Sanitizar tokens o secrets si existieran
  texto = texto.replace(/(bearer\s+|token[=:]\s*|key[=:]\s*)[a-zA-Z0-9_\-.]+/gi, "$1[REDACTADO]");
  return texto;
}
