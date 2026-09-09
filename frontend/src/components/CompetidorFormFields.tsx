"use client";

// Campos del formulario de competidor, compartidos entre la página global de
// competidores y la inscripción rápida dentro de un campeonato.
//
// Restricciones (espejo del backend): nombre y club con tope de caracteres,
// documento solo números, fecha de nacimiento entre 3 y 100 años, peso entre
// 10 y 200 kg. El cinturón se elige del catálogo y el grupo competitivo se
// detecta automáticamente (no se escribe a mano).

import {
  CINTURONES,
  COMPETIDOR_LIMITES,
  grupoDeCinturon,
  type CompetidorData,
  type CompetidorInput,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { enMayusculas } from "@/lib/texto";
import CampoFecha from "@/components/CampoFecha";
import ClubCombobox from "@/components/ClubCombobox";

export interface CompetidorFormState {
  nombre_completo: string;
  documento: string;
  fecha_nacimiento: string; // yyyy-mm-dd (input type=date)
  genero: string;
  cinturon: string;
  peso: string;
  club: string;
  categoria_especial: boolean;
}

export const COMPETIDOR_FORM_VACIO: CompetidorFormState = {
  nombre_completo: "",
  documento: "",
  fecha_nacimiento: "",
  genero: "",
  cinturon: "",
  peso: "",
  club: "",
  categoria_especial: false,
};

export function competidorToForm(c: CompetidorData): CompetidorFormState {
  return {
    // Los datos viejos pueden venir en minúsculas: al abrirlos para editar ya
    // se ven como se van a guardar (ver `enMayusculas`).
    nombre_completo: enMayusculas(c.nombre_completo || ""),
    documento: c.documento || "",
    fecha_nacimiento: c.fecha_nacimiento || "",
    genero: c.genero || "",
    cinturon: c.cinturon || "",
    peso: c.peso != null ? String(c.peso) : "",
    club: enMayusculas(c.club || ""),
    categoria_especial: Boolean(c.categoria_especial),
  };
}

export function formToPayload(f: CompetidorFormState): CompetidorInput {
  return {
    nombre_completo: f.nombre_completo.trim(),
    documento: f.documento.trim() || null,
    fecha_nacimiento: f.fecha_nacimiento || null,
    genero: (f.genero || null) as CompetidorInput["genero"],
    cinturon: f.cinturon || null,
    peso: f.peso.trim() ? Number(f.peso.replace(",", ".")) : null,
    club: f.club.trim() || null,
    categoria_especial: f.categoria_especial,
  };
}

export function edadDesde(fechaNacimiento: string | null, ref?: Date): number | null {
  if (!fechaNacimiento) return null;
  const nacimiento = new Date(`${fechaNacimiento}T00:00:00`);
  if (isNaN(nacimiento.getTime())) return null;
  const hoy = ref || new Date();
  let edad = hoy.getFullYear() - nacimiento.getFullYear();
  const m = hoy.getMonth() - nacimiento.getMonth();
  if (m < 0 || (m === 0 && hoy.getDate() < nacimiento.getDate())) edad -= 1;
  return edad;
}

/** Rango de fechas válido para el input date: edad entre 3 y 100 años. */
function limitesFechaNacimiento(): { min: string; max: string } {
  const hoy = new Date();
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const min = new Date(hoy);
  min.setFullYear(hoy.getFullYear() - COMPETIDOR_LIMITES.edadMax);
  const max = new Date(hoy);
  max.setFullYear(hoy.getFullYear() - COMPETIDOR_LIMITES.edadMin);
  return { min: iso(min), max: iso(max) };
}

export default function CompetidorFormFields({
  value,
  onChange,
  clubes,
  clubesPropios = null,
}: {
  value: CompetidorFormState;
  onChange: (next: CompetidorFormState) => void;
  /** Clubes de los maestros del workspace → el club se elige por combobox. */
  clubes?: string[];
  /**
   * Flujo maestro: el alumno solo puede ir a un club DEL MAESTRO. Con uno solo
   * el campo va fijo (como siempre); si dirige varios dojangs, elige a cuál
   * pertenece este alumno — antes se le imponía el primero y un alumno acababa
   * compitiendo a nombre del dojang equivocado.
   */
  clubesPropios?: string[] | null;
}) {
  const { t } = useI18n();
  const set = (campo: keyof CompetidorFormState, v: string | boolean) =>
    onChange({ ...value, [campo]: v });

  const fechas = limitesFechaNacimiento();
  const grupoDetectado = grupoDeCinturon(value.cinturon);

  return (
    <div className="comp-form-grid">
      <label className="comp-field" style={{ gridColumn: "1 / -1" }}>
        <span className="comp-label">
          {t("form.nombre")} <span className="comp-hint">{t("form.nombreMin", { n: COMPETIDOR_LIMITES.nombreMin })} · {t("form.max", { n: COMPETIDOR_LIMITES.nombreMax })}</span>
        </span>
        <input
          className="input"
          value={value.nombre_completo}
          // En MAYÚSCULAS mientras se escribe: es como se guarda (ver `enMayusculas`).
          onChange={(e) => set("nombre_completo", enMayusculas(e.target.value.slice(0, COMPETIDOR_LIMITES.nombreMax)))}
          placeholder={t("form.nombrePh")}
          maxLength={COMPETIDOR_LIMITES.nombreMax}
          minLength={COMPETIDOR_LIMITES.nombreMin}
          required
        />
      </label>
      <label className="comp-field">
        <span className="comp-label">
          {t("form.documento")} <span className="comp-hint">{t("form.soloNumeros")}</span>
        </span>
        <input
          className="input"
          inputMode="numeric"
          value={value.documento}
          onChange={(e) =>
            set("documento", e.target.value.replace(/\D/g, "").slice(0, COMPETIDOR_LIMITES.documentoMax))
          }
          placeholder={t("form.documentoPh")}
          maxLength={COMPETIDOR_LIMITES.documentoMax}
        />
      </label>
      {/* Este es el campo por el que existe <CampoFecha>: la fecha de
          nacimiento siempre está años atrás, y el calendario de Android solo
          avanza mes a mes. Aquí el año se elige de una rejilla. */}
      <div className="comp-field">
        <span className="comp-label">
          {t("form.fechaNacimiento")} <span className="comp-hint">{t("form.rangoEdad", { min: COMPETIDOR_LIMITES.edadMin, max: COMPETIDOR_LIMITES.edadMax })}</span>
        </span>
        <CampoFecha
          valor={value.fecha_nacimiento}
          min={fechas.min}
          max={fechas.max}
          ariaLabel={t("form.fechaNacimiento")}
          onChange={(v) => set("fecha_nacimiento", v)}
        />
      </div>
      <label className="comp-field">
        <span className="comp-label">{t("form.genero")}</span>
        <select
          className="input"
          value={value.genero}
          onChange={(e) => set("genero", e.target.value)}
        >
          <option value="">{t("form.sinDefinir")}</option>
          <option value="MASCULINO">{t("form.masculino")}</option>
          <option value="FEMENINO">{t("form.femenino")}</option>
        </select>
      </label>
      <label className="comp-field">
        <span className="comp-label">
          {t("form.cinturon")}{" "}
          {grupoDetectado ? (
            <span className="comp-hint" style={{ color: "var(--gold)" }}>
              {t("form.grupoFlecha", { grupo: grupoDetectado.charAt(0) + grupoDetectado.slice(1).toLowerCase() })}
            </span>
          ) : (
            <span className="comp-hint">{t("form.grupoAuto")}</span>
          )}
        </span>
        <select
          className="input"
          value={value.cinturon}
          onChange={(e) => set("cinturon", e.target.value)}
        >
          <option value="">{t("form.sinDefinir")}</option>
          {CINTURONES.map((c) => (
            <option key={c.nombre} value={c.nombre}>{c.nombre}</option>
          ))}
        </select>
      </label>
      <label className="comp-field">
        <span className="comp-label">
          {t("form.peso")} <span className="comp-hint">{t("form.rango", { min: COMPETIDOR_LIMITES.pesoMin, max: COMPETIDOR_LIMITES.pesoMax })}</span>
        </span>
        <input
          className="input"
          inputMode="decimal"
          min={COMPETIDOR_LIMITES.pesoMin}
          max={COMPETIDOR_LIMITES.pesoMax}
          value={value.peso}
          onChange={(e) => {
            const v = e.target.value.slice(0, COMPETIDOR_LIMITES.pesoCharsMax);
            set("peso", v);
          }}
          placeholder={t("form.pesoPh")}
          maxLength={COMPETIDOR_LIMITES.pesoCharsMax}
        />
      </label>
      <label className="comp-field">
        <span className="comp-label">
          {clubesPropios && clubesPropios.length > 1 ? (
            <>
              {t("form.clubElegir")}{" "}
              <span className="comp-hint">{t("form.clubElegirAyuda")}</span>
            </>
          ) : (
            <>
              {t("form.club")}{" "}
              {clubesPropios !== null ? (
                <span className="comp-hint">{t("form.clubFijo")}</span>
              ) : (
                <span className="comp-hint">{t("form.max", { n: COMPETIDOR_LIMITES.clubMax })}</span>
              )}
            </>
          )}
        </span>
        {clubesPropios !== null ? (
          // Flujo maestro: solo sus dojangs. Con uno, fijo; con varios, elige.
          clubesPropios.length > 1 ? (
            <select
              className="input"
              value={value.club}
              onChange={(e) => set("club", e.target.value)}
            >
              {clubesPropios.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          ) : (
            <input className="input" value={clubesPropios[0] || ""} disabled readOnly />
          )
        ) : clubes ? (
          <ClubCombobox
            value={value.club}
            onChange={(v) => set("club", enMayusculas(v.slice(0, COMPETIDOR_LIMITES.clubMax)))}
            clubes={clubes}
            maxLen={COMPETIDOR_LIMITES.clubMax}
          />
        ) : (
          <input
            className="input"
            value={value.club}
            onChange={(e) => set("club", enMayusculas(e.target.value.slice(0, COMPETIDOR_LIMITES.clubMax)))}
            placeholder={t("form.clubPh")}
            maxLength={COMPETIDOR_LIMITES.clubMax}
          />
        )}
      </label>

      <label
        className="comp-especial"
        style={{ gridColumn: "1 / -1" }}
        title={t("form.especialTitle")}
      >
        <input
          type="checkbox"
          checked={value.categoria_especial}
          onChange={(e) => set("categoria_especial", e.target.checked)}
        />
        <span>
          <strong>{t("form.especial")}</strong>
          <span style={{ color: "var(--text-muted)" }}>
            {t("form.especialDesc")}
          </span>
        </span>
      </label>

      <style>{`
        .comp-form-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 10px;
        }
        .comp-field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
        /* ── Etiqueta de campo: minusculas ─────────────────────────────
           «font-weight: 800» + MAYUSCULAS en la sans del cuerpo hace que el
           NOMBRE del campo pese mas que lo que hay dentro. En un formulario de
           doce campos eso es doce palabras gritando y ningun dato destacando.
           En Membresias la misma etiqueta es «.muted» a 0.8 rem, en minusculas.
           Ver «.microetiqueta» en «estilos-ecosistema.css» para la regla
           entera: MAYUSCULAS solo en titular, antetitulo y nombre de dato. */
        .comp-label {
          font-size: 0.8rem; font-weight: 600;
          color: var(--text-muted);
        }
        /* La aclaracion entre parentesis de una etiqueta. Ya no tiene que
           deshacer las mayusculas ni el interletrado de su madre: no los hay. */
        .comp-hint { font-weight: 400; color: var(--text-dim); }
        .comp-especial {
          display: flex; align-items: flex-start; gap: 8px;
          font-size: 0.9rem; cursor: pointer;
          padding: 8px 10px; background: var(--bg-elevated);
          border: 1px solid var(--border); border-radius: var(--radius-sm);
        }
        .comp-especial input { margin-top: 3px; }
      `}</style>
    </div>
  );
}
