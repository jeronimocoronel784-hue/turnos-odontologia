# Sistema de gestión de turnos y agenda para consultorios odontológicos — Informe de Discovery

## 1. Portada

- **Título:** Sistema de gestión de turnos y agenda para consultorios odontológicos — Informe de Discovery
- **Materia:** Metodología I — Tecnicatura Universitaria en Programación
- **Fecha:** octubre 2026
- **Integrantes:** (a completar por el alumno)
- **Fuente del relevamiento:** `discovery/discovery.md` (relevamiento de 18 sistemas, fecha de investigación 2026-10-01; fechas distintas se indican expresamente donde la fuente las declara)
- **Método (heredado de la fuente):** relevamiento exclusivo de fuentes verificables (sitios oficiales, páginas de precios, centros de ayuda, videos/canales oficiales, marketplaces con reseñas verificadas). Se distingue entre **funcionalidad comprobada** (visible en producto, ayuda, video oficial o precio) y **afirmación comercial** (marketing sin evidencia pública). Todo lo no demostrado públicamente se consigna como **"No evidenciado"**.

---

## 2. Resumen ejecutivo

**Qué se investigó.** Se consolidó el relevamiento de 18 sistemas de gestión odontológica con foco en Argentina (prioridad 1), Latinoamérica (prioridad 2) e internacionales relevantes como referencia (prioridad 3). Para cada sistema se verificaron agenda, reserva online, recordatorios/automatización, clínica (odontograma/HC), administración y cobros, y precio publicado, siempre contra fuente oficial con fecha de consulta (base 2026-10-01).

**Principales hallazgos.**

1. Ningún sistema combina clínica profunda + obra social/prepaga argentina + facturación AFIP/ARCA comprobada + Mercado Pago nativo + WhatsApp automático oficial + precio en ARS + evidencia completa. El puntaje máximo ponderado es 4,25/5 (Dentalink) y pierde justamente en integraciones locales argentinas.
2. Los productos argentinos (DentalSoft, FLAP, ClinIA, Odontoly) lideran en encaje local (turnos online, WhatsApp, señas/Mercado Pago, liquidación de obras sociales) pero presentan vacíos de evidencia en odontograma avanzado, auditoría/exportación y precios publicados.
3. Los regionales (Dentalink, Dentidesk) son los más completos en agenda avanzada y clínica por especialidad, pero atan su facturación a Chile/España (SII, VeriFactu) y no evidencian AFIP/ARCA ni Mercado Pago para la Argentina; el WhatsApp automático de Dentidesk figura como "próximamente" (no disponible al 2026-10-01).
4. Los estadounidenses/británicos (Curve, Dentrix Ascend, CareStack, Tab32, Dentally, SOE) superan en imágenes, reclamos e IA, pero con precios de USD 125 a 1.299/mes, sin obra social/AFIP/Mercado Pago/WhatsApp para la Argentina: son inspiración de UX, no competidores adoptables tal cual.
5. Tres vacíos estructurales del mercado argentino: (a) ningún SaaS argentino relevado evidencia facturación AFIP/ARCA nativa; (b) solo FLAP evidencia Mercado Pago con señas vinculadas a cita (Odontoly lo ofrece como add-on pago); (c) el WhatsApp automático real (Business API oficial, plantillas, opt-in, costo por mensaje publicado) está ausente o sin documentar.

**MVP recomendado.** Agenda multi-profesional/multi-sillón con anti-solapamiento + reserva online 24/7 sin registro obligatorio + confirmación automática por WhatsApp (API oficial) y email + HC/odontograma FDI funcional + caja diaria con señas vía Mercado Pago + cálculo de cobertura obra social vs. particular con liquidación exportable + roles, auditoría mínima y exportación CSV/JSON + consentimiento informado. Diferenciadores desde v1: seña atada al turno, liquidación de obras sociales sin planilla, precio en ARS publicado y exportación/auditoría/firma desde el día uno. Explícitamente fuera del MVP: periodontograma avanzado y especialidades profundas, facturación AFIP/ARCA nativa completa (v1: exportación conciliable), recepcionista IA por voz, stock/laboratorio y app nativa obligatoria.

---

## 3. Sección A. Tabla comparativa (ordenada por relevancia para Argentina)

Orden heredado de `discovery/discovery.md`: combinación de encaje local (obra social/prepaga, AFIP/ARCA, Mercado Pago, WhatsApp, soporte AR, precio en ARS) + completitud de agenda + profundidad clínica. No es orden alfabético.

