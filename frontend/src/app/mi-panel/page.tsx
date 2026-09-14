"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  miPanelAPI,
  reclamarFichaAPI,
  type MiCampeonato,
  type MiPanel,
  type UserData,
} from "@/lib/api";
import { Cargando } from "@/components/Cargando";
import { destinoDe } from "@/lib/destino";
import { useI18n } from "@/lib/i18n";
import { obtenerUsuario } from "@/lib/sesion";
import { aviso } from "@/lib/toast";

/**
 * ════════════════════════════════════════════════════════════════════════════
 * EL PANEL DEL COMPETIDOR — F3 de PLAN-CAMPEONATOS
 * ════════════════════════════════════════════════════════════════════════════
 *
 * La primera pantalla de Campeonatos que no es de un campeonato, sino de una
 * persona. Hasta F3 el alumno ni siquiera entraba: el login lo devolvía al
 * portal con `sin_consola`.
 *
 * Todo sale de UNA petición (`GET /api/mi/panel`), que filtra por la cuenta de
 * la sesión: aquí no se manda ningún id.
 *
 * ── Sin ficha, lo primero es encontrarla ──
 *
 * La ficha existe antes que la cuenta (D5): quien compitió sin DINAMYT la
 * reclama con su documento y su fecha de nacimiento. Por eso, sin fichas, la
 * pantalla ES ese formulario; con fichas, queda plegado para una segunda.
 *
 * ── «Sin confirmar» se dice, no se esconde ──
 *
 * Lo que sale de una llave sin enlace se encontró por nombre (opción B del
 * plan). Se enseña con su marca y con la cuenta de cuántos son: esconderlo
 * dejaba vacío todo el historial anterior al 13 de septiembre de 2026, y
 * enseñarlo sin marca era afirmar lo que no se sabe.
 */

const MEDALLA: Record<string, string> = { oro: "🥇", plata: "🥈", bronce: "🥉" };

/** Una fecha CIVIL (AAAA-MM-DD) en el idioma de la pantalla, sin zona que la mueva. */
function fechaCivil(iso: string | null, idioma: string) {
  if (!iso) return null;
  const [a, m, d] = iso.split("-").map(Number);
  if (!a || !m || !d) return iso;
  return new Date(a, m - 1, d).toLocaleDateString(idioma === "en" ? "en-US" : "es-CO", {
    day: "numeric", month: "short", year: "numeric",
  });
}

