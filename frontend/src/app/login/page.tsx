"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { abrirSesionConToken, getMeAPI, loginAPI, logoutAPI } from "@/lib/api";
import { guardarToken, guardarUsuario, limpiarSesion } from "@/lib/sesion";
import CampoContrasena from "@/components/CampoContrasena";
import Logo from "@/components/Logo";
import { IDIOMAS, useI18n } from "@/lib/i18n";
import { PORTAL_URL } from "@/lib/portal";
import { aplicarTema, getTema, type Tema } from "@/lib/theme";

/** Dónde aterriza cada rol al entrar. Lo comparten el formulario y el salto
 *  desde DINAMYT: dos copias de esto es cómo un rol acaba entrando a la
 *  pantalla de otro. */
function destinoDe(rol: string) {
  if (rol === "admin") return "/admin";
  if (rol === "maestro") return "/maestro";
  return "/juez";
}

export default function LoginPage() {
  const router = useRouter();
  const { t, idioma, setIdioma } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // Tema (sin sesión no hay menú global): arranca "dark" como el servidor y
  // se sincroniza al montar para no desajustar la hidratación.
  const [tema, setTema] = useState<Tema>("dark");
  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => { if (!cancelled) setTema(getTema()); });
    return () => { cancelled = true; };
  }, []);
  function cambiarTema() {
    const nuevo: Tema = tema === "dark" ? "light" : "dark";
    aplicarTema(nuevo);
    setTema(nuevo);
  }

  // ── Se llega aquí SALIENDO, y eso lo cambia todo ─────────────────────────
  //
  // «Salir» ya no termina en `/login` a secas. Aterrizar ahí después de cerrar
  // sesión es dejar a la persona delante de la única pantalla del sitio cuyo
  // trabajo es meter gente dentro, con el pase todavía en la URL o la cookie
  // todavía viva — y basta con que sobreviva cualquiera de las dos para que
  // aparezca de vuelta en la consola un segundo después de haber salido. Ese
  // es el «hay que pulsar Salir dos veces» que Membresías ya pagó (§5.12).
  //
  // Con `?salida` esta pantalla es un punto final, no una puerta: no canjea
  // ningún pase, dice en voz alta lo que se cerró, y si detecta que quedó
  // sesión viva la remata.
  //
  // Es un `ref` y no estado porque tiene que estar decidido ANTES de que corran
  // los efectos de abajo, y porque deja de valer en cuanto alguien empieza a
  // entrar a propósito desde aquí (ver `handleSubmit`).
  const enSalida = useRef<"portal" | "sola" | null>(
    typeof window === "undefined"
      ? null
      : (new URLSearchParams(window.location.search).get("salida") as
          | "portal"
          | "sola"
          | null),
  );
  /**
   * Lo mismo, para poder DECIRLO en pantalla sin romper la hidratación.
   *
   * `portal` = se cerraron las dos sesiones, la de aquí y la de DINAMYT.
   * `sola` = esta instalación no habla con el ecosistema: solo había una.
   */
  const [avisoSalida, setAvisoSalida] = useState<"portal" | "sola" | null>(null);
  /** Dos remates y se para: cerrar en bucle sería peor que no cerrar. */
  const remates = useRef(0);

  useEffect(() => {
    setAvisoSalida(enSalida.current);
  }, []);

  /**
   * Se salió, pero el servidor todavía reconoce la sesión: se cierra otra vez.
   *
   * El `POST /auth/logout` puede no haber salido —el backend reiniciándose, un
   * 503 de mantenimiento, un corte— y esa llamada no lanza: limpia lo local y
   * sigue. La cookie httpOnly, que solo borra el servidor, se queda viva. Aquí
   * se le pregunta a él —`GET /auth/me` es la única respuesta que vale— y si
   * contesta que sí, se le vuelve a pedir que cierre.
   *
   * El contador es el freno: si el servidor sigue sin poder cerrar, se para y
   * se enseña el formulario, que es la verdad visible más cercana a lo que la
   * persona pidió y desde donde puede volver a entrar.
   */
  useEffect(() => {
    if (!enSalida.current) return;
    let cancelado = false;
    void (async () => {
      while (!cancelado && remates.current < 2) {
        try {
          await getMeAPI();
        } catch {
          return; // El servidor ya no la reconoce: cerrada de verdad.
        }
        if (cancelado) return;
        remates.current += 1;
        await logoutAPI();
      }
    })();
    return () => { cancelado = true; };
  }, []);

  // ── El salto desde DINAMYT ────────────────────────────────────────────────
  //
  // El portal manda aquí con el pase en el FRAGMENTO (`/login#token=…`), que
  // no viaja al servidor ni queda en ningún registro. Se canjea por la cookie
  // de sesión y se entra directo: es lo que faltaba para que «Entrar a
  // Campeonatos» no acabara en este mismo formulario.
  //
  // ⚠️ El pase **no se guarda** con `guardarToken`. Ese token se manda como
  // cabecera `Authorization` en TODAS las peticiones (ver el interceptor de
  // `lib/api.ts`), y el pase es RS256 del ecosistema: el backend no lo sabe
  // leer y rechazaría cada petición, con la cookie buena ya puesta. Quien
  // autentica a partir de aquí es la cookie.
  const [saltando, setSaltando] = useState(false);
  const [avisoSalto, setAvisoSalto] = useState("");

  useEffect(() => {
    if (typeof window === "undefined") return;
    // Nadie entra por una pantalla a la que se llegó saliendo. El portal nunca
    // manda las dos cosas juntas; el cierre está aquí por si un día lo hace.
    if (enSalida.current) return;
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const pase = params.get("token");
    if (!pase) return;

    // Fuera del historial y de la barra de direcciones antes de nada: un pase
    // en la URL se comparte por captura de pantalla sin querer.
    window.history.replaceState(null, "", window.location.pathname);

    let cancelado = false;
    setSaltando(true);
    abrirSesionConToken(pase)
      .then(({ user }) => {
        if (cancelado) return;
        guardarUsuario(user);
        router.replace(destinoDe(user.rol));
      })
      .catch((err: unknown) => {
        if (cancelado) return;
        limpiarSesion();
        const respuesta = (
          err as { response?: { data?: { error?: string; motivo?: string } } }
        ).response;

        // ── Si el pase es válido pero esta consola no es para esa persona,
        //    se la DEVUELVE al portal, no se la deja aquí ──
        //
        // Dejarla en este formulario es dejarla delante de una puerta que ya
        // sabemos que no va a abrir: no tiene contraseña de aquí, y aunque la
        // tuviera no hay nada dentro para ella. Lo suyo —sus inscripciones,
        // sus resultados— vive en DINAMYT, así que allá vuelve, con el motivo
        // para que el portal se lo explique en su idioma y en su sitio.
        if (respuesta?.data?.motivo) {
          window.location.replace(
            `${PORTAL_URL}/dashboard?campeonatos=${encodeURIComponent(respuesta.data.motivo)}`,
          );
          return;
        }

        // Sin motivo es que no hubo respuesta: el servidor no contestó. Ahí sí
        // se queda aquí, porque el formulario propio puede ser la salida.
        setSaltando(false);
        setAvisoSalto(respuesta?.data?.error || t("login.errorConexion"));
      });
    return () => { cancelado = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // Quien teclea su contraseña aquí ya no está saliendo: está entrando. Sin
    // levantar la marca, el remate de arriba cerraría la sesión recién abierta.
    enSalida.current = null;
    setAvisoSalida(null);
    setError("");
    setLoading(true);
    try {
      const data = await loginAPI(email, password);
      // La sesión ya viene en la cookie httpOnly de la respuesta; aquí solo se
      // guarda el token en memoria (socket y descargas) y el perfil cacheado.
      guardarToken(data.token);
      guardarUsuario(data.user);
      router.push(destinoDe(data.user.rol));
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: string } } };
      setError(axiosErr.response?.data?.error || t("login.errorConexion"));
    } finally {
      setLoading(false);
    }
  }


  return (
    <div className="login-page">
      {/* Fondo con gradiente */}
      <div className="login-bg" aria-hidden="true" />

      <div className="login-wrapper animate-slide">
        {/* Logo central */}
        <div className="login-logo">
          <Logo stacked fontSize="clamp(2rem, 6vw, 2.8rem)" />
          <p className="login-tagline">{t("login.tagline")}</p>
          <p className="login-sub">Global Hapkido Association · GHA</p>
        </div>

        {/* Volviendo de DINAMYT: mientras se canjea el pase no se enseña el
            formulario, o parece que el salto no funcionó y la persona escribe
            su contraseña encima. */}
        {saltando && (
          <p className="login-card-desc" style={{ textAlign: "center" }} role="status">
            {t("comun.cargando")}
          </p>
        )}

        {/* Se acaba de salir: se dice QUÉ se cerró. Sin esta línea, salir y
            aparecer en el formulario de entrar se lee como que no funcionó —
            que es exactamente la duda que traía el botón viejo. */}
        {avisoSalida && (
          <p
            className="login-card-desc"
            role="status"
            style={{ textAlign: "center", maxWidth: 560, margin: "0 auto" }}
          >
            {t(avisoSalida === "portal" ? "login.sesionCerradaDinamyt" : "login.sesionCerrada")}
          </p>
        )}

        {/* Y si el pase no abre esta consola —un alumno, un club sin plan—, se
            dice por qué AQUÍ arriba, no dentro del formulario: lo que tiene
            que hacer no es escribir una contraseña, es volver al portal. */}
        {avisoSalto && (
          <div
            className="login-error animate-fade"
            role="alert"
            style={{ maxWidth: 560, margin: "0 auto 1rem" }}
          >
            {avisoSalto}{" "}
            <a
              href={PORTAL_URL}
              style={{ color: "var(--gold)", textDecoration: "underline" }}
            >
              Volver a DINAMYT
            </a>
          </div>
        )}

        {/* GRID: Pantalla Publica | Separator | Login */}
        <div className="login-grid" hidden={saltando}>

          {/* ── PANTALLA PUBLICA ── */}
          <div className="login-card login-card-public animate-fade">
            <div className="login-card-icon" aria-hidden="true">📺</div>
            <h2 className="login-card-title">{t("login.publica.titulo")}</h2>
            <p className="login-card-desc">
              {t("login.publica.desc1")}<br />
              {t("login.publica.desc2")}
            </p>
            <button
              type="button"
              className="btn btn-lg login-btn-public"
              onClick={() => router.push("/pantalla")}
              style={{
                width: "100%",
                fontWeight: 800,
                fontSize: "1rem",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
              }}
              id="public-access-btn"
            >
              {t("login.publica.boton")}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => router.push("/resultados")}
              style={{ width: "100%", borderColor: "var(--gold-border)", color: "var(--gold)", fontWeight: 700 }}
              id="public-results-btn"
            >
              {t("res.verResultados")}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => router.push("/campeonatos")}
              style={{ width: "100%", borderColor: "var(--gold-border)", color: "var(--gold)", fontWeight: 700 }}
              id="public-champs-btn"
            >
              {t("pub.camp.boton")}
            </button>
            <p className="login-card-note">{t("login.publica.nota")}</p>
          </div>

          {/* ── SEPARADOR ── */}
          <div className="login-separator" aria-hidden="true">
            <div className="login-separator-line" />
            <span className="login-separator-label">{t("login.o")}</span>
            <div className="login-separator-line" />
          </div>

          {/* ── LOGIN JUECES / ADMIN ── */}
          <div className="login-card login-card-auth animate-fade" style={{ animationDelay: "0.1s" }}>
            <div className="login-card-icon" aria-hidden="true">🏅</div>
            <h2 className="login-card-title">{t("login.jueces.titulo")}</h2>
            <p className="login-card-desc">
              {t("login.jueces.desc")}
            </p>

            <form onSubmit={handleSubmit} className="login-form">
              <div className="login-field">
                <label className="login-label" htmlFor="login-email">{t("login.correo")}</label>
                <input
                  type="email"
                  className="input"
                  placeholder="juez@dinamyt.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  id="login-email"
                />
              </div>

              <div className="login-field">
                <label className="login-label" htmlFor="login-password">{t("login.contrasena")}</label>
                <CampoContrasena
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  id="login-password"
                />
              </div>

              {error && (
                <div className="login-error animate-fade" role="alert">
                  {error}
                </div>
              )}

              <button
                type="submit"
                className="btn btn-primary btn-lg"
                style={{ width: "100%" }}
                disabled={loading}
                id="login-submit"
              >
                {loading ? t("login.verificando") : t("login.entrar")}
              </button>
            </form>
          </div>

        </div>

      </div>

      {/* Aquí no hay menú global (se oculta en /login): selector propio de
          idioma + toggle de tema */}
      <div className="login-idiomas" role="group" aria-label={t("menu.idioma")}>
        {IDIOMAS.map((l) => (
          <button
            key={l.codigo}
            type="button"
            className="login-idioma-btn"
            data-activo={idioma === l.codigo}
            aria-pressed={idioma === l.codigo}
            onClick={() => setIdioma(l.codigo)}
          >
            {l.etiqueta}
          </button>
        ))}
        <button
          type="button"
          className="login-idioma-btn"
          onClick={cambiarTema}
          title={tema === "dark" ? t("menu.modoClaro") : t("menu.modoOscuro")}
        >
          {tema === "dark" ? "☀️" : "🌙"}
        </button>
      </div>

      <p className="login-footer">{t("login.footer")}</p>

      <style>{`
        .login-page {
          min-height: 100dvh;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 20px;
          position: relative;
          overflow: hidden;
        }

        .login-bg {
          position: absolute;
          inset: 0;
          background:
            radial-gradient(ellipse 80% 50% at 20% 30%, rgba(240,184,0,0.06) 0%, transparent 60%),
            radial-gradient(ellipse 60% 40% at 80% 70%, rgba(0,85,255,0.05) 0%, transparent 60%);
          pointer-events: none;
          z-index: 0;
        }

        .login-wrapper {
          position: relative;
          z-index: 1;
          width: 100%;
          max-width: 900px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 32px;
        }

        .login-logo {
          text-align: center;
        }

        .login-tagline {
          font-family: var(--font-body);
          font-size: 1.05rem;
          font-weight: 600;
          color: var(--text-muted);
          letter-spacing: 0.04em;
          margin-top: 6px;
        }

        .login-sub {
          font-size: 0.85rem;
          color: var(--text-dim);
          text-transform: uppercase;
          letter-spacing: 0.12em;
          margin-top: 2px;
        }

        .login-grid {
          display: grid;
          grid-template-columns: 1fr auto 1fr;
          gap: 0;
          width: 100%;
          align-items: start;
        }

        .login-card {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          padding: 32px 28px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .login-card-public {
          border-color: var(--chung-border);
        }

        /* CTA de pantalla pública: navy sólido en oscuro; en claro ese navy
           chocaría con el texto azul del tema, así que usa el tinte chung */
        .login-btn-public {
          background: linear-gradient(135deg, #1c2e5e 0%, #0d1d42 100%);
          border: 2px solid var(--chung-border);
          color: var(--chung-light);
        }

        html[data-theme="light"] .login-btn-public {
          background: var(--chung-bg-strong);
        }

        .login-card-auth {
          border-color: var(--gold-border);
        }

        .login-card-icon {
          font-size: 2.2rem;
          line-height: 1;
        }

        .login-card-title {
          font-size: 1.3rem;
          font-weight: 800;
          color: var(--text);
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }

        .login-card-desc {
          font-size: 0.92rem;
          color: var(--text-muted);
          line-height: 1.5;
        }

        .login-card-note {
          font-size: 0.82rem;
          color: var(--text-dim);
          text-align: center;
          margin-top: auto;
        }

        .login-public-form {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .login-separator {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 0 24px;
          gap: 8px;
          padding-top: 80px;
        }

        .login-separator-line {
          flex: 1;
          width: 1px;
          background: var(--border);
          min-height: 60px;
        }

        .login-separator-label {
          font-size: 0.875rem;
          font-weight: 800;
          color: var(--text-dim);
          letter-spacing: 0.1em;
          padding: 8px 0;
        }

        .login-form {
          display: flex;
          flex-direction: column;
          gap: 14px;
        }

        .login-field {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .login-label {
          font-size: 0.82rem;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.10em;
          color: var(--text-muted);
        }

        .login-error {
          background: rgba(255,68,68,0.10);
          border: 1px solid rgba(255,68,68,0.30);
          border-radius: var(--radius-sm);
          padding: 10px 14px;
          color: var(--red-alert);
          font-size: 0.92rem;
          text-align: center;
        }

        .login-idiomas {
          position: relative;
          z-index: 1;
          margin-top: 24px;
          display: flex;
          gap: 8px;
          justify-content: center;
        }

        .login-idioma-btn {
          padding: 7px 18px;
          background: transparent;
          border: 1.5px solid var(--border-light);
          border-radius: var(--radius-sm);
          color: var(--text-muted);
          font: inherit;
          font-weight: 600;
          font-size: 0.9rem;
          cursor: pointer;
          transition: var(--transition);
        }

        .login-idioma-btn:hover,
        .login-idioma-btn:focus-visible {
          background: var(--bg-elevated);
          color: var(--text);
          outline: none;
        }

        .login-idioma-btn[data-activo="true"] {
          background: var(--gold-bg);
          border-color: var(--gold-border);
          color: var(--gold);
          font-weight: 800;
        }

        .login-footer {
          position: relative;
          z-index: 1;
          margin-top: 20px;
          color: var(--text-dim);
          font-size: 0.8rem;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          text-align: center;
        }

        /* Responsive */
        @media (max-width: 700px) {
          .login-grid {
            grid-template-columns: 1fr;
            gap: 0;
          }
          .login-separator {
            flex-direction: row;
            padding: 16px 0;
          }
          .login-separator-line {
            flex: 1;
            width: auto;
            height: 1px;
            min-height: auto;
          }
        }
      `}</style>
    </div>
  );
}