| # | Producto / Proveedor | País | Segmento | Reserva online | Recordatorios | Fuente y fecha |
|---|---|---|---|---|---|---|
| 1 | DentalSoft / DentalSoft | Argentina | Consultorio, clínica pequeña/mediana | Sí: turnos online 24/7 en 4 pasos desde web propia, slots en tiempo real, reconocimiento por DNI. Comprobado en sitio oficial. | WhatsApp + email con confirmación/cancelación automática (la agenda se actualiza sola). Chatbot 24/7 de preguntas frecuentes. Comprobado. | https://dentalsoft.com.ar — consulta 2026-10-01 |
| 2 | Dentalink / Dentalink (Softech) | Chile (opera LatAm + España) | Independiente → cadena | Reserva online (botón de agendamiento web). Comprobado parcial. Chatbot/RRSS: No evidenciado. | Recordatorios por WhatsApp y/o email; Contact Center IA 24/7 por WhatsApp + llamadas (la IA es afirmación comercial con demo, sin documentación técnica pública). | https://www.softwaredentalink.com — consulta 2026-10-01. Planes: https://www.softwaredentalink.com/es/planes — consulta 2026-10-01 |
| 3 | Dentidesk / Dentidesk | Chile (LatAm) | Clínica, multisucursal, sindicatos, universidades | Botón de agendamiento online integrable a la web. Comprobado. Lista de espera: No evidenciado. | Recordatorios configurables + cumpleaños por correo; WhatsApp manual desde ficha/cita (comprobado); WhatsApp automático declarado como "próximamente" (no disponible al 2026-10-01). | https://www.dentidesk.com/ — consulta 2026-10-01 |
| 4 | Clinic Cloud / Doctoralia (grupo Docplanner) | España (opera 13 países, incl. AR/MX/CO/CL) | Clínica dental, centro multidisciplinario | Integración nativa con Doctoralia como marketplace (comprobado). Reserva web propia como flujo autónomo: No evidenciado. | Email marketing/campañas (comprobado). WhatsApp Business API: No evidenciado. | https://clinic-cloud.com — consulta 2026-10-01. Tarifas: https://clinic-cloud.com/tarifas — consulta 2026-10-01 |
| 5 | FLAP / FLAP | Argentina | Independiente → clínica, multisucursal | Página de reservas web + turnero 24/7 optimizado para móvil; demo con datos ficticios. Comprobado. | Avisos y turnero/señas. WhatsApp automático: No evidenciado. | https://flap.com.ar/odontologos — consulta 2026-10-01 |
| 6 | ClinIA / OdontoClinIA / ClinIA | Argentina | Consultorio, clínica PyME, hospital/municipio, cadena | Reserva + asistente IA por WhatsApp que agenda sin intervención (afirmación comercial con demo; sin documentación técnica pública). | Confirmación por WhatsApp y email (comprobado como funcional). Recuperación de ausentes/campañas: No evidenciado. | https://www.clinia.com.ar/odontologia — consulta 2026-10-01 |
| 7 | OdontoSoft Millennium / GB Systems | Argentina/USA | Independiente → gran clínica | No evidenciado (sin reserva online 24/7 documentada). | SMS y emails masivos (comprobado). WhatsApp: No evidenciado. | https://gbsystems.com/os/ · https://www.odontosoft.com/ — consulta 2026-10-01 |
| 8 | Doctoralia / Nubimed / Docplanner | Polonia/global (presencia AR: pro.doctoralia.com/ar) | Independiente, consultorio, centro | Sí: reserva online 24/7, perfil público, recordatorios. Comprobado (núcleo del marketplace). No es software odontológico: multi-sillón/odontograma No evidenciado. | Recordatorios por email/SMS (comprobado). WhatsApp nativo: No evidenciado. | https://www.doctoralia.com.ar — consulta 2026-10-01 |
| 9 | Odontoly / Odontoly | Argentina | Consultorio 1–3 sillones (local-first) | No evidenciado como reserva online pública 24/7 (foco en gestión interna + app móvil privada). | Confirmación automática por WhatsApp 24 h antes (comprobado como funcional). | https://odontoly.com/ — consulta 2026-10-01 |
| 10 | Citalo / Citalo | Argentina/LatAm | Independiente, consultorio | Reserva desde celular (comprobado como propuesta; flujo detallado: No evidenciado). | No evidenciado en detalle público. | https://www.citalo.app/ar/software-turnos-odontologos — consulta 2026-10-01 |
| 11 | XDentalCloud / XDentalCloud | España (opera América) | Profesional solo → centro médico | No evidenciado de forma independiente. | No evidenciado de forma independiente. | https://xdentalcloud.com (comparativa contra Clinic Cloud publicada por el propio proveedor) — consulta 2026-10-01. Tratar precios y funcionalidades como afirmación comercial hasta verificación independiente. |
| 12 | Tab32 / Tab32 | EE.UU. (opera global cloud) | Independiente → grupo (DSO) | Portal paciente + comunicación (comprobado vía comparativas 2026). | Recordatorios por texto/email (comprobado); WhatsApp Business API: No evidenciado. | https://tab32.com — estructura y pricing page verificada vía comparativa de tercero el 2026-09-18 (precio Alpine USD 125/mes año 1, luego USD 225). Verificar al 2026-10-01. |
| 13 | Curve Dental / Curve Dental | EE.UU./Canadá | Independiente → grupo mediano | Portal + Curve GRO engagement (comprobado). | Texto/email incluidos (comprobado); WhatsApp: No evidenciado. | https://www.curvedental.com/pricing — pricing page verificada vía comparativas el 2026-09-18: sin número publicado. Referencias secundarias USD 350–500/mes/sede (no oficial). |
| 14 | Dentrix / Dentrix Ascend / Henry Schein One | EE.UU. | Independiente → enterprise/DSO | Reserve with Google en Ascend (comprobado: 27.000 citas/373 sedes según comparativas). | Engagement como add-on (on-prem) o incluido (Ascend); Detect AI USD 499/mes add-on (comprobado vía comparativas 2026). WhatsApp: No evidenciado. | https://www.dentrix.com · https://www.dentrixascend.com — consulta 2026-10-01 (comparativas de tercero 2026-09-18 y 2026-06). Sin precio publicado. |
| 15 | CareStack / CareStack | EE.UU. | Clínica mediana → grupo/DSO | Portal paciente (comprobado en pricing). | Comunicación por texto/email; VoiceStack como add-on de precio no publicado. WhatsApp: No evidenciado. | https://www.carestack.com/pricing — consulta 2026-09-18 (Essentials desde USD 829/mes, Intelligence desde USD 1.299/mes). |
| 16 | Dentally / Dentally | Reino Unido | Independiente → cadena | Reserva online (afirmación comercial; sin verificación para AR). | Recordatorios SMS/email (afirmación comercial). WhatsApp: No evidenciado. | https://www.dentally.com — consulta 2026-10-01. Sin precio AR; pricing UK por cotización. No evidenciado. |
| 17 | Software of Excellence (SOE) / Exact / Henry Schein One | Reino Unido/NZ | Clínica mediana → cadena | No evidenciado como reserva 24/7 autónoma. | No evidenciado (campañas básicas). | https://www.softwareofexcellence.com — consulta 2026-10-01. Por cotización. No evidenciado. |
| 18 | Legado AR: DentiOffice / Gestión Odontológica / MiPaciente / ConsultoriosOnline / varios | Argentina | Independiente, consultorio chico | No evidenciado. | SMS/email básico en algunos; WhatsApp automático: No evidenciado. | https://www.dentioffice.com.ar (ejemplo; resto sin sitio oficial único verificable al 2026-10-01). Sin precios públicos consistentes. No evidenciado. |

