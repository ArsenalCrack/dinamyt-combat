"use client";

import { useEffect, useState } from "react";
import { aplicarTema, getTema, temaEfectivo, type Tema } from "@/lib/theme";
import { guardarAparienciaEnLaCuenta } from "@/lib/api";
import { haySesionProbable } from "@/lib/sesion";
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

  /**
   * A la cuenta, pero SOLO con sesion.
   *
   * ── Por que la guarda ──
   *
   * `guardarAparienciaEnLaCuenta` va por `api`, y el interceptor de `api`
   * entiende un 401 como «te caduco la sesion»: limpia y **recarga hacia el
   * login**. Este control vive en las pantallas publicas —el marcador del
   * tatami proyectado en una pared, los resultados, la propia pantalla de
   * entrar—, donde casi nunca hay sesion. O sea que tocar el modo claro
   * mientras se proyecta un combate podia mandar la pared al formulario de
   * login. La peticion se ignoraba sola, pero la redireccion no.
   *
   * Sin sesion no se pierde nada: la eleccion ya viajo a las otras tres webs
   * por la cookie compartida (ver `lib/theme.ts`), y en cuanto la persona
   * entre, `AplicarApariencia` no la pisara porque la cookie manda sobre la
   * cuenta. Lo que la cuenta anade es cruzar de DISPOSITIVO, y para eso hace
   * falta saber quien es.
   */
  function guardarSiHaySesion(datos: { theme?: string; locale?: string }) {
    if (!haySesionProbable()) return;
    guardarAparienciaEnLaCuenta(datos);
  }

  function cambiarTema() {
    // Dos estados en el boton, no tres: `sistema` es un punto de partida, no un
    // destino al que alguien quiera volver pulsando. Las tres escritas estan en
    // el perfil del portal, que es donde se elige de verdad.
    const nuevo: Tema = temaEfectivo(tema) === "claro" ? "oscuro" : "claro";
    aplicarTema(nuevo);
    setTema(nuevo);
    // Y a la CUENTA, para que valga tambien en el portal, en Membresias y en
    // Academy: `localStorage` no cruza subdominios.
    guardarSiHaySesion({ theme: nuevo });
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
                onClick={() => {
                  setIdioma(l.codigo);
                  // Y a la cuenta, igual que el tema y igual que hace el menu
                  // con sesion. Faltaba: el idioma elegido aqui viajaba a las
                  // otras webs de ESTE navegador (la cookie compartida) pero no
                  // al telefono de la misma persona.
                  guardarSiHaySesion({
                    locale: l.codigo === "en" ? "en-US" : "es-CO",
                  });
                }}
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

      {/* Las medidas (`.pubctl*`) se mudaron a `estilos-ecosistema.css`:
          estaban solo aquí y el portal necesitaba el mismo control en su
          portada. Un archivo, cuatro webs. */}
    </div>
  );
}
