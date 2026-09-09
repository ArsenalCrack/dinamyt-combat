'use client';

/* eslint-disable @next/next/no-img-element */
import { useI18n } from '@/lib/i18n';

/**
 * La pantalla de espera, la misma en las cuatro webs.
 *
 * ── Por qué existe ─────────────────────────────────────────────────────────
 *
 * Porque no existía: cada pantalla se inventaba la suya. Auditadas el 9 de
 * septiembre de 2026, veinticinco esperas y al menos cuatro formas distintas —
 * un párrafo gris suelto, un `<main>` con relleno, una tarjeta centrada y, en
 * Campeonatos, un «Cargando…» con la clase de la MARCA, o sea a 2.5 rem y en la
 * tipografía de titular. Puestas seguidas parecían cuatro aplicaciones.
 *
 * ── Qué cambia y qué no ────────────────────────────────────────────────────
 *
 * La FORMA es siempre la misma: el escudo latiendo y una línea debajo, con alto
 * mínimo para que lo que llegue no empuje la página. El TEXTO lo pone cada
 * pantalla, y debe ponerlo: decir qué se está esperando —«Cargando tu
 * perfil…»— es lo único que distingue una espera de un cuelgue.
 *
 * `encajado` es para cuando la espera es de un TROZO —una tabla, una lista
 * dentro de una tarjeta— y no de la pantalla entera: quita el alto mínimo, que
 * ahí dejaría un hueco enorme en mitad del contenido.
 *
 * Las medidas viven en `estilos-ecosistema.css` (`.cargando`), así que son
 * literalmente las mismas en las cuatro.
 */
export function Cargando({
  mensaje,
  encajado = false,
}: {
  mensaje?: string;
  encajado?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div
      className="cargando"
      data-encajado={encajado ? 'true' : undefined}
      role="status"
      aria-live="polite"
    >
      <img src="/logo.png" alt="" className="cargando-marca" />
      <p>{mensaje ?? t('comun.cargando')}</p>
    </div>
  );
}