> Aclaración de honestidad: toda celda que en `discovery/discovery.md` figura como "No evidenciado", "sin evidencia pública", "afirmación comercial sin detalle" o equivalente se transcribe aquí como **"No evidenciado"**. No se agregaron funcionalidades, precios, URLs ni fechas no presentes en la fuente. La demo de FLAP utiliza datos ficticios ("Clínica Sonrisa Serena", dato ficticio de demostración, sin personas reales — cf. R13).

---

## 4. Sección B. Matriz de puntuación

Pesos (heredados de la fuente): turnos y automatización 25% · clínica 20% · integraciones locales y WhatsApp 15% · administración/cobros/facturación 15% · experiencia paciente 10% · seguridad/exportación/trazabilidad 10% · precio/adopción 5%. Total ponderado = Σ(nota × peso), escala 0–5.

| Sistema | Turnos + Auto (25%) | Clínica (20%) | Integ. locales + WA (15%) | Admin/Cobros (15%) | Exp. paciente (10%) | Seg/Export (10%) | Precio/Adopción (5%) | Total |
|---|---|---|---|---|---|---|---|---|
| Dentalink | 5 | 5 | 3 | 4 | 4 | 4 | 3 | **4,25** |
| Dentidesk | 4 | 5 | 3 | 4 | 4 | 3 | 3 | **3,90** |
| DentalSoft (AR) | 5 | 3 | 4 | 4 | 5 | 2 | 4 | **3,95** |
| Clinic Cloud | 4 | 4 | 3 | 4 | 4 | 4 | 3 | **3,80** |
| FLAP (AR) | 4 | 3 | 4 | 4 | 4 | 2 | 4 | **3,60** |
| ClinIA (AR) | 4 | 4 | 3 | 3 | 3 | 4 | 3 | **3,55** |
| Tab32 (USA) | 4 | 4 | 2 | 4 | 4 | 3 | 2 | **3,50** |
| Dentrix Ascend (USA) | 4 | 5 | 1 | 4 | 3 | 4 | 1 | **3,50** |
| Curve Dental (USA) | 4 | 4 | 1 | 4 | 4 | 4 | 2 | **3,45** |
| Dentally (UK) | 4 | 4 | 2 | 3 | 4 | 4 | 2 | **3,45** |
| CareStack (USA) | 4 | 4 | 1 | 4 | 4 | 4 | 1 | **3,40** |
| XDentalCloud (ES) | 4 | 4 | 2 | 3 | 3 | 3 | 3 | **3,30** |
| SOE Exact (UK) | 3 | 5 | 1 | 4 | 3 | 4 | 1 | **3,25** |
| Odontoly (AR) | 3 | 4 | 3 | 3 | 3 | 3 | 3 | **3,20** |
| OdontoSoft Millennium | 3 | 4 | 1 | 4 | 2 | 2 | 4 | **2,90** |
| Doctoralia | 5 | 1 | 2 | 1 | 5 | 3 | 2 | **2,80** |
| Citalo (AR) | 4 | 1 | 2 | 2 | 4 | 2 | 4 | **2,60** |
| Legado AR (DentiOffice et al.) | 2 | 2 | 1 | 2 | 2 | 1 | 3 | **~1,80** |

