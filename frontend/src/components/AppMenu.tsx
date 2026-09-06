"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import LogoutButton from "@/components/LogoutButton";
import { PORTAL_URL } from "@/lib/portal";
import { alternarModo, getTema, temaEfectivo, type Tema } from "@/lib/theme";
import { guardarAparienciaEnLaCuenta } from "@/lib/api";
import { IDIOMAS, useI18n, type ClaveTexto } from "@/lib/i18n";

/**
 * ════════════════════════════════════════════════════════════════════════════
 * LA BARRA DE ARRIBA — la misma que Membresias, Academy y el portal
 * ════════════════════════════════════════════════════════════════════════════
 *
 * ── Lo que habia antes, y por que se cambio ──
 *
 * Esta app tenia su propia barra (`.appmenu*`), y no era una variacion del
 * mismo diseno: era otra barra. **Sin marca a la izquierda y sin enlaces**,
 * solo un boton «MENU» en oro, en mayusculas y con borde dorado, flotando a la
 * derecha de una franja vacia. Comparado con Membresias —marca, enlaces del dia
 * a dia, y la identidad en un chip a la derecha— no se parecia en nada, y la
 * barra de arriba es lo primero que se mira al entrar: era la pieza que mas
 * hacia sentir que Campeonatos venia de otro sitio.
 *
 * Ahora usa `.navbar*`, que vive en `estilos-ecosistema.css` —el archivo
 * compartido por las cuatro webs— y salio de Membresias tal cual. Misma
 * estructura, mismas medidas, mismos estados.
 *
 * ── Lo que cambia ademas del aspecto ──
 *
 *   · **Hay marca.** Arriba a la izquierda, el escudo y «DINAMYT», y lleva al
 *     inicio del rol. Antes no habia forma de volver al panel sin abrir el menu.
 *   · **Hay enlaces.** Los del dia a dia se ven en la barra a partir de 860 px
 *     y siguen estando dentro del panel en el telefono, donde el menu es la
 *     unica navegacion que hay.
 *   · **La identidad es el boton del menu**, con su inicial, su nombre de pila
 *     y las tres rayas — en vez de la palabra «MENU».
 *   · La barra es `sticky` y no `fixed`, asi que ya no hace falta reservarle
 *     alto en el `body` (`has-appmenu`): el contenido no queda tapado solo.
 *
 * ── Donde NO sale ──
 *
 * En `/login` y en el tatami, que son pantallas inmersivas con su propia barra.
 * Eso no cambia.
 */

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

/**
 * La inicial dentro de un circulo, en el hueco donde Membresias pone la foto.
 *
 * Aqui no hay fotos —Campeonatos no guarda avatares—, pero el chip tiene que
 * pesar lo mismo en la barra o el boton se ve descolgado. Son exactamente los
 * numeros del respaldo de `Avatar` en Membresias (fondo elevado, borde dorado
 * apagado, letra en oro), para que el chip se vea el mismo con y sin foto.
 */
function Inicial({ nombre, size = 24 }: { nombre: string; size?: number }) {
  const letra = (nombre || "?").trim().charAt(0).toUpperCase() || "?";
  return (
    <span
      aria-hidden
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 800,
        fontSize: size * 0.38,
        background: "var(--bg-elevated)",
        border: "1.5px solid var(--gold-dim)",
        color: "var(--gold)",
        flexShrink: 0,
      }}
    >
      {letra}
    </span>
  );
}

interface SesionUser {
  nombre?: string;
  rol?: "admin" | "juez" | "maestro";
}

/** Un enlace de la barra. `principal` = además se ve arriba en pantalla ancha. */
interface Enlace {
  href: string;
  clave: ClaveTexto;
  principal: boolean;
}

