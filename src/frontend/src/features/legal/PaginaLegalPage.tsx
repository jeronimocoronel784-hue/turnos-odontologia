import { Link } from "react-router-dom";

export function PaginaLegalPage(): JSX.Element {
  const contacto = (import.meta.env.VITE_CONTACTO_PRIVACIDAD as string | undefined) || "";

  return (
    <main data-testid="pagina-legal" className="mx-auto max-w-3xl p-6 space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Política de Privacidad</h1>

      <section>
        <h2 className="text-lg font-semibold text-slate-800">Responsable del tratamiento</h2>
        <p className="text-sm text-slate-600">
          El consultorio odontológico responsable del tratamiento de los datos personales es quien
          presta el servicio de atención. Los datos se tratan conforme a la Ley 25.326 de
          Protección de los Datos Personales y a la Ley 26.529 de Historia Clínica Electrónica
          (HCE).
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold text-slate-800">Finalidad</h2>
        <p className="text-sm text-slate-600">
          Los datos personales y de salud se recopilan con la finalidad de gestionar turnos,
          historias clínicas, presupuestos, consentimientos y la facturación del consultorio.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold text-slate-800">Base legal</h2>
        <p className="text-sm text-slate-600">
          El tratamiento se basa en la legislación vigente de protección de datos personales y de
          historia clínica electrónica, así como en el consentimiento del paciente y las
          obligaciones legales del profesional de la salud.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold text-slate-800">Derechos</h2>
        <p className="text-sm text-slate-600">
          El titular tiene derecho de acceso, rectificación y supresión de sus datos. Para
          ejercerlos, puede solicitar al consultorio la exportación de sus datos personales y
          clínicos (paquete de datos del paciente) conforme a RN-SE-02.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold text-slate-800">Retención</h2>
        <p className="text-sm text-slate-600">
          Los datos se conservan por un mínimo de 5 años, sujeto a dictamen (PO-03), conforme
          a las obligaciones legales de historia clínica.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold text-slate-800">Contacto</h2>
        <p className="text-sm text-slate-600">
          {contacto
            ? `Podés comunicarte a ${contacto} para consultas sobre privacidad.`
            : "Para consultas sobre privacidad, comunicate con el consultorio donde te atendiste."}
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold text-slate-800">Tracking y datos de pacientes</h2>
        <p className="text-sm text-slate-600">
          Esta página no muestra datos de pacientes ni información sensible, no utiliza tracking
          y no escribe datos en el navegador.
        </p>
      </section>

      <footer className="border-t border-slate-200 pt-4 text-xs text-slate-500">
        <Link to="/" className="text-emerald-700 hover:underline">
          Volver al inicio
        </Link>
      </footer>
    </main>
  );
}