**Lectura crítica (heredada de la fuente).** Nadie supera 4,30 porque nadie combina clínica profunda + OS/AFIP/Mercado Pago/WhatsApp AR + precio ARS + evidencia completa; el líder (Dentalink 4,25) pierde en integraciones locales AR. Los argentinos puros (DentalSoft, FLAP) ganan en turnos/integraciones locales/experiencia pero pierden en clínica y seguridad/exportación (sin auditoría ni exportación documentadas). Los estadounidenses/británicos puntúan alto en clínica/seguridad pero colapsan en integraciones locales (1–2) y precio (1–2): inadoptables tal cual en la Argentina. Doctoralia/Citalo puntúan alto en turnos pero casi cero en clínica/administración: no son competidores directos sino complementos (captación). OdontoSoft y el legado AR puntúan bien en precio aparente (licencia única/local) pero mal en turnos digitales y seguridad: deuda técnica disfrazada de precio.

### NOTA METODOLÓGICA (qué significa cada nota y cómo se trataron los "No evidenciados")

- **Escala 0–5.** 0 = ausente o sin evidencia pública; 1 = mención marginal o solo marketing sin detalle; 2 = funcional básico parcial o solo add-on pago; 3 = funcional estándar comprobado pero sin encaje argentino o con limitaciones relevantes; 4 = funcional sólido comprobado con buen encaje; 5 = comprobado + excelente + encaje argentino pleno. Criterio crítico aplicado: ningún puntaje premia promesas sin evidencia.
- **"No evidenciado" = 0 con marca explícita.** La falta de evidencia no se compensa ni se promedia al alza: la ausencia de precios publicados, de integración AFIP/ARCA o Mercado Pago, o de documentación de exportación/auditoría penaliza explícitamente el criterio correspondiente. La marca "No evidenciado" se conserva visible en la Sección A para que el lector distinga un 0 por ausencia de un 0 por mala calidad.
- **Funcionalidad comprobada vs. afirmación comercial.** Solo puntúan alto las funcionalidades visibles en producto, centro de ayuda, video oficial o página de precios. Las afirmaciones de marketing sin evidencia pública (p. ej., IA que agenda, conexión directa con RX, "300+ clínicas", "3.000+ dentistas") se consignan como tales y no elevan la nota.
- **Precios de terceros.** Cuando el proveedor no publica precio, se consigna "No evidenciado / sin precio publicado" aunque existan estimaciones de terceros (Operatory, Capterra, Vendr); esas estimaciones se citan como referencia, no como hecho, y no mejoran la nota de precio/adopción.

---

## 5. Sección C. Análisis competitivo

### C.1. Estándar de mercado (su ausencia descalifica)

1. Agenda diaria/semanal multi-profesional con duraciones configurables y bloqueos (feriados, vacaciones). Presente en 16/18.
2. Reprogramación y cancelación (al menos manual) con estados de turno. Presente en 15/18.
3. Historia clínica digital + odontograma básico (al menos registro por pieza). Presente en 13/18; periodontograma ya estándar en gama media (Dentalink, Dentidesk, Clinic Cloud Max).
4. Presupuestos/planes de tratamiento vinculados a citas. Presente en 12/18.
5. Recordatorios (al menos email/SMS; WhatsApp manual como mínimo). Presente en 14/18.
6. Roles y permisos básicos + multi-sucursal elemental. Presente en 12/18.
7. Reportes operativos/financieros básicos. Presente en 14/18.
8. Reserva online (al menos botón web). Presente en 12/18; su ausencia (OdontoSoft, legado) hoy se percibe como obsolescencia.
9. Prueba gratuita o demo guiada (15 días es el estándar). Presente en 12/18.
10. Soporte en español y capacitación inicial. Declarado en 15/18 (verificar calidad real en demo).

### C.2. Diferenciadores reales (pocos los tienen comprobados)