export default function AppMenu() {
  const pathname = usePathname();
  const router = useRouter();
  const { t, idioma, setIdioma } = useI18n();
  const [user, setUser] = useState<SesionUser | null>(null);
  const [open, setOpen] = useState(false);
  // Arranca en "sistema" (igual que el servidor) y se sincroniza al montar:
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
    // La cuenta la hace `alternarModo` mirando el DOM, no este `tema`: el
    // estado arranca en "sistema" y se sincroniza en un efecto, asi que una
    // pulsacion temprana calculaba sobre un valor viejo y aplicaba **el modo
    // que ya estaba**. Se veia como «tuve que darle dos veces».
    const nuevo = alternarModo();
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

  /**
   * Que la PAGINA sepa que hay barra.
   *
   * Las pantallas publicas —campeonatos, la ficha de un campeonato, los
   * resultados— llevan la marca en su propia cabecera, porque se abren sin
   * entrar y ahi la barra no sale. Pero un maestro con la sesion abierta las ve
   * CON barra, y entonces «DINAMYT Campeonatos» salia dos veces, una encima de
   * la otra.
   *
   * Con esta marca en el `<body>`, esas cabeceras esconden su copia por CSS
   * (`.solo-sin-barra`, en el archivo compartido). Se hace asi y no leyendo la
   * sesion en cada pagina porque leerla obliga a un efecto —el servidor no ve
   * `localStorage`— y eso pinta la marca y la quita un instante despues.
   */
  useEffect(() => {
    if (typeof document === 'undefined') return;
    if (visible) document.body.dataset.barra = 'si';
    else delete document.body.dataset.barra;
    return () => {
      delete document.body.dataset.barra;
    };
  }, [visible]);

  if (!visible || !user) return null;

  const inicio = user.rol === "admin" ? "/admin" : user.rol === "maestro" ? "/maestro" : "/juez";
  const rolLabel =
    user.rol === "admin" ? t("rol.admin")
    : user.rol === "maestro" ? t("rol.maestro")
    : t("rol.juez");

  const nombre = user.nombre || t("menu.sesion");
  const primerNombre = nombre.trim().split(/\s+/)[0];

  const enlaces: Enlace[] = [
    { href: inicio, clave: "menu.inicio", principal: true },
    { href: "/campeonatos", clave: "menu.campeonatos", principal: true },
    { href: "/pantalla", clave: "menu.pantallaPublica", principal: true },
  ];

  /** Si esta ruta es la que se está mirando. Igual que en Membresías. */
  const activo = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  function ir(ruta: string) {
    setOpen(false);
    router.push(ruta);
  }

  return (
    <header ref={ref} className="navbar">
      <div className="navbar-inner">
        {/* La marca lleva al inicio del rol. Antes no existía, y volver al
            panel desde una pantalla cualquiera obligaba a abrir el menú. */}
        <Link href={inicio} className="navbar-marca">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="DINAMYT" width={30} height={30} />
          {/* La marca del ecosistema: DINAMYT en oro + el nombre de la app.
              Estaba del color del texto —o sea negra en modo claro— mientras
              en el portal iba en oro. Ver `.marca` en `estilos-ecosistema.css`. */}
          <span className="marca">
            DINAMYT<span className="marca-app">{t("app.nombreCorto")}</span>
          </span>
        </Link>

        <nav className="navbar-links" aria-label={t("menu.navegacion")}>
          {enlaces.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="navbar-link"
              data-activo={activo(l.href)}
            >
              {t(l.clave)}
            </Link>
          ))}
        </nav>

        <div className="navbar-derecha">
          {/* El botón del menú ES la identidad: inicial, nombre de pila y las
              tres rayas. Antes ponía «MENU» en mayúsculas y el nombre no salía
              en ninguna parte hasta abrirlo. */}
          <button
            type="button"
            className="navbar-toggle"
            aria-label={open ? t("menu.cerrar") : t("menu.abrir")}
            aria-expanded={open}
            aria-haspopup="menu"
            onClick={() => setOpen((o) => !o)}
          >
            <Inicial nombre={nombre} size={24} />
            <span className="navbar-toggle-nombre">{primerNombre}</span>
            <span className="navbar-rayas" data-abierto={open} aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </button>
        </div>
      </div>

      {open && (
        <div className="navbar-panel" role="menu">
          <div className="navbar-panel-quien">
            <Inicial nombre={nombre} size={38} />
            <span className="navbar-panel-datos">
              <b>{nombre}</b>
              <span>{rolLabel}</span>
            </span>
          </div>

          {/* Todos los enlaces, no solo los que faltan: en móvil el menú es la
              única navegación que hay. En PC, los que ya se ven arriba se
              ocultan por CSS (`data-principal`). */}
          <div className="navbar-panel-nav" data-solo-principales={enlaces.every((l) => l.principal)}>
            <p className="navbar-etiqueta">{t("menu.navegacion")}</p>
            <div className="navbar-panel-links">
              {enlaces.map((l) => (
                <button
                  key={l.href}
                  type="button"
                  role="menuitem"
                  className="navbar-item"
                  data-activo={activo(l.href)}
                  data-principal={l.principal}
                  onClick={() => ir(l.href)}
                >
                  {t(l.clave)}
                </button>
              ))}
            </div>
            <div className="navbar-sep" />
          </div>

          <button type="button" role="menuitem" className="navbar-item" onClick={cambiarTema}>
            {temaEfectivo(tema) === "oscuro" ? t("menu.modoClaro") : t("menu.modoOscuro")}
          </button>

          <p className="navbar-etiqueta">{t("menu.idioma")}</p>
          <div className="navbar-idiomas" role="group" aria-label={t("menu.idioma")}>
            {IDIOMAS.map((l) => (
              <button
                key={l.codigo}
                type="button"
                className="navbar-idioma"
                data-activo={idioma === l.codigo}
                aria-pressed={idioma === l.codigo}
                onClick={() => {
                  setIdioma(l.codigo);
                  // Y a la CUENTA, como el tema. Faltaba, y era la mitad del
                  // fallo del idioma: se elegia ingles aqui, nunca llegaba a
                  // `users.locale`, y al primer `visibilitychange`
                  // `AplicarApariencia` leia `es-CO` del servidor y devolvia
                  // la pantalla a espaniol sola.
                  guardarAparienciaEnLaCuenta({
                    locale: l.codigo === "en" ? "en-US" : "es-CO",
                  });
                }}
              >
                {l.etiqueta}
              </button>
            ))}
          </div>

          <div className="navbar-sep" />

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
            */}
          <a
            href={`${PORTAL_URL}/dashboard`}
            role="menuitem"
            className="navbar-item"
            title={t("menu.ecosistemaTitulo")}
          >
            <IconoEcosistema />
            {t("menu.ecosistema")}
          </a>

          {/* ── Por qué esta separación ──
              «Ir a DINAMYT» y «Salir» hacen lo mismo desde lejos —los dos te
              sacan de esta app— pero uno te lleva a tu portal y el otro te
              cierra la sesión, y equivocarse cuesta volver a escribir la
              contraseña. */}
          <div style={{ height: 8 }} />
          <LogoutButton />
        </div>
      )}
    </header>
  );
}
