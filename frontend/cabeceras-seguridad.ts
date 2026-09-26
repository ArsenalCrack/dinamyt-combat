/**
 * LAS CABECERAS DE SEGURIDAD de esta web (OPERAR.md §4.24).
 *
 * Hasta el 26 sep 2026 ninguna de las cuatro webs mandaba ni una: ni CSP, ni
 * HSTS, ni `X-Frame-Options`. El portal guarda el pase de DINAMYT al alcance
 * de JavaScript, así que un XSS sería un robo de sesión; no se ha encontrado
 * ninguno, pero la CSP es la red de debajo.
 *
 * Este archivo es IGUAL en las cuatro webs (portal, Academy, Membresías y
 * Campeonatos); lo que cambia es lo que cada `next.config.ts` le pasa. Si se
 * toca aquí, se toca en las cuatro.
 *
 * ── La CSP va primero en modo INFORME ──
 *
 * `Content-Security-Policy-Report-Only` no bloquea nada: el navegador avisa de
 * lo que bloquearía, y lo manda a `/csp-informe`, que lo escribe en el registro
 * del servicio (`[CSP] …`). Con una semana limpia se enciende de verdad con
 * `CSP_ESTRICTA=1` al COMPILAR (las cabeceras se hornean en el build).
 *
 * ── Por qué `'unsafe-inline'` en los guiones ──
 *
 * Next mete guiones en línea (la carga de RSC) y los anti-parpadeo del tema son
 * en línea. Con nonces habría que generarlos por petición y se perdería el
 * pre-renderizado. Lo que corta la exfiltración y el clickjacking es lo demás:
 * `connect-src`, `img-src`, `frame-ancestors`, `object-src`, `base-uri` y
 * `form-action`, cerrados. Los nonces, en otra vuelta si compensan.
 */

export interface OpcionesSeguridad {
  /** Orígenes a los que el navegador pide datos (fetch, XHR, WebSocket). */
  conectar?: (string | undefined)[];
  /** Orígenes de las imágenes. `https:` = cualquiera por HTTPS. */
  imagenes?: (string | undefined)[];
  /** Orígenes que se pueden embeber en un `<iframe>`. */
  marcos?: (string | undefined)[];
  /** Orígenes de audio y video. */
  medios?: (string | undefined)[];
}

/** El origen de una URL (`https://x.org`), o la fuente tal cual si ya lo es. */
function origen(valor: string | undefined): string | null {
  if (!valor) return null;
  if (/^[a-z]+:$/.test(valor) || valor.includes('*')) return valor; // `https:`, `http://*:5000`
  try {
    return new URL(valor).origin;
  } catch {
    return null;
  }
}

function lista(valores: (string | undefined)[] = []): string {
  return [...new Set(valores.map(origen).filter((v): v is string => !!v))].join(' ');
}

export function cabecerasDeSeguridad(o: OpcionesSeguridad = {}) {
  const enDesarrollo = process.env.NODE_ENV !== 'production';
  const csp = [
    "default-src 'self'",
    // `'unsafe-eval'` solo en `next dev`: el recargado en caliente lo usa.
    `script-src 'self' 'unsafe-inline'${enDesarrollo ? " 'unsafe-eval'" : ''}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${lista(o.imagenes)}`.trim(),
    "font-src 'self' data:",
    `connect-src 'self' ${lista(o.conectar)}`.trim(),
    `media-src 'self' blob: ${lista(o.medios)}`.trim(),
    `frame-src ${lista(o.marcos) || "'none'"}`,
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
    'report-uri /csp-informe',
  ].join('; ');

  return [
    { key: 'X-Content-Type-Options', value: 'nosniff' },
    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
    { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
    // La cámara y el micrófono, para la propia web: el kiosco de Membresías lee
    // QR y Academy graba las figuras. `camera=()` los rompería.
    {
      key: 'Permissions-Policy',
      value: 'camera=(self), microphone=(self), geolocation=(), payment=(), usb=()',
    },
    // Solo cuenta por HTTPS: en el PC del evento (http en la LAN) se ignora.
    // Sin `includeSubDomains`: cada web manda la suya.
    { key: 'Strict-Transport-Security', value: 'max-age=31536000' },
    {
      key:
        process.env.CSP_ESTRICTA === '1'
          ? 'Content-Security-Policy'
          : 'Content-Security-Policy-Report-Only',
      value: csp,
    },
  ];
}