- **IA que agenda/confirma/reactiva por WhatsApp + voz 24/7** (Dentalink Contact Center IA; ClinIA asistente WA; Dentidesk dictado por voz, no agendamiento). Diferencial frágil: todos lo anuncian, ninguno publica documentación técnica, costos por mensaje ni tasa de éxito.
- **Sobreturno paralelo + reprogramación masiva + autoasignación por carga** (Dentalink, FLAP). Muy valorado en clínicas con ausentismo alto; casi nadie más lo documenta.
- **Fichas de especialidad profundas** (Dentidesk: ortodoncia, cirugía, endodoncia, disfunción; SOE/Dentrix: enterprise). Barrera de entrada clínica real.
- **Liquidación por obra social/prepaga argentina con cálculo de cobertura** (DentalSoft, parcial FLAP/ClinIA). Diferencial local exclusivo; ningún sistema LatAm ni USA lo tiene.
- **Seña vinculada a cita + Mercado Pago** (FLAP comprobado; Odontoly como add-on). Reduce ausentismo y financia la agenda; ausente en todo el resto LatAm/USA.
- **Facturación fiscal integrada al país** (SII Chile en Dentidesk, VeriFactu en Dentalink/Clinic Cloud, eClaims USA). En la Argentina nadie la tiene comprobada con AFIP/ARCA: es diferenciador vacante.
- **Operación offline local-first** (Odontoly, 30 días sin internet + backup 3-2-1). Único en el conjunto; relevante donde la conectividad falla.
- **Firma digital de consentimientos + trazabilidad/auditoría + exportación abierta** (Dentidesk firma, Clinic Cloud RGPD, Odontoly CSV/JSON). Ningún producto argentino lo combina todo; quien lo haga lidera en confianza.
- **Marketplace como canal de captación** (Doctoralia → Clinic Cloud). Ningún producto argentino lo replica: turnero propio + vidriera pública en un solo producto es espacio abierto.

### C.3. Vacíos del mercado argentino (oportunidades directas)

1. **Sin AFIP/ARCA comprobado** en ningún SaaS argentino relevado. Todo es "No evidenciado" o add-on futuro. Dolor crónico: doble carga administrativa.
2. **Sin Mercado Pago nativo y conciliado**, salvo FLAP (comprobado) y Odontoly (add-on). Faltan señas, cuotas, links de pago y conciliación automática.
3. **Sin matriz de OS/prepagas mantenida** (coberturas, aranceles, liquidaciones, débitos). Solo DentalSoft la declara funcional; sin evidencia de actualización ni padrón.
4. **WhatsApp automático real** (Business API oficial, plantillas, opt-in, costos claros) ausente o "próximamente". Todos dicen "WhatsApp", pocos distinguen manual vs. automático vs. IA, y ninguno publica precio por mensaje en la Argentina.
5. **Prevención de solapamientos por sillón/box + duración variable por prestación**, documentada solo en Dentalink/FLAP; el resto es agenda genérica médica adaptada.
6. **Lista de espera inteligente + recuperación de ausentes + controles periódicos** casi inexistentes como flujo automático; solo campañas de email genéricas.
7. **Exportación abierta + auditoría + Ley 25.326 / HCE declaradas con evidencia**: solo afirmaciones. Nadie publica política de respaldo, retención ni proceso de portabilidad.
8. **Precios en ARS publicados y actualizables**: solo Odontoly publica (en USD/blue). El resto es "consultar", lo que frena la adopción en independientes.
9. **Migración desde Excel/papel/legado incluida y documentada**: solo Odontoly y Dentidesk la prometen; sin guía pública reproducible.
10. **UX móvil para el paciente** (reservar/reprogramar/pagar/firmar desde el celular sin app obligatoria): solo DentalSoft/FLAP lo aproximan; el resto exige login pesado o desktop.

### C.4. Oportunidades de innovación para un nuevo sistema

1. **"Agenda que se cobra sola"**: turno online + seña Mercado Pago + confirmación WA automática + lista de espera que rellena huecos + política de cancelación con cargo. Nadie lo cierra end-to-end en la Argentina.
2. **"OS sin planilla"**: padrón configurable de OS/prepagas, cálculo cobertura vs. particular en el turno, liquidación exportable y control de débitos. Foso local defendible.
3. **"Cumplimiento verificable"**: consentimiento con firma digital, auditoría por usuario/fecha, exportación CSV/JSON en 1 clic, backup declarado, adecuación Ley 25.326 + Ley HCE con página legal pública (no solo eslogan). Convierte desconfianza en ventas.
4. **"Recepción IA honesta"**: chatbot/voz WA que agenda/confirma/reprograma con límites explícitos (horarios, prestaciones, derivación a humano), log auditable y costo por mensaje visible. Diferenciarse por transparencia, no por magia.
5. **"Modo consultorio chico"**: onboarding en 1 día (plantillas por especialidad, importación Excel), precio ARS publicado, funcionamiento aceptable con internet inestable (caché/cola offline), app liviana sin obligar al paciente a instalar nada.
6. **"Vidriera + gestión"**: perfil público (tratamientos, OS, opiniones) que alimenta la misma agenda, sin depender de Doctoralia. Modelo freemium de captación + SaaS de gestión.

