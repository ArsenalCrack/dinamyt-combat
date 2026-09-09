"use client";

import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { logoutAPI } from "@/lib/api";
import { PORTAL_URL, urlDeSalida, urlSalirDelPortal } from "@/lib/portal";

/**
 * El símbolo de encendido de «Salir», dibujado en vez de escrito.
 *
 * ── Por qué este dibujo y no el de antes ─────────────────────────────────────
 *
 * Aquí había una puerta con una flecha saliendo. No estaba mal — pero era la
 * única de las cuatro webs con ese dibujo: el portal, Membresías y Academy usan
 * el símbolo de encendido, y el menú de esta app es, línea por línea, el mismo
 * que el de Membresías. Dos iconos para la misma acción en dos apps que se
 * abren una al lado de la otra es de las cosas que hacen que el ecosistema se
 * sienta como tres programas y no como uno.
 *
 * Es literalmente el mismo `path` que `IconoSalir` en `NavBar.tsx` de
 * Membresías y en el panel del portal, con el mismo grosor de trazo.
 */
function IconoSalir() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
      style={{ flexShrink: 0 }}
    >
      <path d="M12 2.8v9.4" />
      <path d="M6.3 6.3a8 8 0 1 0 11.4 0" />
    </svg>
  );
}

/**
 * Botón de cerrar sesión. **Igual que en Membresías y en el portal: sin
 * preguntar.**
 *
 * ── Por qué se quitó la pregunta ─────────────────────────────────────────────
 *
 * Aquí había un diálogo modal —«¿Cerrar sesión?», con su fondo oscuro, su
 * emoji y sus dos botones— y era la única de las cuatro webs que lo tenía. El
 * razonamiento de entonces se sostenía por sí solo: salir sin querer en mitad
 * de un combate, con el marcador en pantalla, cuesta más que salir sin querer
 * de un roster.
 *
 * Lo que no aguanta es mirarlo desde fuera del archivo. La misma persona abre
 * Membresías y Campeonatos en la misma tarde, con la misma cuenta, y el mismo
 * botón rojo, en el mismo sitio del mismo menú, se comporta distinto: en una
 * sale, en la otra pregunta. Eso no se lee como «esta app es más cuidadosa»;
 * se lee como que son dos programas distintos, que es justo lo que §4.9 existe
 * para evitar.
 *
 * Y el peligro que la pregunta protegía es más pequeño de lo que parecía: para
 * llegar a este botón hay que ABRIR EL MENÚ y bajar hasta el final, o sea dos
 * gestos deliberados. El tatami —la pantalla donde de verdad dolería— ni
 * siquiera dibuja la barra, así que este botón no está ahí.
 *
 * ── Lo que sí se queda ───────────────────────────────────────────────────────
 *
 * El estado de carga mientras el servidor cierra: sin él, pulsar y no ver nada
 * durante medio segundo es exactamente el disfraz del «pulso Salir y no pasa
 * nada» que esta app ya se comió tres veces.
 */
export default function LogoutButton({ label }: { label?: string }) {
  const { t } = useI18n();
  const [loggingOut, setLoggingOut] = useState(false);

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
   * acaba de salir se queda una flecha atrás. Se volvía a ella —restaurada del
   * bfcache tal como estaba— y ahí ninguna acción funcionaba: la sesión estaba
   * cerrada de verdad y cada petición contestaba 401. Una pantalla muerta que
   * parece viva es peor que no poder volver.
   *
   * `replace` sustituye la entrada: la flecha atrás lleva a donde se estaba
   * ANTES de entrar a la consola, que es lo que la persona espera.
   */
  async function handleLogout() {
    if (loggingOut) return;
    setLoggingOut(true);
    // La cookie de sesión es httpOnly: solo el backend puede borrarla, así
    // que limpiar aquí a secas dejaría la sesión viva en el servidor.
    const salida = await logoutAPI();
    const hayPortal = (salida.portal ?? true) && Boolean(PORTAL_URL);
    window.location.replace(hayPortal ? urlSalirDelPortal() : urlDeSalida(false));
  }

  return (
    /* ── Por qué ya no es un botón «neutro que se pone rojo al pasar» ─────
       Porque en Membresías y en el portal este botón es rojo desde el
       principio, y es el único del menú que lo es: eso es lo que dice de un
       vistazo cuál de los cinco no hay que tocar sin mirar. Aquí salía en
       gris hasta que lo rozabas — o sea, en un teléfono, nunca. */
    <button
      type="button"
      className="btn btn-danger"
      style={{ width: "100%", justifyContent: "flex-start", gap: 7 }}
      onClick={() => void handleLogout()}
      disabled={loggingOut}
    >
      <IconoSalir />
      <span>{loggingOut ? t("logout.cerrando") : label ?? t("logout.boton")}</span>
    </button>
  );
}
