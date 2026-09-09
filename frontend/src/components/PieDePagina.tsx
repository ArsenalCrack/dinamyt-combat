'use client';

/* eslint-disable @next/next/no-img-element */
import { usePathname } from 'next/navigation';
import { useI18n } from '@/lib/i18n';
import { PORTAL_URL } from '@/lib/portal';
import { Version } from './Version';

/**
 * El pie de Campeonatos — el mismo que el de Membresías y el del portal.
 *
 * ── Lo que había, que era nada ─────────────────────────────────────────────
 *
 * Campeonatos no tenía pie. Ni aviso de derechos, ni dirección de soporte, ni
 * versión. Así que de las tres webs que se abren con la misma cuenta, una se
 * acababa en blanco: quien no conseguía entrar no tenía a dónde escribir —que
 * es justo cuando hace falta— y quien reportaba un fallo no podía decir qué
 * versión estaba viendo.
 *
 * Dice lo mismo y en el mismo orden que las otras dos: arriba quién es esto y
 * dónde pedir ayuda; abajo, de quién es y qué está corriendo. Las clases
 * (`.pie*`) viven en `estilos-ecosistema.css`, o sea que son literalmente las
 * mismas medidas.
 *
 * ── Dónde NO sale ──────────────────────────────────────────────────────────
 *
 * En el tatami y en la pantalla pública. Las dos son inmersivas —una se maneja
 * de pie junto al área y la otra se proyecta en una pared— y ahí un pie con
 * enlaces legales no es que estorbe: es que se ve a tres metros y no lo va a
 * tocar nadie. Es la misma excepción que el kiosco de Membresías.
 *
 * Y en `/login`, no: ahí es donde más falta hace la dirección de soporte.
 */

/** Primer año publicado de la obra. No se toca: fija la antigüedad. */
const AÑO_INICIAL = 2026;

/** Titular de los derechos. */
const AUTOR = 'Amir Sarmiento';

/**
 * El buzón de quien no puede entrar. El mismo del portal y de Membresías, con
 * el mismo valor por defecto: una instalación sin la variable puesta sigue
 * enseñando una dirección que existe.
 */
const CORREO_SOPORTE =
  process.env.NEXT_PUBLIC_SUPPORT_CONTACT_EMAIL || 'soporte@dinamyt.org';

export default function PieDePagina() {
  const { t } = useI18n();
  const pathname = usePathname();

  if (pathname.startsWith('/tatami') || pathname.startsWith('/pantalla')) {
    return null;
  }

  const ahora = new Date().getFullYear();
  const años = ahora > AÑO_INICIAL ? `${AÑO_INICIAL}–${ahora}` : String(AÑO_INICIAL);

  return (
    <footer className="pie">
      <div className="pie-fila">
        <span className="pie-marca">
          <img src="/logo.png" alt="" width={22} height={22} />
          DINAMYT Campeonatos · Hapkido
        </span>
        <nav className="pie-enlaces">
          {/* Los dos enlaces públicos de esta app: se abren sin entrar, y son
              los que alguien busca cuando llega desde un cartel o un grupo. */}
          <a href="/campeonatos">{t('menu.campeonatos')}</a>
          <a href="/resultados">{t('res.titulo')}</a>
          {PORTAL_URL && (
            <>
              <a href={PORTAL_URL} target="_blank" rel="noopener noreferrer">
                DINAMYT
              </a>
              <a
                href={`${PORTAL_URL}/privacidad`}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t('pie.privacidad')}
              </a>
            </>
          )}
          {/* La dirección va en su propio trozo y con `word-break`: un correo
              partido por la mitad no se puede ni leer ni copiar. */}
          <a href={`mailto:${CORREO_SOPORTE}`} className="pie-soporte">
            <span aria-hidden="true">✉</span>
            <span>{t('pie.ayuda')}</span>
            <span className="pie-correo">{CORREO_SOPORTE}</span>
          </a>
        </nav>
      </div>

      <div className="pie-legal">
        <p>
          © {años} <strong>{AUTOR}</strong> · {t('pie.derechos')}
        </p>
        <p className="pie-legal-nota">{t('pie.nota')}</p>
        <Version />
      </div>
    </footer>
  );
}