---

## 6. Sección D. Recomendación final

### D.1. Cinco competidores prioritarios para demo (con qué mirar en cada uno)

1. **Dentalink** (https://www.softwaredentalink.com) — Pedir demo de: sobreturno paralelo, reprogramación masiva, odontograma/perio en vivo, Contact Center IA por WA (pedir costos, plantillas, opt-in, tasa de confirmación), multicentro e informes. Preguntar: precio final para 2 sillones + 3 profesionales en AR, AFIP/Mercado Pago/OS argentinas (¿roadmap con fecha?), exportación y borrado.
2. **Dentidesk** (https://www.dentidesk.com) — Demo de: fichas ortodoncia/endodoncia/cirugía, presupuestos por grupos de precios, convenios, stock, reportes financieros, firma digital, app móvil. Preguntar: WA automático (¿cuándo? ¿costo?), facturación AR (¿solo SII/Alegra o hay conector AFIP?), migración real desde Excel, precio USD vs. ARS.
3. **DentalSoft (AR)** (https://dentalsoft.com.ar) — Demo de: reserva en 4 pasos + reconocimiento DNI, confirmación/cancelación WA automática, chatbot, liquidación OS, caja. Preguntar: ¿dónde está el odontograma?, ¿Mercado Pago/AFIP?, ¿auditoría/exportación?, ¿precios y SLA de soporte?, ¿referencias visitables de las "300+ clínicas"? (afirmación sin padrón verificable).
4. **FLAP (AR)** (https://flap.com.ar/odontologos) — Demo de: autoasignación por carga, agenda por box, señas + Mercado Pago conciliado, página de reservas móvil, odontograma FDI. Preguntar: facturación AFIP, liquidación OS, WA automático, roles/auditoría/exportación, precio por profesional/sucursal.
5. **ClinIA OdontoClinIA (AR)** (https://www.clinia.com.ar/odontologia) — Demo de: agenda por sillón, confirmación WA, odontograma con historial, presupuestos, facturación/SUMAR+/PUCO, recetario ReNaPDiS N.º 248, interoperabilidad FHIR. Preguntar: alcance real fuera del sector público, precio, soporte, evidencia de Ley HCE (¿auditoría externa?), exportación.

> Suplente si alguna demo falla: **Clinic Cloud** (modelo por módulos y Doctoralia como canal) u **Odontoly** (offline-first y pricing transparente), según se quiera estudiar monetización o resiliencia.

### D.2. Tres productos de referencia para experiencia de usuario (no para copiar features, sino UX)

1. **DentalSoft (reserva en 4 pasos) + Doctoralia (búsqueda/reserva)** — El estándar de "reservar sin llamar": pocos pasos, slots reales, confirmación inmediata por WA, reconocimiento por DNI. Copiar el flujo, no el marketing.
2. **Tab32 / Curve GRO (portal paciente)** — Comunicación, recordatorios, formularios previos y pagos en un portal liviano sin app obligatoria. Referencia de tono, microcopy y estados (confirmado/en sala/cancelado).
3. **Dentidesk (ficha clínica) + Odontoly (odontograma anatómico)** — Densidad clínica sin laberinto: odontograma visual + historial por pieza + presupuestos al lado, todo imprimible/exportable. Referencia de cómo mostrar complejidad sin abrumar.

### D.3. MVP sugerido

**Imprescindibles (sin esto no se lanza):**

- Agenda diaria/semanal multi-profesional + multi-sillón/box, duraciones por prestación, bloqueos (feriados/vacaciones), estados, prevención de solapamientos, sobreturnos explícitos, reprogramación en 1 clic con historial.
- Reserva online 24/7 (link + embed web + RRSS) con slots reales, sin registro obligatorio (nombre + DNI + teléfono), confirmación/cancelación/reprogramación por el paciente, lista de espera básica que avisa huecos.
- Recordatorios + confirmación automática por WhatsApp (Business API oficial) y email, con plantillas, opt-in y log; política de cancelación configurable (anticipación mínima).
- Ficha clínica + anamnesis + odontograma funcional (FDI, por pieza/superficie, historial) + adjuntos (RX/fotos/PDF) + presupuestos/planes vinculados a citas.
- Caja diaria (cobros/gastos, medios, cierre), señas vinculadas a turno, Mercado Pago (link/QR conciliado), cálculo cobertura OS vs. particular y liquidación básica exportable.
- Roles y permisos (dueño/recepción/profesional), multi-sucursal elemental, auditoría mínima (quién/qué/cuándo), exportación CSV/JSON en 1 clic, backup declarado.
- Cumplimiento base declarado y verificable: consentimiento informado, Ley 25.326 + Ley HCE (página legal pública), control de acceso, trazabilidad.

**Diferenciadores del MVP (lo que gana contra los 18):**

- Seña + Mercado Pago atada al turno (reduce ausentismo y financia huecos) desde el día 1.
- Liquidación OS/prepagas AR sin planilla (padrón configurable + control de débitos).
- WA automático honesto con costos visibles + lista de espera que rellena cancelaciones sola.
- Precio ARS publicado + onboarding en 1 día (plantillas + importación Excel) + funcionamiento aceptable con internet inestable.
- Exportación + auditoría + firma de consentimientos desde v1 (confianza como feature).

**Para etapas posteriores (explícitamente NO en MVP):**

- Periodontograma avanzado, ortodoncia/endo/cirugía profundas, imágenes con IA diagnóstica, dictado por voz, transcripción.
- Facturación electrónica AFIP/ARCA nativa completa (v1: exportación conciliable; v2: conector fiscal).
- Recepcionista IA por voz 24/7, campañas/recuperación de pacientes con scoring, marketing automation.
- Stock/inventario, laboratorio, comisiones complejas, multi-cadena con consolidación, APIs públicas/marketplace, Google Calendar bidireccional, radiología directa, integraciones de marketing.
- App nativa obligatoria; portal paciente avanzado con pagos recurrentes y telemedicina.

> Regla de corte: si una funcionalidad no reduce ausentismo, no acelera el cobro o no evita doble carga (agenda ↔ HC ↔ caja ↔ OS), va a backlog.

---

## 7. Verificación de fuentes (a completar por el alumno con comprobación personal)

Instrucción: elegir 5 fuentes, visitarlas personalmente y completar cada ficha: qué afirmaba el informe, qué encontraron y qué corrigieron. No basta con copiar la URL: hay que describir la evidencia vista (captura, sección, fecha de visita).

### Fuente 1 — Sitio oficial del producto

- Tipo: sitio oficial.
- URL visitada:
- Fecha de visita:
- (a completar por el alumno: detallar la fuente comprobada personalmente, qué afirmaba el informe, qué encontraron y qué corrigieron)

### Fuente 2 — Página de precios

- Tipo: página de precios.
- URL visitada:
- Fecha de visita:
- (a completar por el alumno: detallar la fuente comprobada personalmente, qué afirmaba el informe, qué encontraron y qué corrigieron)

### Fuente 3 — Centro de ayuda / documentación

- Tipo: centro de ayuda.
- URL visitada:
- Fecha de visita:
- (a completar por el alumno: detallar la fuente comprobada personalmente, qué afirmaba el informe, qué encontraron y qué corrigieron)

### Fuente 4 — Video oficial / documentación técnica

- Tipo: video oficial o documentación técnica.
- URL visitada:
- Fecha de visita:
- (a completar por el alumno: detallar la fuente comprobada personalmente, qué afirmaba el informe, qué encontraron y qué corrigieron)

### Fuente 5 — Marketplace / reseñas verificadas

- Tipo: marketplace o reseñas verificadas.
- URL visitada:
- Fecha de visita:
- (a completar por el alumno: detallar la fuente comprobada personalmente, qué afirmaba el informe, qué encontraron y qué corrigieron)

---

## 8. Referencias completas (URLs con fecha; funcionalidad comprobada vs. afirmación comercial)

Fecha base de consulta: 2026-10-01 salvo indicación expresa. "Comprobada" = visible en producto, ayuda, video oficial o precio. "Afirmación comercial" = marketing sin evidencia pública; se indica expresamente.

- DentalSoft — https://dentalsoft.com.ar — 2026-10-01. Reserva 24/7, WhatsApp+email automáticos, liquidación OS: comprobadas en sitio. Odontograma, Mercado Pago, AFIP, precios: No evidenciado. "300+ clínicas": afirmación comercial sin padrón.
- Dentalink — home https://www.softwaredentalink.com/es/ ; agenda https://www.softwaredentalink.com/experiencia-de-pacientes/agenda ; planes https://www.softwaredentalink.com/es/planes — 2026-10-01. Agenda avanzada, odontograma/perio, multicentro: comprobados. Contact Center IA y conexión RX: afirmación comercial con demo. AFIP/ARCA, Mercado Pago, montos: No evidenciado.
- Dentidesk — https://www.dentidesk.com/ ; https://www.dentidesk.com/dentidesk/feature ; https://www.capterra.co/software/184029/dentidesk (precio desde USD 50, verificado) — 2026-10-01. Agendamiento online, especialidades, prueba 15 días: comprobados. WhatsApp automático: declarado "próximamente" (no disponible). SII Chile/Alegra: comprobados; AFIP/ARCA, Mercado Pago, precio ARS: No evidenciado.
- Clinic Cloud — producto dental https://clinic-cloud.com/software-clinica-dental-programa-odontologico ; tarifas https://clinic-cloud.com/tarifas (desde €29/mes + IVA) ; odontograma https://clinic-cloud.com/faq/historia-clinica-y-pacientes/odontograma ; HCE https://clinic-cloud.com/historias-clinicas-electronicas-digitales-software-gestion/ — 2026-10-01. Nube, RGPD, IA Noa, Doctoralia, precios EUR: comprobados. OS/AFIP/Mercado Pago/WhatsApp API AR: No evidenciado.
- FLAP Odontología — https://flap.com.ar/odontologos — 2026-10-01. Multi-profesional, turnero 24/7, HC/odontograma FDI, Mercado Pago + señas: comprobados. AFIP, liquidación OS, WhatsApp automático, precios: No evidenciado.
- ClinIA Odontología — https://www.clinia.com.ar/odontologia — 2026-10-01. Turnos por sillón, confirmación WA/email, odontograma, ReNaPDiS N.º 248 (solo recetario): comprobados parciales. Asistente IA que agenda, FHIR/RENAPER/PUCO, Ley HCE plena, precios, Mercado Pago/AFIP: afirmación comercial o No evidenciado.
- OdontoSoft Millennium — https://gbsystems.com/os/ ; https://gbsystems.com/os/index.htm ; https://gbsystems.com/os/producto.htm ; https://www.odontosoft.com/ (no confundir con https://www.odontsoft.com/, homónimo de Colombia) — 2026-10-01. Fichas/odontogramas definibles, SMS masivos, multi-clínica: comprobados. Reserva online, WhatsApp, nube real, precios: No evidenciado. "3000+ dentistas / desde 1995": afirmación sin padrón.
- Doctoralia AR — https://www.doctoralia.com.ar — 2026-10-01. Reserva 24/7, recordatorios email/SMS: comprobados (marketplace). Odontograma/HC, caja/OS/facturación AR, WhatsApp nativo, montos AR: No evidenciado.
- Odontoly — https://odontoly.com/ — 2026-10-01. GCalendar bidireccional, odontograma 32 marcas, caja, confirmación WA 24 h, precio USD 599,90 setup + desde USD 99,90/mes en ARS a blue con lock 12 m, AFIP/MP como add-ons: comprobados. Reserva pública 24/7, OS en detalle: No evidenciado. IA/recepcionista por voz: afirmación comercial (planes).
- Citalo AR — https://www.citalo.app/ar/software-turnos-odontologos — 2026-10-01. Propuesta de reserva desde celular: comprobada como propuesta; flujo detallado, clínica, cobros, precios: No evidenciado.
- XDentalCloud — https://xdentalcloud.com/comparativas/xdentalcloud-vs-clinic-cloud/ — 2026-10-01. Precio auto-declarado desde €42/mes (USD 49 América) y comparativa funcional: afirmación comercial del propio proveedor hasta verificación independiente.
- Comparativas USA 2026 (terceros) — https://operatory.app/best-cloud-based-dental-practice-management-software-2026/ ; https://operatory.app/carestack-vs-curve-dental-which-one-wins-in-2026/ ; https://avized.com/insights/carestack-vs-dentrix-ascend-vs-curve-dental-cloud-pms-showdown-for-growing-practices ; https://www.themolarreport.com/compare/dentrix-vs-curve-dental ; https://costbench.com/compare/curve-dental-vs-dentrix/ — consultas 2026-09-18 y 2026-06 según ficha. Se priorizó la apertura real de pricing pages por Operatory (2026-09-18) sobre el marketing de cada vendor.
- Sitios oficiales USA/UK — https://www.curvedental.com/pricing ; https://www.carestack.com/pricing (Essentials USD 829/mes, Intelligence USD 1.299/mes — 2026-09-18) ; https://tab32.com/pricing (Alpine USD 125/mes año 1, luego USD 225 — vía Operatory 2026-09-18, verificar al 2026-10-01) ; https://www.dentrixascend.com ; https://www.dentally.com ; https://www.softwareofexcellence.com — 2026-10-01 salvo indicación. Curve/Dentrix sin precio publicado (estimaciones secundarias citadas solo como referencia). Claims/eClaims USA: comprobados; AFIP/OS/Mercado Pago/WhatsApp AR: no aplica o No evidenciado.
- Legado AR — https://www.dentioffice.com.ar (ejemplo; resto sin sitio oficial único verificable al 2026-10-01). Agenda básica, odontograma básico, caja básica: afirmación comercial fragmentaria. Reserva online, WhatsApp automático, Mercado Pago/AFIP, precios consistentes: No evidenciado.

*Nota de datos ficticios (R13): la demo de FLAP exhibe datos ficticios ("Clínica Sonrisa Serena"). No se incluye ningún dato real de pacientes en este informe; no se hallaron ejemplos con personas reales en la fuente.*
