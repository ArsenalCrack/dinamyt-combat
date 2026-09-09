"use client";

// Delegación del maestro = país + ciudad, con DOS comboboxes escribibles:
//
//  • País: se escribe para FILTRAR, pero el valor final DEBE ser un país del
//    catálogo (no vale texto libre: lo que se escriba y no coincida se descarta
//    al cerrar). Reutiliza el patrón abrir/cerrar de ClubCombobox.
//  • Ciudad: sugiere las ciudades del país elegido (se escribe para filtrar) y
//    cierra la lista con «Otra ciudad…», que pasa a texto libre — igual que el
//    selector de ciudad de "Crear campeonato" (<PaisCiudadSelect>). Antes el
//    campo aceptaba texto libre "a la callada": quien no encontraba su ciudad
//    en la lista no tenía forma de saber que podía escribirla igualmente.
//    Se habilita solo tras elegir un país.
//
// Ojo con el marcado: el desplegable NO puede colgar dentro de un <label> que
// envuelva al input, porque al hacer clic en una opción el navegador reenvía
// ese clic al input (comportamiento propio de <label>), este se vuelve a
// enfocar y el país recién elegido se veía en blanco.

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { PAISES, ciudadesDe } from "@/lib/geo";
import { useI18n } from "@/lib/i18n";

/** Minúsculas y sin acentos, para filtrar sin sensibilidad. */
function normaliza(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim()
    .toLowerCase();
}

/** Hook: cierra el desplegable al hacer clic fuera o pulsar Escape. */
function useCerrarFuera(
  ref: React.RefObject<HTMLDivElement | null>,
  abierto: boolean,
  cerrar: () => void,
) {
  useEffect(() => {
    if (!abierto) return;
    function fuera(e: MouseEvent | TouchEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) cerrar();
    }
    function tecla(e: KeyboardEvent) {
      if (e.key === "Escape") cerrar();
    }
    document.addEventListener("mousedown", fuera);
    document.addEventListener("touchstart", fuera);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("touchstart", fuera);
      document.removeEventListener("keydown", tecla);
    };
  }, [abierto, ref, cerrar]);
}

const listaEstilo: React.CSSProperties = {
  position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
  zIndex: 40, margin: 0, padding: 4, listStyle: "none",
  maxHeight: 220, overflowY: "auto",
  background: "var(--bg-card)", border: "1px solid var(--gold-border)",
  borderRadius: "var(--radius-sm)", boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
};

function opcionEstilo(activa: boolean): React.CSSProperties {
  return {
    padding: "8px 10px", cursor: "pointer", borderRadius: 6,
    fontWeight: activa ? 800 : 500,
    color: activa ? "var(--gold)" : "var(--text)",
  };
}

/** Combobox ESTRICTO de país: filtra al escribir, pero solo un país del
 *  catálogo puede quedar como valor. */
