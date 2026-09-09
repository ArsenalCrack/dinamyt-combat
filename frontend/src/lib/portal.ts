"use client";

/**
 * El portal del ecosistema (DINAMYT), visto desde Campeonatos.
 *
 * Vivía como una constante suelta dentro de `app/login/page.tsx`, y salió de
 * ahí en cuanto «Salir» necesitó exactamente la misma dirección: dos copias de
 * una URL de despliegue es cómo una de las dos se queda apuntando al
 * `localhost` de siempre el día que la otra se configura.
 */
export const PORTAL_URL =
  process.env.NEXT_PUBLIC_ECOSYSTEM_PORTAL_URL || "https://dinamyt.org";

/**
 * A dónde se aterriza al salir. **Nunca es `/login` a secas.**
 *
 * `?salida` hace dos cosas en `app/login/page.tsx`: apaga el canje del
 * `#token=` —nadie entra por una pantalla a la que se llegó saliendo— y
 * enciende el remate, que vuelve a cerrar si el servidor todavía reconoce la
 * sesión. Su valor dice de CUÁNTAS sesiones se salió, y de eso depende la
 * frase que se lee al llegar: en el modo local no hay ningún DINAMYT del que
 * salir, y prometerlo sería mentir.
 */
export function urlDeSalida(hayPortal: boolean): string {
  return `/login?salida=${hayPortal ? "portal" : "sola"}`;
}

/**
 * A dónde lleva «← Inicio» en las pantallas PÚBLICAS (resultados, la lista de
 * campeonatos, la pantalla de proyección).
 *
 * ── Qué hacía, y por qué estaba mal ─────────────────────────────────────────
 *
 * `router.push("/login")`. O sea: el único botón de estas pantallas que se
 * llama «Inicio» llevaba al FORMULARIO DE CONTRASEÑA de Campeonatos. Quien
 * llega a los resultados desde un cartel —un padre, un competidor, alguien que
 * pasaba por ahí— pulsaba «Inicio» y acababa delante de una consola de jueces
 * que no es suya y de una contraseña que no tiene. Es el mismo fallo que ya se
 * había arreglado en el logo (`Logo.tsx`, `alPortal`) y que aquí se quedó sin
 * arreglar: media reparación es la que confunde más, porque el logo lleva a
 * DINAMYT y el botón de al lado no.
 *
 * Inicio es DINAMYT. Cuando hay portal, ahí va.
 *
 * ── Y cuando no hay portal ──────────────────────────────────────────────────
 *
 * En el modo local del día del evento no hay ningún dinamyt.org al que llegar:
 * ahí `/login` sí es el inicio, porque es la única casa que existe. Devolver
 * una ruta relativa es la señal de que hay que navegar con el router y no con
 * el navegador entero; `esExterno` lo dice sin tener que adivinarlo.
 */
export function urlDeInicioPublico(): string {
  return PORTAL_URL || "/login";
}

/** `true` si la dirección sale de esta app (otro origen: el router de Next no
 *  llega ahí y hay que usar `<a>` o `window.location`). */
export function esExterno(url: string): boolean {
  return /^https?:\/\//i.test(url);
}

/**
 * La ruta de salida del portal, que cierra la sesión de DINAMYT y devuelve.
 *
 * `PORTAL/salir` no pide nada, no pregunta nada y funciona igual si no había
 * sesión que cerrar: cuesta una redirección y quita una clase entera de
 * fallos. El destino va en lista blanca al otro lado (`lib/apps.ts` del
 * portal), así que tiene que ser el origen de esta app tal cual.
 */
export function urlSalirDelPortal(): string {
  const vuelta = `${window.location.origin}${urlDeSalida(true)}`;
  return `${PORTAL_URL}/salir?redirect=${encodeURIComponent(vuelta)}`;
}