export default function MiPanelPage() {
  const router = useRouter();
  const { t, idioma } = useI18n();
  const [user, setUser] = useState<UserData | null>(null);
  const [panel, setPanel] = useState<MiPanel | null>(null);
  const [error, setError] = useState(false);

  const [documento, setDocumento] = useState("");
  const [nacimiento, setNacimiento] = useState("");
  const [reclamando, setReclamando] = useState(false);
  const [otraAbierta, setOtraAbierta] = useState(false);

  const cargar = useCallback(async () => {
    setError(false);
    try {
      setPanel(await miPanelAPI());
    } catch (err) {
      const estado = (err as { response?: { status?: number } }).response?.status;
      if (estado === 401 || estado === 422) {
        router.replace("/login");
        return;
      }
      setError(true);
    }
  }, [router]);

  useEffect(() => {
    const u = obtenerUsuario<UserData>();
    if (!u) { router.replace("/login"); return; }
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setUser(u);
      void cargar();
    });
    return () => { cancelled = true; };
  }, [cargar, router]);

  async function reclamar(e: React.FormEvent) {
    e.preventDefault();
    if (reclamando || !documento.trim() || !nacimiento) return;
    setReclamando(true);
    try {
      await reclamarFichaAPI(documento.trim(), nacimiento);
      setDocumento("");
      setNacimiento("");
      setOtraAbierta(false);
      await cargar();
      aviso(t("mi.reclamar.ok"), "ok");
    } catch (err) {
      // El servidor ya distingue lo que hay que decir: no aparece, es de otra
      // cuenta, o demasiados intentos.
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      aviso(m || t("mi.reclamar.error"), "error");
    } finally {
      setReclamando(false);
    }
  }

  if (!user) return null;

  if (error) {
    return (
      <div className="mi-panel">
        <div className="card" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span>{t("mi.error")}</span>
          <button className="btn btn-sm" onClick={() => void cargar()}>{t("mi.reintentar")}</button>
        </div>
      </div>
    );
  }

  if (!panel) return <Cargando mensaje={t("comun.cargando")} />;

  const { persona, fichas, estadisticas: st } = panel;
  const opera = user.rol !== "competidor";

  const lugar = (c: MiCampeonato) => [c.lugar, c.ciudad, c.pais].filter(Boolean).join(" · ");
  const fechas = (c: MiCampeonato) => {
    const inicio = fechaCivil(c.fecha_inicio, idioma);
    const fin = fechaCivil(c.fecha_fin, idioma);
    if (!inicio) return t("mi.sinFecha");
    return fin && fin !== inicio ? `${inicio} – ${fin}` : inicio;
  };

  const formularioReclamar = (
    <form onSubmit={reclamar} className="mi-reclamar">
      <label className="mi-campo">
        <span className="microetiqueta">{t("mi.reclamar.documento")}</span>
        <input
          className="input"
          inputMode="numeric"
          autoComplete="off"
          maxLength={20}
          value={documento}
          onChange={(e) => setDocumento(e.target.value)}
        />
      </label>
      <label className="mi-campo">
        <span className="microetiqueta">{t("mi.reclamar.fecha")}</span>
        <input
          className="input"
          type="date"
          value={nacimiento}
          onChange={(e) => setNacimiento(e.target.value)}
        />
      </label>
      <button
        type="submit"
        className="btn btn-primary"
        disabled={reclamando || !documento.trim() || !nacimiento}
      >
        {reclamando ? t("mi.reclamar.buscando") : t("mi.reclamar.boton")}
      </button>
    </form>
  );

  return (
    <div className="mi-panel">
      <header className="mi-cabecera">
        <div>
          <h1 className="display" style={{ fontSize: "1.5rem" }}>{t("mi.titulo")}</h1>
          <p className="muted" style={{ fontSize: "0.85rem", marginTop: 2 }}>{persona.nombre}</p>
        </div>
        {/* Quien además opera tiene su consola: el panel no es su única casa. */}
        {opera && (
          <button className="btn btn-sm" onClick={() => router.push(destinoDe(user.rol))}>
            {t("mi.irConsola")}
          </button>
        )}
      </header>

      {!persona.con_cuenta ? (
        <div className="card mi-nota">{t("mi.sinCuenta")}</div>
      ) : fichas.length === 0 ? (
        <section className="card">
          <div className="card-title">{t("mi.reclamar.titulo")}</div>
          <p className="muted mi-ayuda">{t("mi.reclamar.ayuda")}</p>
          {formularioReclamar}
        </section>
      ) : (
        <>
          {/* ── Tu ficha ── */}
          <section className="card">
            <div className="card-title">
              {fichas.length > 1 ? t("mi.fichas.titulo") : t("mi.ficha.titulo")}
            </div>
            <div className="mi-lista">
              {fichas.map((f) => (
                <div key={f.uid} className="mi-fila">
                  <div style={{ fontWeight: 700, overflowWrap: "anywhere" }}>{f.nombre_completo}</div>
                  <div className="mi-datos">
                    {[f.club, f.cinturon, f.documento].filter(Boolean).join(" · ")}
                  </div>
                </div>
              ))}
            </div>
            {panel.maestro && (
              <p className="mi-datos" style={{ marginTop: 10 }}>
                {t("mi.maestro")}:{" "}
                <strong style={{ color: "var(--text)" }}>{panel.maestro.nombre}</strong>
                {panel.maestro.club ? ` · ${panel.maestro.club}` : ""}
              </p>
            )}
            {otraAbierta ? (
              <div style={{ marginTop: 12 }}>{formularioReclamar}</div>
            ) : (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ marginTop: 10 }}
                onClick={() => setOtraAbierta(true)}
              >
                {t("mi.reclamar.otra")}
              </button>
            )}
          </section>

          {/* ── Tus números ── */}
          <section className="card">
            <div className="card-title">{t("mi.stats.titulo")}</div>
            <div className="mi-numeros">
              <Numero valor={st.combates} etiqueta={t("mi.stats.combates")} />
              <Numero valor={st.victorias} etiqueta={t("mi.stats.victorias")} />
              <Numero valor={st.derrotas} etiqueta={t("mi.stats.derrotas")} />
              <Numero valor={st.medallas.oro} etiqueta={`${MEDALLA.oro} ${t("mi.stats.oro")}`} />
              <Numero valor={st.medallas.plata} etiqueta={`${MEDALLA.plata} ${t("mi.stats.plata")}`} />
              <Numero valor={st.medallas.bronce} etiqueta={`${MEDALLA.bronce} ${t("mi.stats.bronce")}`} />
            </div>
            {(st.por_anio.length > 0 || st.por_modalidad.length > 0) && (
              <div className="mi-desgloses">
                {st.por_anio.length > 0 && (
                  <div>
                    <div className="microetiqueta">{t("mi.stats.porAnio")}</div>
                    {st.por_anio.map((f) => (
                      <div key={f.anio} className="mi-desglose">
                        <span>{f.anio}</span>
                        <span>{MEDALLA.oro} {f.oro} · {MEDALLA.plata} {f.plata} · {MEDALLA.bronce} {f.bronce}</span>
                      </div>
                    ))}
                  </div>
                )}
                {st.por_modalidad.length > 0 && (
                  <div>
                    <div className="microetiqueta">{t("mi.stats.porModalidad")}</div>
                    {st.por_modalidad.map((f) => (
                      <div key={f.tipo} className="mi-desglose">
                        <span>{f.tipo === "figuras" ? t("mi.tipo.figuras") : t("mi.tipo.combate")}</span>
                        <span>{MEDALLA.oro} {f.oro} · {MEDALLA.plata} {f.plata} · {MEDALLA.bronce} {f.bronce}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {st.sin_confirmar > 0 && (
              <p className="mi-datos" style={{ marginTop: 10 }}>
                {t("mi.stats.sinConfirmar", { n: st.sin_confirmar })}
              </p>
            )}
          </section>

          {/* ── Próximos ── */}
          <section className="card">
            <div className="card-title">{t("mi.proximos.titulo")}</div>
            {panel.proximos.length === 0 ? (
              <p className="muted mi-ayuda">{t("mi.proximos.vacio")}</p>
            ) : (
              <div className="mi-lista">
                {panel.proximos.map((c) => (
                  <div key={c.id} className="mi-fila">
                    <div style={{ fontWeight: 700, overflowWrap: "anywhere" }}>{c.nombre}</div>
                    <div className="mi-datos">{[fechas(c), lugar(c)].filter(Boolean).join(" · ")}</div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Inscripciones ── */}
          <section className="card">
            <div className="card-title">{t("mi.insc.titulo")}</div>
            {panel.inscripciones.length === 0 ? (
              <p className="muted mi-ayuda">{t("mi.insc.vacio")}</p>
            ) : (
              <div className="mi-lista">
                {panel.inscripciones.map((i) => (
                  <div key={i.id} className="mi-fila">
                    <div className="mi-fila-cabeza">
                      <span style={{ fontWeight: 700, overflowWrap: "anywhere" }}>{i.campeonato.nombre}</span>
                      <span className={`badge ${
                        i.estado === "aceptada" ? "badge-green"
                        : i.estado === "rechazada" ? "badge-hong"
                        : "badge-gray"
                      }`}>
                        {i.estado === "aceptada" ? t("mi.insc.aceptada")
                          : i.estado === "rechazada" ? t("mi.insc.rechazada")
                          : t("mi.insc.pendiente")}
                      </span>
                    </div>
                    <div className="mi-datos">
                      {[fechas(i.campeonato), i.modalidades.join(", "), i.grupo_cinturon]
                        .filter(Boolean).join(" · ")}
                    </div>
                    {i.maestro && (
                      <div className="mi-datos">{t("mi.insc.porMaestro", { nombre: i.maestro.nombre })}</div>
                    )}
                    {i.estado === "rechazada" && i.motivo_rechazo && (
                      <div className="mi-datos" style={{ color: "var(--text)" }}>
                        {t("mi.insc.motivo")} {i.motivo_rechazo}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Resultados ── */}
          <section className="card">
            <div className="card-title">{t("mi.res.titulo")}</div>
            {panel.resultados.length === 0 ? (
              <p className="muted mi-ayuda">{t("mi.res.vacio")}</p>
            ) : (
              <div className="mi-lista">
                {panel.resultados.map((r) => (
                  <div
                    key={`${r.campeonato.id}-${r.tipo}-${r.categoria}-${r.puesto}`}
                    className="mi-fila"
                  >
                    <div className="mi-fila-cabeza">
                      <span style={{ fontWeight: 700, overflowWrap: "anywhere" }}>
                        {r.medalla ? `${MEDALLA[r.medalla]} ` : ""}
                        {t("mi.res.puesto", { n: r.puesto })} · {r.categoria}
                      </span>
                      {!r.confirmado && (
                        <span className="badge badge-gray" title={t("mi.res.sinConfirmarTitle")}>
                          {t("mi.res.sinConfirmar")}
                        </span>
                      )}
                    </div>
                    <div className="mi-datos">
                      {[
                        r.tipo === "figuras" ? t("mi.tipo.figuras") : t("mi.tipo.combate"),
                        r.campeonato.nombre,
                        fechas(r.campeonato),
                      ].join(" · ")}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      <style>{`
        .mi-panel {
          max-width: 760px; margin: 0 auto; padding: 20px clamp(16px, 4vw, 32px);
          display: flex; flex-direction: column; gap: 14px;
        }
        .mi-cabecera {
          display: flex; justify-content: space-between; align-items: center;
          gap: 10px; flex-wrap: wrap;
          padding-bottom: 14px; border-bottom: 1px solid var(--border);
        }
        .mi-ayuda { font-size: 0.9rem; margin: 0 0 12px; }
        .mi-nota { color: var(--text-muted); font-size: 0.92rem; }
        .mi-reclamar {
          display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap;
        }
        .mi-campo { display: flex; flex-direction: column; gap: 4px; flex: 1 1 180px; }
        .mi-lista { display: flex; flex-direction: column; gap: 8px; }
        .mi-fila {
          padding: 10px 12px; border-radius: var(--radius-sm);
          background: var(--bg-elevated); border: 1px solid var(--border);
          display: flex; flex-direction: column; gap: 3px; min-width: 0;
        }
        .mi-fila-cabeza {
          display: flex; justify-content: space-between; align-items: center;
          gap: 8px; flex-wrap: wrap;
        }
        .mi-datos { color: var(--text-muted); font-size: 0.84rem; overflow-wrap: anywhere; }
        .mi-numeros {
          display: grid; grid-template-columns: repeat(auto-fit, minmax(96px, 1fr)); gap: 8px;
        }
        .mi-numero {
          padding: 10px; border-radius: var(--radius-sm); text-align: center;
          background: var(--bg-elevated); border: 1px solid var(--border);
        }
        .mi-numero strong { display: block; font-size: 1.4rem; color: var(--text); }
        .mi-numero span { font-size: 0.78rem; color: var(--text-muted); }
        .mi-desgloses {
          display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 14px; margin-top: 14px;
        }
        .mi-desglose {
          display: flex; justify-content: space-between; gap: 8px;
          font-size: 0.86rem; padding: 4px 0; border-bottom: 1px solid var(--border);
        }
      `}</style>
    </div>
  );
}

function Numero({ valor, etiqueta }: { valor: number; etiqueta: string }) {
  return (
    <div className="mi-numero">
      <strong>{valor}</strong>
      <span>{etiqueta}</span>
    </div>
  );
}
