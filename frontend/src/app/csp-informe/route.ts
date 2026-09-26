/**
 * Donde el navegador cuenta lo que la CSP bloquearía (`cabeceras-seguridad.ts`).
 *
 * Se escribe en el registro del servicio con `[CSP]` delante, para leerlo en la
 * VPS con `journalctl … | grep CSP`. Es la semana de pruebas antes de encender
 * la CSP de verdad.
 *
 * ⚠️ Es una ruta sin sesión que escribe en el registro: tope de 30 líneas por
 * minuto y de 2 KB por informe, para que nadie pueda inundarlo.
 */
let desde = 0;
let cuenta = 0;

export async function POST(req: Request) {
  const ahora = Date.now();
  if (ahora - desde > 60_000) {
    desde = ahora;
    cuenta = 0;
  }
  if (++cuenta <= 30) {
    const texto = (await req.text()).slice(0, 2000);
    try {
      const cuerpo = JSON.parse(texto);
      const r = cuerpo['csp-report'] ?? cuerpo;
      console.warn(
        `[CSP] ${r['violated-directive'] ?? r.effectiveDirective ?? '?'} bloquearía ` +
          `${r['blocked-uri'] ?? r.blockedURL ?? '?'} en ${r['document-uri'] ?? r.documentURL ?? '?'}`,
      );
    } catch {
      console.warn('[CSP] informe ilegible');
    }
  }
  return new Response(null, { status: 204 });
}
