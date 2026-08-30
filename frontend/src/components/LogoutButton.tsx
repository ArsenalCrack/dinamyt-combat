"use client";

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { logoutAPI } from "@/lib/api";
import { PORTAL_URL, urlDeSalida, urlSalirDelPortal } from "@/lib/portal";

/**
 * Botón de cerrar sesión con confirmación.
 * Buenas prácticas aplicadas:
 * - Icono + etiqueta visible (no solo icono).
 * - Estilo neutro en reposo, peligro solo al pasar el cursor (no alarma).
 * - Diálogo de confirmación para evitar cierres accidentales en pleno torneo.
 * - Accesible: role="dialog", cierre con Escape, foco inicial en "Cancelar".
 * - Estado de carga mientras se cierra la sesión.
 */
export default function LogoutButton({ label }: { label?: string }) {
  const { t } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!confirming) return;
    cancelRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setConfirming(false);
    }
    window.addEventListener("keydown", onKey);

    // La pantalla de detrás no se mueve mientras se pregunta. Sin esto, el
    // gesto de desplazar sobre el fondo oscuro seguía recorriendo el panel: se
    // leía la pregunta encima de un tatami y al cancelar se estaba en otro
    // sitio. En el celular es peor, porque el pulgar cae justo ahí.
    const scrollPrevio = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = scrollPrevio;
    };
  }, [confirming]);

  /**
   * Salir de verdad, de una sola pulsación, y de las DOS sesiones.
   *
   * ── Por qué hay que pasar por el portal ──
   *
   * Quien entra desde DINAMYT (§4.13) tiene dos sesiones: la cookie de aquí y
   * la del portal, que vive en su dominio y que ningún navegador deja tocar
   * desde fuera. Cerrando solo la de aquí, el portal seguía reconociendo a la
   * persona: volvía al dashboard, pulsaba «Entrar a Campeonatos» y estaba
   * dentro otra vez sin ver una sola pantalla. Es exactamente como se ve un
   * botón de salir roto, aunque el de aquí hubiera hecho su trabajo.
   *
   * ── Quién decide si hay portal ──
   *
   * El **servidor**, en la respuesta del logout. Membresías lo decidía con una
   * marca del `localStorage` y ahí estaba su bug de las dos pulsaciones
   * (§5.12): la marca se perdía sola y nadie se enteraba. Aquí no hay marca
   * que perder. Si el servidor no contestó se pasa igual —de más solo cuesta
   * una redirección; de menos deja media sesión abierta—.
   *
   * ── Por qué se sale con `location` y no con el router ──
   *
   * Es una salida, no una navegación: se quiere una página nueva de cero, sin
   * un solo componente del panel vivo detrás. Y de paso no depende de que el
   * router esté sano, que es justo lo que más falla con el disfraz de «pulso
   * Salir y no pasa nada».
   *
   * ── Y por qué `replace` y no `href` ──
   *
   * `href` EMPUJA una entrada al historial, así que la consola de la que se
   * acaba de salir se queda una flecha atrás. Se volvía a ella —con el diálogo
   * de «¿cerrar sesión?» todavía abierto, porque el navegador restaura la
   * página del bfcache tal como estaba— y ahí ninguna acción funcionaba: la
   * sesión estaba cerrada de verdad y cada petición contestaba 401. Una
   * pantalla muerta que parece viva es peor que no poder volver.
   *
   * `replace` sustituye la entrada: la flecha atrás lleva a donde se estaba
   * ANTES de entrar a la consola, que es lo que la persona espera.
   */
  async function handleLogout() {
    setLoggingOut(true);
    // La cookie de sesión es httpOnly: solo el backend puede borrarla, así
    // que limpiar aquí a secas dejaría la sesión viva en el servidor.
    const salida = await logoutAPI();
    const hayPortal = (salida.portal ?? true) && Boolean(PORTAL_URL);
    window.location.replace(hayPortal ? urlSalirDelPortal() : urlDeSalida(false));
  }

  return (
    <>
      <button
        type="button"
        className="btn btn-sm logout-btn"
        onClick={() => setConfirming(true)}
        aria-haspopup="dialog"
      >
        <svg
          width="15" height="15" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2.2"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
        >
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <polyline points="16 17 21 12 16 7" />
          <line x1="21" y1="12" x2="9" y2="12" />
        </svg>
        <span>{label ?? t("logout.boton")}</span>
      </button>

      {confirming && (
        <div
          className="overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="logout-dialog-title"
          onClick={(e) => {
            if (e.target === e.currentTarget && !loggingOut) setConfirming(false);
          }}
        >
          <div className="overlay-box" style={{ maxWidth: 400, padding: "28px 24px" }}>
            <div style={{ fontSize: "2rem", marginBottom: 8 }} aria-hidden="true">👋</div>
            <h2
              id="logout-dialog-title"
              style={{
                fontSize: "1.15rem", fontWeight: 800,
                letterSpacing: "0.04em", marginBottom: 8,
              }}
            >
              {t("logout.titulo")}
            </h2>
            <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginBottom: 22 }}>
              {t("logout.mensaje")}
            </p>
            <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
              <button
                ref={cancelRef}
                type="button"
                className="btn"
                onClick={() => setConfirming(false)}
                disabled={loggingOut}
                style={{ minWidth: 130 }}
              >
                {t("logout.cancelar")}
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={handleLogout}
                disabled={loggingOut}
                style={{ minWidth: 150, fontWeight: 800 }}
              >
                {loggingOut ? t("logout.cerrando") : t("logout.confirmar")}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .logout-btn {
          gap: 7px;
          color: var(--text-muted);
        }
        .logout-btn:hover,
        .logout-btn:focus-visible {
          background: rgba(255, 68, 68, 0.10);
          border-color: rgba(255, 68, 68, 0.35);
          color: var(--red-alert);
        }
        .logout-btn:focus-visible {
          outline: 2px solid var(--red-alert);
          outline-offset: 2px;
        }
      `}</style>
    </>
  );
}
