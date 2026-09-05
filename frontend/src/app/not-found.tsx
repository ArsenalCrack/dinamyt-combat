"use client";

import { usePathname, useRouter } from "next/navigation";
import Logo from "@/components/Logo";
import { useI18n } from "@/lib/i18n";

/**
 * Página no encontrada (404).
 *
 * Next atrapa con este archivo CUALQUIER dirección que no corresponda a una
 * pantalla de la app. Sin él, quien se equivoca al teclear la URL —o abre un
 * enlace viejo desde el celular— se encontraba la pantalla en blanco y negro
 * que trae Next de fábrica, en inglés y sin ninguna salida.
 *
 * Va dentro del layout, así que conserva la barra de menú y el tema elegido:
 * quien tiene sesión no se queda encerrado aquí.
 */
export default function NoEncontrada() {
  const router = useRouter();
  const { t } = useI18n();
  const pathname = usePathname();

  return (
    <div className="e404-page">
      <div className="e404-bg" aria-hidden="true" />

      <div className="e404-card card animate-slide">
        <Logo stacked fontSize="clamp(1.6rem, 5vw, 2.2rem)" />

        <div className="e404-codigo" aria-hidden="true">
          {t("e404.codigo")}
        </div>

        <h1 className="e404-titulo">{t("e404.titulo")}</h1>
        <p className="e404-desc">{t("e404.desc")}</p>

        {/* La dirección pedida, tal cual: es lo primero que hay que ver para
            saber si fue un dedazo o un enlace mal copiado. */}
        <div className="e404-ruta">
          <span className="e404-ruta-label">{t("e404.ruta")}</span>
          <code className="e404-ruta-valor">{pathname}</code>
        </div>

        <div className="e404-acciones">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => router.push("/")}
          >
            {t("e404.inicio")}
          </button>
          <button type="button" className="btn" onClick={() => router.back()}>
            {t("e404.volver")}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => router.push("/pantalla")}
          >
            {t("e404.pantalla")}
          </button>
        </div>
      </div>

      <style>{`
        .e404-page {
          min-height: 100dvh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
          position: relative;
          overflow: hidden;
        }
        .e404-bg {
          position: absolute;
          inset: 0;
          background:
            radial-gradient(ellipse 80% 50% at 20% 30%, rgba(240,184,0,0.06) 0%, transparent 60%),
            radial-gradient(ellipse 60% 40% at 80% 70%, rgba(0,85,255,0.05) 0%, transparent 60%);
          pointer-events: none;
          z-index: 0;
        }
        .e404-card {
          position: relative;
          z-index: 1;
          width: 100%;
          max-width: 520px;
          text-align: center;
          border-color: var(--gold-border);
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
          padding: 32px 28px;
        }
        .e404-codigo {
          font-family: var(--font-display);
          font-size: clamp(4rem, 18vw, 7rem);
          line-height: 0.9;
          color: var(--gold);
          letter-spacing: 0.06em;
          text-shadow: 0 0 30px var(--gold-bg);
        }
        /* Interletrado NEGATIVO y la letra de titular, como en las otras tres
           webs. El +0.06em venia de Bebas Neue, que es condensada y necesita
           aire; Archivo es ancha y con ese valor la palabra se desparrama.
           Ver .display en estilos-ecosistema.css. */
        .e404-titulo {
          font-family: var(--font-display);
          font-size: 1.25rem;
          font-weight: 800;
          font-stretch: 118%;
          color: var(--text);
          text-transform: uppercase;
          letter-spacing: -0.015em;
        }
        .e404-desc {
          font-size: 0.94rem;
          color: var(--text-muted);
          line-height: 1.5;
        }
        .e404-ruta {
          width: 100%;
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          padding: 10px 12px;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .e404-ruta-label {
          font-size: 0.72rem;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: var(--text-dim);
        }
        .e404-ruta-valor {
          font-family: var(--font-mono, monospace);
          font-size: 0.86rem;
          color: var(--text-muted);
          overflow-wrap: anywhere;
        }
        .e404-acciones {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          justify-content: center;
          width: 100%;
        }
        .e404-acciones .btn {
          flex: 1 1 150px;
        }
      `}</style>
    </div>
  );
}
