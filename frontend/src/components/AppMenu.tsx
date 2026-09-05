"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import LogoutButton from "@/components/LogoutButton";
import { PORTAL_URL } from "@/lib/portal";
import { aplicarTema, getTema, temaEfectivo, type Tema } from "@/lib/theme";
import { guardarAparienciaEnLaCuenta } from "@/lib/api";
import { IDIOMAS, useI18n } from "@/lib/i18n";

/**
 * La cuadrícula de aplicaciones, dibujada y no escrita.
 *
 * Por lo mismo que el icono de salir: los símbolos técnicos que parecen
 * iconos (⇱, ⊞, ⏻) no están en las fuentes de Android y salen como el
 * cuadrito de «glifo que no tengo». Un SVG se ve igual en todos lados y
 * hereda el color del texto.
 *
 * Es el MISMO dibujo en Campeonatos, Membresías y Academy: la puerta al
 * ecosistema se reconoce por su forma antes que por su texto.
 */
function IconoEcosistema() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
      style={{ flexShrink: 0 }}
    >
      <rect x="3" y="3" width="7.5" height="7.5" rx="2" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="2" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="2" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2" />
    </svg>
  );
}

interface SesionUser {
  nombre?: string;
  rol?: "admin" | "juez" | "maestro";
}

/**
 * Barra superior global con menú hamburguesa. Va montada en el layout, así que
 * acompaña al usuario en casi toda la app (fija arriba, también en móvil): desde
 * cualquier página puede volver al inicio o cerrar sesión sin devolverse hasta
 * el panel principal. Es una BARRA (no un botón flotante) para que el contenido
 * pase por debajo sin chocar con los botones de cada página.
 *
 * Se OCULTA en: /login y en las pantallas inmersivas que ya tienen su propia
 * barra superior (el tatami del Juez Central/jueces, con "Volver" y
 * "Activar/Desactivar"). Ahí no aporta y chocaría.
 */
