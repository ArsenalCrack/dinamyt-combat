"use client";

import { useEffect, useState } from "react";
import { aplicarTema, getTema, temaEfectivo, type Tema } from "@/lib/theme";
import { guardarAparienciaEnLaCuenta } from "@/lib/api";
import { IDIOMAS, useI18n } from "@/lib/i18n";

/**
 * Controles flotantes de TEMA e IDIOMA para las superficies públicas (sin
 * sesión): la pantalla de selección de tatami y la pantalla pública del
 * marcador. El menú global (AppMenu) solo existe con sesión iniciada, así que
 * sin esto un espectador no tenía cómo cambiar el tema ni el idioma.
 *
 * Es un botón 🌐 discreto (esquina inferior derecha, sobre el pie de página)
 * que expande un mini panel. La elección persiste en localStorage igual que
 * en el menú global.
 */
export default function PublicControls() {
  const { t, idioma, setIdioma } = useI18n();
  const [tema, setTema] = useState<Tema>("sistema");
  const [open, setOpen] = useState(false);

  // Sincronizar con el tema guardado al montar (el servidor renderiza "dark")
  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) setTema(getTema());
    });
    return () => { cancelled = true; };
  }, []);

  function cambiarTema() {
    // Dos estados en el boton, no tres: `sistema` es un punto de partida, no un
    // destino al que alguien quiera volver pulsando. Las tres escritas estan en
    // el perfil del portal, que es donde se elige de verdad.
    const nuevo: Tema = temaEfectivo(tema) === "claro" ? "oscuro" : "claro";
    aplicarTema(nuevo);
    setTema(nuevo);
    // Y a la CUENTA, para que valga tambien en el portal, en Membresias y en
    // Academy: `localStorage` no cruza subdominios.
    guardarAparienciaEnLaCuenta({ theme: nuevo });
  }

  return (
    <div className="pubctl">
      {open && (
        <div className="pubctl-panel animate-fade" role="group" aria-label={t("pub.controles")}>
          <button type="button" className="pubctl-item" onClick={cambiarTema}>
            {temaEfectivo(tema) === "oscuro" ? t("menu.modoClaro") : t("menu.modoOscuro")}
          </button>
          <div className="pubctl-langs">
            {IDIOMAS.map((l) => (
              <button
                key={l.codigo}
                type="button"
                className="pubctl-lang"
                data-activo={idioma === l.codigo}
                aria-pressed={idioma === l.codigo}
                onClick={() => setIdioma(l.codigo)}
              >
                {l.etiqueta}
              </button>
            ))}
          </div>
        </div>
      )}
      <button
        type="button"
        className="pubctl-toggle"
        aria-label={t("pub.controles")}
        aria-expanded={open}
        title={t("pub.controles")}
        onClick={() => setOpen((o) => !o)}
      >
        🌐
      </button>

      <style>{`
        .pubctl {
          position: fixed;
          right: 14px;
          bottom: 52px;
          z-index: 60;
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 8px;
        }
        .pubctl-toggle {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          border: 1px solid var(--border);
          background: var(--bg-card);
          color: var(--text);
          font-size: 1.1rem;
          cursor: pointer;
          opacity: 0.65;
          transition: var(--transition);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .pubctl-toggle:hover,
        .pubctl-toggle:focus-visible {
          opacity: 1;
          border-color: var(--border-light);
          outline: none;
        }
        .pubctl-panel {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          padding: 10px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          box-shadow: 0 6px 24px rgba(0,0,0,0.35);
          min-width: 170px;
        }
        .pubctl-item {
          padding: 8px 12px;
          background: transparent;
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          color: var(--text);
          font: inherit;
          font-weight: 600;
          font-size: 0.9rem;
          cursor: pointer;
          text-align: left;
          transition: var(--transition);
        }
        .pubctl-item:hover,
        .pubctl-item:focus-visible {
          background: var(--bg-elevated);
          outline: none;
        }
        .pubctl-langs {
          display: flex;
          gap: 6px;
        }
        .pubctl-lang {
          flex: 1;
          padding: 6px 10px;
          background: transparent;
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          color: var(--text-muted);
          font: inherit;
          font-weight: 600;
          font-size: 0.85rem;
          cursor: pointer;
          transition: var(--transition);
        }
        .pubctl-lang:hover,
        .pubctl-lang:focus-visible {
          color: var(--text);
          background: var(--bg-elevated);
          outline: none;
        }
        .pubctl-lang[data-activo="true"] {
          background: var(--gold-bg);
          border-color: var(--gold-border);
          color: var(--gold);
          font-weight: 800;
        }
      `}</style>
    </div>
  );
}
