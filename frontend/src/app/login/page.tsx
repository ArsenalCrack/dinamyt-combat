"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { abrirSesionConToken, getMeAPI, loginAPI, logoutAPI } from "@/lib/api";
import { guardarToken, guardarUsuario, limpiarSesion } from "@/lib/sesion";
import CampoContrasena from "@/components/CampoContrasena";
import PublicControls from "@/components/PublicControls";
import { useI18n } from "@/lib/i18n";
import { PORTAL_URL } from "@/lib/portal";
import { LIM } from "@/lib/limites";
import { aplicarAparienciaDelPase } from "@/lib/theme";

/**
 * ════════════════════════════════════════════════════════════════════════════
 * LA PANTALLA DE ENTRAR — la misma que el portal, Membresías y Academy
 * ════════════════════════════════════════════════════════════════════════════
 *
 * ── Lo que había, y por qué no valía ─────────────────────────────────────────
 *
 * Una rejilla de 900 px con DOS tarjetas del mismo tamaño —«Pantalla pública»
 * a la izquierda, «Jueces y admin» a la derecha— separadas por una raya
 * vertical con una «O» en medio, y noventa líneas de `<style>` propias dentro
 * del archivo. No se parecía a ninguna de las otras tres webs, que son todas
 * la misma tarjeta de 380 px con el logo dentro (`.eco-login*`, en el archivo
 * compartido). Y lo peor: **de las dos mitades, la que de verdad es esta
 * pantalla —el formulario— ocupaba la mitad de un lado.**
 *
 * Ahora es la caja de siempre: logo, antetítulo, título con la segunda palabra
 * en oro, los dos campos y el botón. Lo público no desaparece —se ve sin
 * cuenta y es lo que busca quien llega desde un cartel— pero pasa a ser lo que
 * es: tres enlaces debajo del formulario, detrás de una raya.
 *
 * ── El logo lleva a DINAMYT ──────────────────────────────────────────────────
 *
 * Como en Membresías y en Academy: ninguna app del ecosistema es un callejón
 * sin salida. Antes el logo de aquí no era un enlace a nada, así que quien
 * aterrizaba en este formulario sin cuenta de Campeonatos no tenía a dónde ir.
 *
 * ── Y el tema y el idioma son el globo 🌐 ────────────────────────────────────
 *
 * El mismo `PublicControls` de las pantallas públicas y el mismo `.pubctl` que
 * el portal usa en su login. Antes esta pantalla tenía su propia fila de
 * botones de idioma abajo del todo (`.login-idiomas`), que era el cuarto sitio
 * distinto donde se elegía lo mismo.
 */

/** Dónde aterriza cada rol al entrar. Lo comparten el formulario y el salto
 *  desde DINAMYT: dos copias de esto es cómo un rol acaba entrando a la
 *  pantalla de otro. */
function destinoDe(rol: string) {
  if (rol === "admin") return "/admin";
  if (rol === "maestro") return "/maestro";
  return "/juez";
}

/** Lo que tarda el aviso de «cerraste tu sesión» en irse solo. Ver abajo. */
const MS_AVISO_SALIDA = 9000;