export default function AppMenu() {
  const pathname = usePathname();
  const router = useRouter();
  const { t, idioma, setIdioma } = useI18n();
  const [user, setUser] = useState<SesionUser | null>(null);
  const [open, setOpen] = useState(false);
  // Arranca en "dark" (igual que el servidor) y se sincroniza al montar:
  // así el HTML del servidor y el primer render del cliente coinciden.
  const [tema, setTema] = useState<Tema>("sistema");
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) setTema(getTema());
    });
    return () => { cancelled = true; };
  }, []);

  function cambiarTema() {
    // Dos estados en el boton, no tres: `sistema` es un punto de partida, no un
    // destino al que alguien quiera volver pulsando. Las tres escritas estan en
    // el perfil del portal, que es donde se elige de verdad.
    const nuevo: Tema = temaEfectivo(tema) === "claro" ? "oscuro" : "claro";
    aplicarTema(nuevo);
    setTema(nuevo);
    // Y a la CUENTA, para que valga tambien en el portal, en Membresias y en
    // Academy: `localStorage` no cruza subdominios.
    guardarAparienciaEnLaCuenta({ theme: nuevo });
  }

  // Releer la sesión en cada cambio de ruta (tras login/logout) y cerrar el panel
  useEffect(() => {
    try {
      const raw = localStorage.getItem("dinamyt_user");
      setUser(raw ? (JSON.parse(raw) as SesionUser) : null);
    } catch {
      setUser(null);
    }
    setOpen(false);
  }, [pathname]);

  // Cerrar al hacer clic/tocar fuera o con Escape
  useEffect(() => {
    if (!open) return;
    function fuera(e: MouseEvent | TouchEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function tecla(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", fuera);
    document.addEventListener("touchstart", fuera);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("touchstart", fuera);
      document.removeEventListener("keydown", tecla);
    };
  }, [open]);

  const oculta =
    pathname === "/login" ||
    pathname.startsWith("/tatami");
  const visible = !!user && !oculta;

  // Reservar el alto de la barra en el body para que el contenido no quede
  // tapado (la barra es fija). Solo cuando la barra se muestra.
  useEffect(() => {
    document.body.classList.toggle("has-appmenu", visible);
    return () => document.body.classList.remove("has-appmenu");
  }, [visible]);

  if (!visible || !user) return null;

  const inicio = user.rol === "admin" ? "/admin" : user.rol === "maestro" ? "/maestro" : "/juez";
  const rolLabel =
    user.rol === "admin" ? t("rol.admin")
    : user.rol === "maestro" ? t("rol.maestro")
    : t("rol.juez");

  function ir(ruta: string) {
    setOpen(false);
    router.push(ruta);
  }

  return (
    <header ref={ref} className="appmenu">
      <button
        type="button"
        className="appmenu-toggle"
        aria-label={open ? t("menu.cerrar") : t("menu.abrir")}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="appmenu-bars" data-open={open} aria-hidden="true">
          <span /><span /><span />
        </span>
        <span className="appmenu-toggle-label">{t("menu.etiqueta")}</span>
      </button>

      {open && (
        <div className="appmenu-panel" role="menu">
          <div className="appmenu-user">
            <div className="appmenu-user-name">{user.nombre || t("menu.sesion")}</div>
            <div className="appmenu-user-role">{rolLabel}</div>
          </div>
          <button type="button" role="menuitem" className="appmenu-item" onClick={() => ir(inicio)}>
            {t("menu.inicio")}
          </button>
          <button type="button" role="menuitem" className="appmenu-item" onClick={() => ir("/pantalla")}>
            {t("menu.pantallaPublica")}
          </button>
          <button type="button" role="menuitem" className="appmenu-item" onClick={() => ir("/campeonatos")}>
            {t("menu.campeonatos")}
          </button>
          <button type="button" role="menuitem" className="appmenu-item" onClick={cambiarTema}>
            {temaEfectivo(tema) === "oscuro" ? t("menu.modoClaro") : t("menu.modoOscuro")}
          </button>
          <div className="appmenu-sep" />
          {/* Selector de idioma: los disponibles, con el activo resaltado */}
          <div className="appmenu-lang" role="group" aria-label={t("menu.idioma")}>
            <span className="appmenu-lang-label">🌐 {t("menu.idioma")}</span>
            <div className="appmenu-lang-btns">
              {IDIOMAS.map((l) => (
                <button
                  key={l.codigo}
                  type="button"
                  className="appmenu-lang-btn"
                  data-activo={idioma === l.codigo}
                  aria-pressed={idioma === l.codigo}
                  onClick={() => setIdioma(l.codigo)}
                >
                  {l.etiqueta}
                </button>
              ))}
            </div>
          </div>
          <div className="appmenu-sep" />

          {/**
            * La puerta de vuelta al ecosistema.
            *
            * ── El agujero que tapa ──
            *
            * Desde DINAMYT se entra aquí con un botón, pero de aquí no se
            * volvía: al portal solo se llegaba por el enlace del aviso de
            * «este pase no abre esta consola» o cerrando sesión. Salir de una
            * app no puede ser la forma de llegar a la de al lado.
            *
            * ── Por qué NO lleva `?redirect=` ──
            *
            * Porque ir a DINAMYT significa ir a DINAMYT. Ese parámetro le dice
            * al portal «cuando acabes, devuélvelo aquí», y es justo el que se
            * quedaba pegado en el historial del navegador y acababa metiendo
            * en la app equivocada a quien quería el portal. El destino es el
            * dashboard, y punto.
            *
            * ── Por qué aquí abajo ──
            *
            * Junto a «Salir» están las dos cosas que te sacan de esta app. El
            * resto del menú son pantallas de aquí dentro.
            */}
          <a
            href={`${PORTAL_URL}/dashboard`}
            role="menuitem"
            className="appmenu-item"
            title={t("menu.ecosistemaTitulo")}
          >
            <IconoEcosistema />
            {t("menu.ecosistema")}
          </a>

          {/* ── Por qué esta separación ──
              «Ir a DINAMYT» y «Salir» hacen lo mismo desde lejos —los dos te
              sacan de esta app— pero uno te lleva a tu portal y el otro te
              cierra la sesión, y equivocarse cuesta volver a escribir la
              contraseña. Pegados, al pasar el ratón los dos fondos se tocaban y
              parecían un solo bloque; el de arriba además ES un `<a>` con
              `:hover` propio. Ocho píxeles no son decoración: son el margen de
              un dedo en un teléfono. */}
          <div style={{ height: 8 }} />
          <LogoutButton />
        </div>
      )}
    </header>
  );
}
