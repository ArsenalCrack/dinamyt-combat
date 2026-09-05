"use client";

import { useCallback, useEffect, useState } from "react";
import {
  EVENTO_MANTENIMIENTO,
  obtenerMantenimientoAPI,
  type EstadoMantenimiento,
} from "@/lib/api";
import Logo from "@/components/Logo";
import { useI18n } from "@/lib/i18n";

/**
 * Puerta de la aplicación mientras el superadmin sube una actualización.
 *
 * Envuelve TODA la app en el layout. Cuando el mantenimiento está puesto,
 * enseña un aviso en lugar de la pantalla que tocaba — a todos menos al
 * superadmin, que es quien tiene que poder entrar a apagarlo.
 *
 * Tres cosas que hace a propósito:
 *
 * 1. **Falla abierto.** Si el backend no contesta, se sigue como si no hubiera
 *    mantenimiento. En la LAN de un campeonato el servidor se cae por un cable
 *    suelto más a menudo que por una actualización, y cerrar la aplicación por
 *    un error de red sería peor que el problema.
 * 2. **Quien decide es el servidor** (`exento`), no el perfil guardado en el
 *    navegador: ese puede ser de un login viejo y no traer el dato.
 * 3. **Se reabre sola.** Sigue consultando cada pocos segundos, así que al
 *    apagar el mantenimiento las pantallas vuelven sin que nadie recargue —
 *    incluidas las de los tatamis, que suelen estar sin teclado al lado.
 */

/** Cada cuánto se vuelve a preguntar, en milisegundos. */
const SONDEO_MS = 15000;
/** Con el aviso puesto se pregunta más seguido: es cuando importa volver. */
const SONDEO_ACTIVO_MS = 5000;

export default function PorteroMantenimiento({
  children,
}: {
  children: React.ReactNode;
}) {
  const { t } = useI18n();
  const [estado, setEstado] = useState<EstadoMantenimiento | null>(null);
  const [comprobando, setComprobando] = useState(false);

  const comprobar = useCallback(async () => {
    setComprobando(true);
    try {
      setEstado(await obtenerMantenimientoAPI());
    } catch {
      // Sin respuesta no se cierra nada (ver el punto 1 del comentario).
      setEstado(null);
    } finally {
      setComprobando(false);
    }
  }, []);

  const cerrado = Boolean(estado?.activo && !estado.exento);

  // Primera comprobación y aviso inmediato desde cualquier petición que reciba
  // el 503 del backend: así la pantalla sale en el momento, sin esperar al
  // siguiente sondeo. `queueMicrotask` para no tocar el estado dentro del
  // cuerpo del efecto (misma pauta que el resto de la app).
  useEffect(() => {
    let cancelado = false;
    queueMicrotask(() => { if (!cancelado) void comprobar(); });

    const alAvisar = () => void comprobar();
    window.addEventListener(EVENTO_MANTENIMIENTO, alAvisar);
    return () => {
      cancelado = true;
      window.removeEventListener(EVENTO_MANTENIMIENTO, alAvisar);
    };
  }, [comprobar]);

  // Sondeo periódico: es lo que hace que las pantallas vuelvan solas cuando el
  // superadmin apaga el mantenimiento.
  useEffect(() => {
    const id = setInterval(comprobar, cerrado ? SONDEO_ACTIVO_MS : SONDEO_MS);
    return () => clearInterval(id);
  }, [comprobar, cerrado]);

  if (!cerrado) return <>{children}</>;

  const desde = estado?.desde ? new Date(estado.desde) : null;

  return (
    <div className="mant-page">
      <div className="mant-bg" aria-hidden="true" />

      <div className="mant-card card animate-slide" role="status" aria-live="polite">
        <Logo stacked fontSize="clamp(1.6rem, 5vw, 2.2rem)" />

        <div className="mant-icono" aria-hidden="true">🛠️</div>
        <h1 className="mant-titulo">{t("mant.titulo")}</h1>

        {/* El aviso que escribió el superadmin manda sobre el texto genérico:
            es él quien sabe cuánto va a tardar y por qué. */}
        <p className="mant-desc">{estado?.mensaje || t("mant.desc")}</p>

        {desde && (
          <p className="mant-desde">
            {t("mant.desde")} {desde.toLocaleString()}
          </p>
        )}

        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void comprobar()}
          disabled={comprobando}
        >
          {comprobando ? t("mant.comprobando") : t("mant.reintentar")}
        </button>

        <p className="mant-nota">{t("mant.aviso")}</p>
      </div>

      <style>{`
        .mant-page {
          min-height: 100dvh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
          position: relative;
          overflow: hidden;
        }
        .mant-bg {
          position: absolute;
          inset: 0;
          background:
            radial-gradient(ellipse 80% 50% at 20% 30%, rgba(240,184,0,0.07) 0%, transparent 60%),
            radial-gradient(ellipse 60% 40% at 80% 70%, rgba(0,85,255,0.05) 0%, transparent 60%);
          pointer-events: none;
          z-index: 0;
        }
        .mant-card {
          position: relative;
          z-index: 1;
          width: 100%;
          max-width: 480px;
          text-align: center;
          border-color: var(--gold-border);
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
          padding: 32px 28px;
        }
        .mant-icono { font-size: 2.4rem; line-height: 1; }
        /* Interletrado NEGATIVO y la letra de titular, como en las otras tres
           webs. El +0.06em venia de Bebas Neue, que es condensada y necesita
           aire; Archivo es ancha y con ese valor la palabra se desparrama.
           Ver .display en estilos-ecosistema.css. */
        .mant-titulo {
          font-family: var(--font-display);
          font-size: 1.25rem;
          font-weight: 800;
          font-stretch: 118%;
          color: var(--text);
          text-transform: uppercase;
          letter-spacing: -0.015em;
        }
        .mant-desc {
          font-size: 0.94rem;
          color: var(--text-muted);
          line-height: 1.5;
        }
        .mant-desde {
          font-family: var(--font-mono, monospace);
          font-size: 0.8rem;
          color: var(--text-dim);
        }
        .mant-nota {
          font-size: 0.82rem;
          color: var(--text-dim);
        }
      `}</style>
    </div>
  );
}