export default function LoginPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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

  /**
   * El aviso se enseña… y se va.
   *
   * ── Qué pasaba ──
   *
   * Se ponía al montar y no lo quitaba nadie. Quien salía se quedaba con
   * «Cerraste tu sesión» clavado encima del formulario para siempre: al minuto
   * ya no es un aviso, es parte del diseño, y encima contradice lo que la
   * persona está haciendo, que es volver a entrar. Recargando volvía, porque el
   * `?salida=` seguía en la barra.
   *
   * ── Las tres cosas que lo cierran ──
   *
   *   · Un reloj: a los nueve segundos ya se leyó.
   *   · La dirección, que se limpia **navegando** (`router.replace`) y no con
   *     `history.replaceState`. Ese atajo es el que dejó a Membresías con el
   *     router mudo dos veces seguidas —el estado del historial guarda dentro
   *     la URL, y tocarlo a mano las descuadra—, y `?salida` sí es parte de la
   *     ruta que Next gestiona. Navegar es lo único que Next entiende.
   *   · Y teclear (ver `alTeclear`): quien escribe su contraseña ya no está
   *     saliendo.
   *
   * El remate de abajo no se entera de nada de esto: mira `enSalida.current`,
   * que es un `ref` y no la barra de direcciones.
   */
  useEffect(() => {
    if (!enSalida.current) return;
    setAvisoSalida(enSalida.current);
    const reloj = setTimeout(() => setAvisoSalida(null), MS_AVISO_SALIDA);
    router.replace("/login");
    return () => clearTimeout(reloj);
  }, [router]);

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
        // El tema y el idioma que eligio esta persona en el portal viajan
        // DENTRO del pase, y este es el unico momento en que Campeonatos lo ve:
        // despues la sesion es una cookie y el JWT ya no se puede leer.
        // Sin esto, `localStorage` es por origen y la eleccion se queda en
        // dinamyt.org.
        aplicarAparienciaDelPase(pase);
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

  /**
   * Teclear es entrar, y entrar no es salir.
   *
   * Levanta la marca en cuanto alguien toca un campo: sin esto el remate de
   * arriba cerraría la sesión que este formulario está a punto de abrir, y el
   * aviso de «cerraste tu sesión» seguiría encima de la contraseña que se está
   * escribiendo.
   */
  function alTeclear() {
    if (!enSalida.current && !avisoSalida) return;
    enSalida.current = null;
    setAvisoSalida(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    alTeclear();
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
    <main className="eco-login">
      <form onSubmit={handleSubmit} className="card eco-login-caja">
        {/* El logo lleva al portal, la convención del ecosistema: ninguna app
            es un callejón sin salida. Solo cuando hay portal al que ir: en el
            modo local —el del día del evento, sin internet— se queda como
            estaba, porque el enlace no llevaría a ninguna parte. */}
        {PORTAL_URL ? (
          <a href={PORTAL_URL} title={t("login.volverAlPortal")}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="DINAMYT" className="eco-login-logo" />
          </a>
        ) : (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img src="/logo.png" alt="DINAMYT" className="eco-login-logo" />
        )}

        <p className="eyebrow eco-login-eyebrow">{t("login.eyebrow")}</p>
        <h1 className="display eco-login-titulo">
          {t("login.titulo")} <span className="acento">{t("login.tituloAcento")}</span>
        </h1>
        <p className="muted eco-login-subtitulo">
          {saltando ? t("comun.cargando") : t("login.subtitulo")}
        </p>

        {/* Volviendo de DINAMYT: mientras se canjea el pase no se enseña el
            formulario, o parece que el salto no funcionó y la persona escribe
            su contraseña encima. */}
        {!saltando && (
          <>
            <label className="muted eco-login-etiqueta" htmlFor="login-email">
              {t("login.correo")}
            </label>
            <input
              id="login-email"
              type="email"
              className="input"
              style={{ margin: "0.3rem 0 0.9rem" }}
              maxLength={LIM.correo}
              placeholder="juez@dinamyt.com"
              value={email}
              onChange={(e) => {
                alTeclear();
                setEmail(e.target.value);
              }}
              required
              autoComplete="username"
            />

            <label className="muted eco-login-etiqueta" htmlFor="login-password">
              {t("login.contrasena")}
            </label>
            {/* Sin `maxLength` a propósito: es el único campo de contraseña que
                no fija una nueva, sino que comprueba la que ya existe. Recortar
                aquí dejaría fuera a quien tenga una más larga de lo que hoy se
                permite crear. */}
            {/* El margen va en `style` y no en una clase: `CampoContrasena`
                reparte el estilo —los márgenes al envoltorio, el resto al
                campo— porque el ojo se centra respecto al envoltorio, y su
                `className` sustituye a `.input` en vez de sumarse. */}
            <CampoContrasena
              id="login-password"
              style={{ margin: "0.3rem 0 1.1rem" }}
              placeholder="••••••••"
              value={password}
              onChange={(e) => {
                alTeclear();
                setPassword(e.target.value);
              }}
              required
              autoComplete="current-password"
            />

            {/* Se acaba de salir: se dice QUÉ se cerró, y se deja de decir a los
                nueve segundos. Sin esta línea, salir y aparecer en el
                formulario de entrar se lee como que no funcionó — que es
                exactamente la duda que traía el botón viejo. */}
            {avisoSalida && !error && (
              <p
                className="muted"
                role="status"
                style={{ marginBottom: "0.8rem", fontSize: "0.85rem" }}
              >
                {t(
                  avisoSalida === "portal"
                    ? "login.sesionCerradaDinamyt"
                    : "login.sesionCerrada",
                )}
              </p>
            )}

            {error && (
              <p
                className="msg-error"
                role="alert"
                style={{ marginBottom: "0.8rem", fontSize: "0.85rem" }}
              >
                {error}
              </p>
            )}

            {/* Y si el pase no abre esta consola —un alumno, un club sin plan—,
                se dice por qué: lo que tiene que hacer no es escribir una
                contraseña, es volver al portal. */}
            {avisoSalto && (
              <p
                className="msg-error"
                role="alert"
                style={{ marginBottom: "0.8rem", fontSize: "0.85rem" }}
              >
                {avisoSalto}{" "}
                <a href={PORTAL_URL} style={{ color: "var(--gold)" }}>
                  {t("login.volverAlPortal")}
                </a>
              </p>
            )}

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: "100%" }}
              disabled={loading}
              id="login-submit"
            >
              {loading ? t("login.verificando") : t("login.entrar")}
            </button>

            {/* ── Lo público, que no pide cuenta ──────────────────────────
                Estaba en una tarjeta del mismo tamaño que el formulario, a su
                izquierda, y esta pantalla parecía dos pantallas. Es lo que
                busca quien llega desde un cartel o un grupo de WhatsApp, así
                que no se esconde — pero va debajo y en outline, porque quien
                abre `/login` casi siempre viene a entrar. */}
            <div className="eco-login-sep" aria-hidden="true">
              <span />
              <em>{t("login.o")}</em>
              <span />
            </div>

            <p className="muted" style={{ fontSize: "0.85rem", marginBottom: "0.7rem" }}>
              {t("login.publica.intro")}
            </p>

            <div className="eco-login-publico">
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => router.push("/pantalla")}
                id="public-access-btn"
              >
                {t("login.publica.boton")}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => router.push("/campeonatos")}
                id="public-champs-btn"
              >
                {t("pub.camp.boton")}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => router.push("/resultados")}
                id="public-results-btn"
              >
                {t("res.verResultados")}
              </button>
            </div>
          </>
        )}
      </form>

      {/* Sin sesión no hay barra: el tema y el idioma viven en el globo, el
          mismo de las pantallas públicas y el mismo que el portal usa en su
          login. */}
      <PublicControls />
    </main>
  );
}
