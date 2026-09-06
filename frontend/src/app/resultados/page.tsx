"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getResultadosCampeonatoAPI,
  listCampeonatosResultadosAPI,
  type ResultadoPublico,
  type ResultadosCampeonato,
} from "@/lib/api";
import Logo from "@/components/Logo";
import PublicControls from "@/components/PublicControls";
import { useI18n } from "@/lib/i18n";

interface CampeonatoOpcion {
  id: number | string; // "pub:<uuid>" si es un snapshot importado
  nombre: string;
  num_resultados: number;
}

type FiltroModalidad = "todas" | "combate" | "figuras";

// Resalta la parte del nombre que coincide con la búsqueda (para encontrarse
// rápido entre cientos de competidores).
function resaltar(nombre: string, termino: string) {
  if (!termino) return nombre;
  const idx = nombre.toLowerCase().indexOf(termino.toLowerCase());
  if (idx < 0) return nombre;
  return (
    <>
      {nombre.slice(0, idx)}
      <mark style={{ background: "var(--gold-bg)", color: "var(--gold)", padding: "0 2px", borderRadius: 3 }}>
        {nombre.slice(idx, idx + termino.length)}
      </mark>
      {nombre.slice(idx + termino.length)}
    </>
  );
}

export default function ResultadosPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [campeonatos, setCampeonatos] = useState<CampeonatoOpcion[]>([]);
  const [campId, setCampId] = useState<number | string | null>(null);
  const [data, setData] = useState<ResultadosCampeonato | null>(null);
  const [loading, setLoading] = useState(true);
  const [cargandoResultados, setCargandoResultados] = useState(false);
  const [error, setError] = useState(false);

  // Filtros
  const [busqueda, setBusqueda] = useState("");
  const [modalidad, setModalidad] = useState<FiltroModalidad>("todas");
  const [categoria, setCategoria] = useState("");
  const [tatami, setTatami] = useState("");

  // Cargar la lista de campeonatos con resultados
  useEffect(() => {
    let cancelled = false;
    queueMicrotask(async () => {
      try {
        const lista = await listCampeonatosResultadosAPI();
        if (cancelled) return;
        setCampeonatos(lista);
        if (lista.length === 1) setCampId(lista[0].id);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, []);

  // Cargar los resultados del campeonato elegido
  useEffect(() => {
    if (campId == null) { setData(null); return; }
    let cancelled = false;
    setCargandoResultados(true);
    queueMicrotask(async () => {
      try {
        const res = await getResultadosCampeonatoAPI(campId);
        if (!cancelled) setData(res);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setCargandoResultados(false);
      }
    });
    return () => { cancelled = true; };
  }, [campId]);

  const visibles = useMemo(() => {
    if (!data) return [];
    const termino = busqueda.trim().toLowerCase();
    return data.resultados.filter((r) => {
      if (modalidad === "combate" && r.tipo === "figuras") return false;
      if (modalidad === "figuras" && r.tipo !== "figuras") return false;
      if (categoria && r.nombre !== categoria) return false;
      if (tatami && String(r.tatami_numero ?? "") !== tatami) return false;
      if (termino) {
        const enParticipantes = r.participantes.some((p) => p.toLowerCase().includes(termino));
        const enNombre = r.nombre.toLowerCase().includes(termino);
        if (!enParticipantes && !enNombre) return false;
      }
      return true;
    });
  }, [data, busqueda, modalidad, categoria, tatami]);

  const hayFiltros = Boolean(busqueda || modalidad !== "todas" || categoria || tatami);

  function limpiar() {
    setBusqueda("");
    setModalidad("todas");
    setCategoria("");
    setTatami("");
  }

  return (
    <div className="resultados-page">
      <div className="resultados-header">
        <Logo className="solo-sin-barra" fontSize="1.5rem" />
        <div>
          <h1 className="resultados-titulo">{t("res.titulo")}</h1>
          <p className="resultados-sub">{t("res.sub")}</p>
        </div>
        <button className="btn btn-sm btn-ghost" onClick={() => router.push("/login")}>
          {t("res.volverInicio")}
        </button>
      </div>

      {loading ? (
        <p className="animate-shimmer resultados-msg">{t("res.cargando")}</p>
      ) : error && campeonatos.length === 0 ? (
        <p className="resultados-msg" style={{ color: "var(--red-alert)" }}>{t("res.errorConexion")}</p>
      ) : campeonatos.length === 0 ? (
        <p className="resultados-msg">{t("res.sinCampeonatos")}</p>
      ) : (
        <>
          {/* Selector de campeonato */}
          <div className="card" style={{ padding: "14px 18px" }}>
            <label className="resultados-label">{t("res.pasoCampeonato")}</label>
            {campeonatos.length === 1 ? (
              <div className="resultados-camp-unico">
                {campeonatos[0].nombre}
                <span className="badge badge-gray" style={{ marginLeft: 8 }}>
                  {t("res.nResultados", { n: campeonatos[0].num_resultados })}
                </span>
              </div>
            ) : (
              <select
                className="input"
                value={campId ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  // Los snapshots importados usan id "pub:<uuid>" (no numérico).
                  setCampId(!v ? null : v.startsWith("pub:") ? v : Number(v));
                }}
              >
                <option value="">{t("res.selecciona")}</option>
                {campeonatos.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nombre} · {t("res.nResultados", { n: c.num_resultados })}
                  </option>
                ))}
              </select>
            )}
          </div>

          {campId != null && (
            <>
              {/* Búsqueda + filtros */}
              <div className="card" style={{ padding: "14px 18px", display: "flex", flexDirection: "column", gap: 12 }}>
                <div>
                  <input
                    className="input resultados-buscar"
                    placeholder={t("res.buscar")}
                    value={busqueda}
                    onChange={(e) => setBusqueda(e.target.value)}
                    autoComplete="off"
                  />
                  <p className="resultados-nota">{t("res.buscarNota")}</p>
                </div>
                <div className="resultados-filtros">
                  <select className="input" value={modalidad} onChange={(e) => setModalidad(e.target.value as FiltroModalidad)} aria-label={t("res.filtroModalidad")}>
                    <option value="todas">{t("res.modTodas")}</option>
                    <option value="combate">{t("res.modCombate")}</option>
                    <option value="figuras">{t("res.modFiguras")}</option>
                  </select>
                  <select className="input" value={categoria} onChange={(e) => setCategoria(e.target.value)} aria-label={t("res.filtroCategoria")}>
                    <option value="">{t("res.todasCategorias")}</option>
                    {(data?.categorias || []).map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <select className="input" value={tatami} onChange={(e) => setTatami(e.target.value)} aria-label={t("res.filtroTatami")}>
                    <option value="">{t("res.todosTatamis")}</option>
                    {(data?.tatamis || []).map((n) => (
                      <option key={n} value={String(n)}>{t("res.tatami", { n })}</option>
                    ))}
                  </select>
                  {hayFiltros && (
                    <button className="btn btn-sm" onClick={limpiar}>{t("res.limpiar")}</button>
                  )}
                </div>
                {data && (
                  <span className="resultados-conteo">
                    {t("res.deTotal", { n: visibles.length, total: data.resultados.length })}
                  </span>
                )}
              </div>

              {/* Lista de resultados */}
              {cargandoResultados ? (
                <p className="animate-shimmer resultados-msg">{t("res.cargando")}</p>
              ) : !data || data.resultados.length === 0 ? (
                <div className="card resultados-vacio">{t("res.sinResultados")}</div>
              ) : visibles.length === 0 ? (
                <div className="card resultados-vacio">{t("res.sinCoincidencias")}</div>
              ) : (
                <div className="resultados-grid">
                  {visibles.map((r) => (
                    <ResultadoCard key={r.id} r={r} termino={busqueda.trim()} />
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}

      <PublicControls />

      <style>{`
        .resultados-page {
          max-width: 1100px; margin: 0 auto; padding: 20px clamp(14px, 4vw, 32px);
          display: flex; flex-direction: column; gap: 16px; min-height: 100dvh;
        }
        .resultados-header {
          display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
          padding-bottom: 12px; border-bottom: 1px solid var(--border);
        }
        .resultados-header > div { flex: 1; min-width: 0; }
        /* ── El titulo de pantalla, como en las otras tres webs ─────────────
           Estaba en ORO y con un interletrado positivo de 0.08em. Las dos cosas
           venian de Bebas Neue, la condensada que esta app usaba antes: una
           condensada necesita aire entre letras, y Archivo —que es ancha y
           ademas se usa estirada al 118%— con ese mismo valor se desparrama y
           llega al borde de su caja. Era buena parte de lo que se veia
           "ampliado y al limite".

           Y el oro: en el portal, Membresias y Academy el titulo va del color
           del TEXTO, y el oro se reserva para el antetitulo y la marca. Un oro
           que sale tambien en cada titulo deja de ser un acento.

           Los valores son los de .display (estilos-ecosistema.css) con el
           tamano de text-3xl, que es con el que se titula en el portal.

           OJO: aqui dentro NO se pueden usar comillas invertidas. Esto vive
           dentro de un template literal de JS y la primera cerraria la cadena.
        */
        .resultados-titulo {
          font-family: var(--font-display); font-size: 1.5rem;
          font-weight: 800; font-stretch: 118%; text-transform: uppercase;
          color: var(--text); letter-spacing: -0.015em; line-height: 0.98;
        }
        .resultados-sub { color: var(--text-muted); font-size: 0.9rem; margin-top: 2px; }
        .resultados-msg { text-align: center; padding: 40px 0; color: var(--text-muted); }
        .resultados-label {
          font-size: 0.8rem; font-weight: 800; text-transform: uppercase;
          letter-spacing: 0.08em; color: var(--text-muted); display: block; margin-bottom: 6px;
        }
        .resultados-camp-unico {
          padding: 10px 14px; border-radius: var(--radius-sm);
          border: 1px solid var(--gold-border); background: var(--gold-bg);
          color: var(--gold); font-weight: 700;
        }
        .resultados-buscar { font-size: 1.05rem; }
        .resultados-nota { font-size: 0.82rem; color: var(--text-dim); margin-top: 6px; }
        .resultados-filtros { display: flex; gap: 8px; flex-wrap: wrap; }
        .resultados-filtros .input { width: auto; min-width: 150px; flex: 1 1 150px; max-width: 220px; }
        .resultados-conteo { font-size: 0.85rem; color: var(--text-dim); }
        .resultados-vacio { text-align: center; padding: 32px; color: var(--text-dim); }
        .resultados-grid {
          display: grid; gap: 12px;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        }
        @media (max-width: 560px) {
          .resultados-filtros .input { max-width: none; }
        }
      `}</style>
    </div>
  );
}

function ResultadoCard({ r, termino }: { r: ResultadoPublico; termino: string }) {
  const { t } = useI18n();
  const medalla = (p?: number) => (p === 1 ? "🥇" : p === 2 ? "🥈" : p === 3 ? "🥉" : `${p ?? "-"}°`);
  const badgeClase = r.tipo === "figuras" ? "badge-chung" : "badge-hong";
  const badgeTexto = r.tipo === "figuras" ? t("res.modFiguras") : t("res.modCombate");

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 800, fontSize: "1.02rem", overflowWrap: "anywhere" }}>{r.nombre}</span>
        <span className={`badge ${badgeClase}`}>{badgeTexto}</span>
        {r.tatami_numero != null && (
          <span className="badge badge-gray">{t("res.tatami", { n: r.tatami_numero })}</span>
        )}
      </div>
      {r.descripcion && (
        <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: -4 }}>{r.descripcion}</div>
      )}

      {/* Combate (llave): podio 1/2/3 */}
      {(r.tipo === "combate") && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {(r.podio || []).map((p) => (
            <div key={p.puesto} className="res-fila" style={{
              background: p.puesto === 1 ? "var(--gold-bg)" : "var(--bg-elevated)",
              borderColor: p.puesto === 1 ? "var(--gold-border)" : "var(--border)",
            }}>
              <span className="res-medalla">{medalla(p.puesto)}</span>
              <span className="res-nombre">{resaltar(p.nombre, termino)}
                {p.club && <span className="res-club"> {p.club}</span>}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Figuras: ranking completo */}
      {r.tipo === "figuras" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {(r.ranking || []).map((item, i) => (
            <div key={`${item.nombre}-${i}`} className="res-fila" style={{
              background: item.puesto === 1 ? "var(--gold-bg)" : "var(--bg-elevated)",
              borderColor: item.puesto === 1 ? "var(--gold-border)" : "var(--border)",
            }}>
              <span className="res-medalla">{medalla(item.puesto)}</span>
              <span className="res-nombre">
                {resaltar(item.nombre, termino)}
                {item.club && <span className="res-club"> {item.club}</span>}
                {item.especial && <span className="badge badge-chung" style={{ marginLeft: 6 }}>{t("res.especial")}</span>}
                {item.empate && <span className="badge badge-gray" style={{ marginLeft: 6 }}>{t("res.empate")}</span>}
              </span>
              {item.total != null && (
                <span className="res-total">{Number(item.total).toFixed(2)}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Combate suelto: marcador y ganador */}
      {r.tipo === "combate_suelto" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {[
            { c: r.hong, color: "var(--hong-light)", win: r.ganador?.color === "hong" },
            { c: r.chung, color: "var(--chung-light)", win: r.ganador?.color === "chung" },
          ].map((lado, i) => lado.c && (
            <div key={i} className="res-fila" style={{
              background: lado.win ? "var(--gold-bg)" : "var(--bg-elevated)",
              borderColor: lado.win ? "var(--gold-border)" : "var(--border)",
            }}>
              <span className="res-medalla" style={{ color: lado.color }}>{lado.win ? "🥇" : ""}</span>
              <span className="res-nombre">{resaltar(lado.c.nombre, termino)}</span>
              <span className="res-total">{lado.c.marcador.toFixed(1)}</span>
            </div>
          ))}
          {r.ganador?.color === "empate" && (
            <div style={{ fontSize: "0.85rem", color: "var(--text-dim)", textAlign: "center" }}>{t("res.empate")}</div>
          )}
        </div>
      )}

      <style>{`
        .res-fila {
          display: flex; align-items: center; gap: 10px;
          padding: 6px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border);
        }
        .res-medalla { font-size: 1.05rem; min-width: 28px; text-align: center; flex-shrink: 0; }
        .res-nombre { flex: 1; font-weight: 700; overflow-wrap: anywhere; }
        .res-club { color: var(--text-muted); font-weight: 500; font-size: 0.85rem; }
        .res-total { font-family: var(--font-mono); font-weight: 800; color: var(--gold); flex-shrink: 0; }
      `}</style>
    </div>
  );
}