function PaisCombobox({
  id, value, onChange,
}: {
  id: string;
  value: string;
  onChange: (pais: string) => void;
}) {
  const { t } = useI18n();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [abierto, setAbierto] = useState(false);
  // null = no se está filtrando → el input muestra el país elegido. Así el
  // campo nunca se ve vacío teniendo país, ni al abrir ni al reenfocar.
  const [filtro, setFiltro] = useState<string | null>(null);

  const cerrar = () => { setAbierto(false); setFiltro(null); };
  useCerrarFuera(rootRef, abierto, cerrar);

  const filtradas = useMemo(() => {
    const q = normaliza(filtro ?? "");
    return q ? PAISES.filter((p) => normaliza(p).includes(q)) : PAISES;
  }, [filtro]);

  function elegir(pais: string) {
    onChange(pais);
    cerrar();
  }

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <input
        id={id}
        className="input"
        value={filtro ?? value}
        placeholder={t("form.paisSelecc")}
        // Al enfocar se selecciona el texto: la primera tecla reemplaza el
        // país mostrado en vez de escribir pegado a él.
        onFocus={(e) => { setAbierto(true); e.currentTarget.select(); }}
        onClick={(e) => { setAbierto(true); if (filtro === null) e.currentTarget.select(); }}
        onChange={(e) => { setAbierto(true); setFiltro(e.target.value); }}
        autoComplete="off"
      />
      {abierto && (
        <ul role="listbox" style={listaEstilo}>
          {filtradas.map((p) => (
            <li
              key={p}
              role="option"
              aria-selected={p === value}
              // preventDefault: si algún día esto queda dentro de un <label>,
              // evita que el clic se reenvíe al input y lo reabra.
              onClick={(e) => { e.preventDefault(); elegir(p); }}
              style={opcionEstilo(p === value)}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-elevated)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              {p}
            </li>
          ))}
          {filtradas.length === 0 && (
            <li style={{ padding: "8px 10px", color: "var(--text-dim)", fontSize: "0.85rem" }}>
              {t("form.paisSinResultados")}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

/** Combobox de ciudad: sugiere las ciudades del país (filtra al escribir) y
 *  cierra la lista con «Otra ciudad…» para las que no están en el catálogo.
 *  Deshabilitado hasta elegir país.
 *
 *  Se monta con `key={pais}`: al cambiar de país el componente se rehace, así
 *  el modo texto libre no se queda pegado de la delegación anterior. */
function CiudadCombobox({
  id, value, ciudades, disabled, maxLen, onChange,
}: {
  id: string;
  value: string;
  ciudades: string[];
  disabled: boolean;
  maxLen: number;
  onChange: (ciudad: string) => void;
}) {
  const { t } = useI18n();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [abierto, setAbierto] = useState(false);
  // null = no se está filtrando → el input muestra la ciudad elegida (mismo
  // motivo que en PaisCombobox: si no, el campo se ve vacío al reenfocarlo).
  const [filtro, setFiltro] = useState<string | null>(null);
  // Texto libre tras elegir «Otra ciudad…». Arranca activo si la ciudad
  // guardada no está en el catálogo del país (dato viejo o escrito a mano):
  // así se puede ver y corregir, en vez de quedar atrapada en la lista.
  const [libre, setLibre] = useState(
    () => Boolean(value) && !ciudades.some((c) => normaliza(c) === normaliza(value)),
  );

  const cerrar = () => { setAbierto(false); setFiltro(null); };
  useCerrarFuera(rootRef, abierto, cerrar);

  const filtradas = useMemo(() => {
    const q = normaliza(filtro ?? "");
    return q ? ciudades.filter((c) => normaliza(c).includes(q)) : ciudades;
  }, [ciudades, filtro]);

  if (disabled) {
    return (
      <input id={id} className="input" value="" disabled readOnly
        placeholder={t("form.delegacionPaisPrimero")} />
    );
  }

  // ── Modo texto libre («Otra ciudad…») ──
  if (libre) {
    return (
      <div style={{ display: "flex", gap: 6 }}>
        <input
          id={id}
          className="input"
          value={value}
          placeholder={t("geo.ciudadLibre")}
          maxLength={maxLen}
          onChange={(e) => onChange(e.target.value.slice(0, maxLen))}
          style={{ flex: 1, minWidth: 0 }}
          autoFocus
        />
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => { onChange(""); setLibre(false); setAbierto(true); }}
          title={t("form.delegacionCiudadSelecc")}
        >
          ↩
        </button>
      </div>
    );
  }

  // ── Modo lista/filtro ──
  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <input
        id={id}
        className="input"
        value={filtro ?? value}
        placeholder={t("form.delegacionCiudadSelecc")}
        maxLength={maxLen}
        onFocus={(e) => { setAbierto(true); e.currentTarget.select(); }}
        onClick={(e) => { setAbierto(true); if (filtro === null) e.currentTarget.select(); }}
        onChange={(e) => { setAbierto(true); setFiltro(e.target.value); }}
        autoComplete="off"
      />
      {abierto && (
        <ul role="listbox" style={listaEstilo}>
          {filtradas.map((c) => (
            <li
              key={c}
              role="option"
              aria-selected={normaliza(c) === normaliza(value)}
              onClick={(e) => { e.preventDefault(); onChange(c); cerrar(); }}
              style={opcionEstilo(normaliza(c) === normaliza(value))}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-elevated)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              {c}
            </li>
          ))}
          {filtradas.length === 0 && (
            <li style={{ padding: "8px 10px", color: "var(--text-dim)", fontSize: "0.85rem" }}>
              {t("form.ciudadSinResultados")}
            </li>
          )}
          {/* «Otra ciudad…»: el catálogo no tiene todas las ciudades del mundo,
              y esta es la salida visible para las que faltan. */}
          <li
            role="option"
            aria-selected={false}
            onClick={(e) => { e.preventDefault(); setLibre(true); cerrar(); onChange(""); }}
            style={{
              padding: "8px 10px", cursor: "pointer", borderRadius: 6,
              marginTop: 4, borderTop: "1px solid var(--border)",
              color: "var(--chung-light)", fontWeight: 700,
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-elevated)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          >
            {t("geo.otraCiudad")}
          </li>
        </ul>
      )}
    </div>
  );
}

export default function DelegacionSelect({
  delegacion,
  pais,
  onChange,
  maxLen = 120,
}: {
  delegacion: string;
  pais: string;
  onChange: (delegacion: string, pais: string) => void;
  maxLen?: number;
}) {
  const { t } = useI18n();
  const ciudades = pais ? ciudadesDe(pais) : [];
  // Etiquetas ligadas por htmlFor (no envolviendo al input): ver nota de arriba.
  const idPais = useId();
  const idCiudad = useId();

  return (
    <div className="deleg-grid">
      <div className="deleg-field">
        <label className="deleg-label" htmlFor={idPais}>{t("camp.campos.pais")}</label>
        <PaisCombobox
          id={idPais}
          value={pais}
          onChange={(nuevoPais) => {
            // Al cambiar de país, conservar la ciudad solo si pertenece al
            // nuevo país; si no, limpiarla para no dejar un par incoherente.
            const pertenece = ciudadesDe(nuevoPais).some(
              (c) => normaliza(c) === normaliza(delegacion),
            );
            onChange(pertenece ? delegacion : "", nuevoPais);
          }}
        />
      </div>
      <div className="deleg-field">
        <label className="deleg-label" htmlFor={idCiudad}>{t("form.delegacion")}</label>
        <CiudadCombobox
          // Rehacer el campo al cambiar de país: si no, el modo «Otra ciudad…»
          // seguiría activo con las ciudades del país anterior.
          key={pais}
          id={idCiudad}
          value={delegacion}
          ciudades={ciudades}
          disabled={!pais}
          maxLen={maxLen}
          onChange={(ciudad) => onChange(ciudad, pais)}
        />
      </div>

      <style>{`
        .deleg-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 10px;
        }
        .deleg-field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
        /* ── Etiqueta de campo: minusculas ─────────────────────────────
           «font-weight: 800» + MAYUSCULAS en la sans del cuerpo hace que el
           NOMBRE del campo pese mas que lo que hay dentro. En un formulario de
           doce campos eso es doce palabras gritando y ningun dato destacando.
           En Membresias la misma etiqueta es «.muted» a 0.8 rem, en minusculas.
           Ver «.microetiqueta» en «estilos-ecosistema.css» para la regla
           entera: MAYUSCULAS solo en titular, antetitulo y nombre de dato. */
        .deleg-label {
          font-size: 0.8rem; font-weight: 600;
          color: var(--text-muted);
          cursor: pointer;
        }
      `}</style>
    </div>
  );
}
