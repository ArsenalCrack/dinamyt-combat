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
