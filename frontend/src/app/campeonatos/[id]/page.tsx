"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getCampeonatoPublicoAPI,
  type CampeonatoPublicoDetalle,
  type EstadoCampeonato,
} from "@/lib/api";
import Logo from "@/components/Logo";
import PublicControls from "@/components/PublicControls";
import { useI18n, type ClaveTexto, type Idioma } from "@/lib/i18n";

type Apartado = "info" | "inscritos" | "jueces";

/** Roles de tatami con traducción; cualquier otro se muestra tal cual. El
 *  orden de las claves es el de la mesa: central primero, luego esquinas. */
const CLAVE_ROL: Record<string, ClaveTexto> = {
  arbitro: "rol.arbitro",
  j1: "rol.j1",
  j2: "rol.j2",
  j3: "rol.j3",
  j4: "rol.j4",
};
const ORDEN_ROL = Object.keys(CLAVE_ROL);

/** El badge del estado usa el mismo código de color que el resto del panel. */
function claseEstado(estado: EstadoCampeonato): string {
  if (estado === "en_curso") return "badge badge-gold";
  if (estado === "finalizado") return "badge badge-green";
  return "badge badge-gray";
}

/** Fecha larga ("sábado, 12 de julio de 2025"); rango si hay fecha fin. */
function fechaLarga(inicio: string | null, fin: string | null, idioma: Idioma): string | null {
  // Mediodía y no medianoche: evita que el desfase horario corra el día.
  const fmt = (s: string, conDia: boolean) => {
    const d = new Date(`${s}T12:00:00`);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleDateString(idioma, {
      ...(conDia ? { weekday: "long" as const } : {}),
      day: "numeric", month: "long", year: "numeric",
    });
  };
  if (inicio && fin && inicio !== fin) return `${fmt(inicio, true)} → ${fmt(fin, false)}`;
  if (inicio) return fmt(inicio, true);
  if (fin) return fmt(fin, true);
  return null;
}

export default function CampeonatoPublicoFichaPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const campId = Number(params.id);
  const { t, idioma } = useI18n();

  const [detalle, setDetalle] = useState<CampeonatoPublicoDetalle | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(false);
  const [apartado, setApartado] = useState<Apartado>("info");

  // Filtros de inscritos: plegados, para que al abrir la ficha se vea la
  // lista completa y no una barra de controles.
  const [filtrosAbiertos, setFiltrosAbiertos] = useState(false);
  const [busqueda, setBusqueda] = useState("");
  const [clubFiltro, setClubFiltro] = useState("");
  const [modalidadFiltro, setModalidadFiltro] = useState("");

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(async () => {
      try {
        // Un id que no es número no llega a pedirse: se trata como no encontrado.
        if (!Number.isInteger(campId)) throw new Error("id inválido");
        const d = await getCampeonatoPublicoAPI(campId);
        if (!cancelled) setDetalle(d);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setCargando(false);
      }
    });
    return () => { cancelled = true; };
  }, [campId]);

  const competidores = useMemo(() => detalle?.competidores ?? [], [detalle]);

  // Modalidades y clubes con su número de inscritos: se derivan de la lista
  // aceptada (el backend no los devuelve contados). De más a menos gente.
  const { modalidades, clubes } = useMemo(() => {
    const porModalidad = new Map<string, number>();
    const porClub = new Map<string, number>();
    competidores.forEach((c) => {
      c.modalidades.forEach((m) => porModalidad.set(m, (porModalidad.get(m) || 0) + 1));
      if (c.club) porClub.set(c.club, (porClub.get(c.club) || 0) + 1);
    });
    const ordenar = (m: Map<string, number>) =>
      [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    return { modalidades: ordenar(porModalidad), clubes: ordenar(porClub) };
  }, [competidores]);

  const inscritosVisibles = useMemo(() => {
    const term = busqueda.trim().toLowerCase();
    return competidores.filter((c) => {
      if (clubFiltro && c.club !== clubFiltro) return false;
      if (modalidadFiltro && !c.modalidades.includes(modalidadFiltro)) return false;
      if (term && !`${c.nombre} ${c.club}`.toLowerCase().includes(term)) return false;
      return true;
    });
  }, [competidores, busqueda, clubFiltro, modalidadFiltro]);

  const hayFiltro = !!(busqueda.trim() || clubFiltro || modalidadFiltro);

  // Jueces por tatami, en el orden de los tatamis; al final los que quedaron
  // sin tatami (por si una asignación perdió su tatami).
  const juecesPorTatami = useMemo(() => {
    if (!detalle) return [];
    // Dentro de cada tatami, el orden de la mesa (central → esquinas).
    const porRol = (a: { rol_tatami: string }, b: { rol_tatami: string }) => {
      const ia = ORDEN_ROL.indexOf(a.rol_tatami);
      const ib = ORDEN_ROL.indexOf(b.rol_tatami);
      return (ia < 0 ? ORDEN_ROL.length : ia) - (ib < 0 ? ORDEN_ROL.length : ib);
    };
    const grupos = detalle.tatamis.map((tat) => ({
      numero: tat.numero as number | null,
      id: tat.id as number | null,
      activo: tat.activo,
      jueces: detalle.jueces.filter((j) => j.tatami_numero === tat.numero).sort(porRol),
    }));
    const huerfanos = detalle.jueces.filter((j) => j.tatami_numero == null).sort(porRol);
    if (huerfanos.length > 0) {
      grupos.push({ numero: null, id: null, activo: true, jueces: huerfanos });
    }
    return grupos;
  }, [detalle]);

  const nCompetidores = (n: number) =>
    n === 1 ? t("pub.camp.unCompetidor") : t("pub.camp.nCompetidores", { n });

  if (cargando) {
    return (
      <div className="ficha-page">
        <p className="ficha-msg animate-shimmer">{t("pub.camp.cargandoFicha")}</p>
        <PublicControls />
        <style>{ESTILOS}</style>
      </div>
    );
  }

  if (error || !detalle) {
    return (
      <div className="ficha-page">
        <p className="ficha-msg" style={{ color: "var(--red-alert)" }}>
          {t("pub.camp.noEncontrado")}
        </p>
        <div style={{ textAlign: "center" }}>
          <button className="btn" onClick={() => router.push("/campeonatos")}>
            {t("pub.camp.volverLista")}
          </button>
        </div>
        <PublicControls />
        <style>{ESTILOS}</style>
      </div>
    );
  }

  const c = detalle.campeonato;
  const fecha = fechaLarga(c.fecha_inicio, c.fecha_fin, idioma);
  const ubicacion = [c.lugar, c.ciudad, c.pais].filter(Boolean).join(", ");
  const enCurso = c.estado === "en_curso";

  const resumen: { valor: number; etiqueta: string }[] = [
    { valor: competidores.length, etiqueta: t("pub.camp.inscritos") },
    { valor: clubes.length, etiqueta: t("pub.camp.clubes") },
    { valor: detalle.jueces.length, etiqueta: t("pub.camp.jueces") },
    { valor: detalle.tatamis.length, etiqueta: t("pub.camp.tatamis") },
  ];

  return (
    <div className="ficha-page">
      <div className="ficha-topbar">
        <Logo className="solo-sin-barra" fontSize="1.5rem" />
        <button className="btn btn-sm btn-ghost" onClick={() => router.push("/campeonatos")}>
          {t("pub.camp.volverLista")}
        </button>
      </div>

      {/* Cabecera: nombre, estado, cuándo y dónde — todo de un vistazo */}
      <header className="card ficha-hero animate-fade">
        <div className="ficha-hero-top">
          <h1 className="ficha-titulo">{c.nombre}</h1>
          <span className={claseEstado(c.estado)}>
            {enCurso ? "● " : ""}{t(`camp.estado.${c.estado}` as ClaveTexto)}
          </span>
        </div>
        {c.descripcion && <p className="ficha-desc">{c.descripcion}</p>}
        <div className="ficha-meta">
          <span>📅 {fecha ?? t("pub.camp.fechaPorConfirmar")}</span>
          {ubicacion && <span>📍 {ubicacion}</span>}
        </div>
        <div className="ficha-resumen">
          {resumen.map((r) => (
            <div key={r.etiqueta} className="ficha-stat">
              <span className="ficha-stat-num">{r.valor}</span>
              <span className="ficha-stat-lbl">{r.etiqueta}</span>
            </div>
          ))}
        </div>
      </header>

      {/* Apartados: la información se reparte en tres vistas limpias */}
      <nav className="ficha-tabs" aria-label={t("pub.camp.titulo")}>
        {([
          ["info", t("pub.camp.tab.info")],
          ["inscritos", `${t("pub.camp.inscritos")} (${competidores.length})`],
          ["jueces", `${t("pub.camp.jueces")} (${detalle.jueces.length})`],
        ] as [Apartado, string][]).map(([id, etiqueta]) => (
          <button
            key={id}
            type="button"
            className="ficha-tab"
            data-activo={apartado === id}
            aria-pressed={apartado === id}
            onClick={() => setApartado(id)}
          >
            {etiqueta}
          </button>
        ))}
      </nav>

      {/* ══════════════ INFORMACIÓN ══════════════ */}
      {apartado === "info" && (
        <div className="animate-fade ficha-secciones">
          <section className="card">
            <div className="card-title">{t("pub.camp.datosEvento")}</div>
            <dl className="ficha-datos">
              {([
                [t("pub.camp.fecha"), fecha ?? t("pub.camp.fechaPorConfirmar")],
                [t("pub.camp.lugar"), c.lugar || t("pub.camp.sinDato")],
                [t("pub.camp.ciudad"), c.ciudad || t("pub.camp.sinDato")],
                [t("pub.camp.pais"), c.pais || t("pub.camp.sinDato")],
                [t("pub.camp.estado"), t(`camp.estado.${c.estado}` as ClaveTexto)],
              ] as [string, string][]).map(([etiqueta, valor]) => (
                <div key={etiqueta} className="ficha-dato">
                  <dt>{etiqueta}</dt>
                  <dd>{valor}</dd>
                </div>
              ))}
            </dl>
            <div className="ficha-aviso">{t("pub.camp.contactaMaestro")}</div>
          </section>

          {modalidades.length > 0 && (
            <section className="card">
              <div className="card-title">{t("pub.camp.modalidades")}</div>
              <div className="ficha-chips">
                {modalidades.map(([m, n]) => (
                  <span key={m} className="badge badge-gold" title={nCompetidores(n)}>
                    {m} · {n}
                  </span>
                ))}
              </div>
            </section>
          )}

          <section className="card">
            <div className="card-title">
              {t("pub.camp.clubesAsistentes")} ({clubes.length})
            </div>
            {clubes.length === 0 ? (
              <p className="ficha-vacio">{t("pub.camp.sinInscritos")}</p>
            ) : (
              <ul className="ficha-lista">
                {clubes.map(([club, n]) => (
                  <li key={club} className="ficha-fila">
                    <span className="ficha-fila-nombre">{club}</span>
                    <span className="badge badge-gray">{nCompetidores(n)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card">
            <div className="card-title">
              {t("pub.camp.tatamis")} ({detalle.tatamis.length})
            </div>
            {detalle.tatamis.length === 0 ? (
              <p className="ficha-vacio">{t("pub.camp.sinTatamis")}</p>
            ) : (
              <div className="ficha-tatamis">
                {/* "tat" y no "t": no hacerle sombra a la función de traducción */}
                {detalle.tatamis.map((tat) => (
                  <div key={tat.id} className="ficha-tatami" data-inactivo={!tat.activo}>
                    <span className="ficha-tatami-num">{tat.numero}</span>
                    <span className="ficha-tatami-lbl">{t("camp.tatami")}</span>
                    {!tat.activo && (
                      <span className="badge badge-gray">{t("pub.camp.tatamiInactivo")}</span>
                    )}
                    {/* La pantalla del tatami solo tiene sentido con el evento
                        en curso: antes no hay nada que proyectar. */}
                    {enCurso && tat.activo && (
                      <button
                        className="btn btn-sm"
                        onClick={() => router.push(`/tatami/${tat.id}?rol=pantalla`)}
                      >
                        {t("pub.camp.verPantallaTatami")}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {/* ══════════════ INSCRITOS ══════════════ */}
      {apartado === "inscritos" && (
        <section className="card animate-fade">
          <div className="ficha-inscritos-head">
            <div className="card-title" style={{ marginBottom: 0 }}>
              {t("pub.camp.inscritos")} ({competidores.length})
            </div>
            {competidores.length > 0 && (
              <button
                type="button"
                className="btn btn-sm"
                aria-expanded={filtrosAbiertos}
                onClick={() => setFiltrosAbiertos((v) => !v)}
              >
                {filtrosAbiertos ? t("pub.camp.filtrosCerrar") : t("pub.camp.filtrosAbrir")}
              </button>
            )}
          </div>

          {filtrosAbiertos && (
            <div className="ficha-filtros animate-slide">
              <input
                className="input"
                placeholder={t("pub.camp.buscar")}
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                style={{ flex: "1 1 180px", minWidth: 0 }}
              />
              <select
                className="input"
                value={clubFiltro}
                onChange={(e) => setClubFiltro(e.target.value)}
                aria-label={t("pub.camp.todosClubes")}
                style={{ width: "auto", minWidth: 150 }}
              >
                <option value="">{t("pub.camp.todosClubes")}</option>
                {detalle.clubes.map((cl) => <option key={cl} value={cl}>{cl}</option>)}
              </select>
              <select
                className="input"
                value={modalidadFiltro}
                onChange={(e) => setModalidadFiltro(e.target.value)}
                aria-label={t("pub.camp.todasModalidades")}
                style={{ width: "auto", minWidth: 150 }}
              >
                <option value="">{t("pub.camp.todasModalidades")}</option>
                {modalidades.map(([m]) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          )}

          {hayFiltro && (
            <p className="ficha-conteo">
              {t("pub.camp.mostrando", {
                n: inscritosVisibles.length, total: competidores.length,
              })}
            </p>
          )}

          {competidores.length === 0 ? (
            <p className="ficha-vacio">{t("pub.camp.sinInscritos")}</p>
          ) : inscritosVisibles.length === 0 ? (
            <p className="ficha-vacio">{t("pub.camp.sinCoincidencias")}</p>
          ) : (
            <ul className="ficha-lista">
              {inscritosVisibles.map((a, i) => (
                <li key={`${a.nombre}-${i}`} className="ficha-fila ficha-fila-insc">
                  <span className="ficha-fila-nombre">{a.nombre}</span>
                  <span className="ficha-fila-club">{a.club || t("pub.camp.sinClub")}</span>
                  <span className="ficha-chips">
                    {a.modalidades.map((m) => (
                      <span key={m} className="badge badge-gray">{m}</span>
                    ))}
                    {a.modalidades.length === 0 && (
                      <span className="ficha-vacio-inline">{t("pub.camp.sinModalidades")}</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* ══════════════ JUECES ══════════════ */}
      {apartado === "jueces" && (
        <div className="animate-fade ficha-secciones">
          {detalle.jueces.length === 0 ? (
            <section className="card">
              <p className="ficha-vacio">{t("pub.camp.sinJueces")}</p>
            </section>
          ) : (
            juecesPorTatami.map((g) => (
              <section key={g.numero ?? "sin-tatami"} className="card">
                <div className="card-title">
                  {g.numero != null
                    ? `${t("camp.tatami")} ${g.numero}`
                    : t("pub.camp.sinTatami")}
                  {" "}({g.jueces.length})
                </div>
                {g.jueces.length === 0 ? (
                  <p className="ficha-vacio">{t("pub.camp.sinJueces")}</p>
                ) : (
                  <ul className="ficha-lista">
                    {g.jueces.map((j, i) => (
                      <li key={`${j.nombre}-${i}`} className="ficha-fila">
                        <span className="ficha-fila-nombre">{j.nombre}</span>
                        <span className="badge badge-chung">
                          {CLAVE_ROL[j.rol_tatami]
                            ? t(CLAVE_ROL[j.rol_tatami])
                            : j.rol_tatami.toUpperCase()}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            ))
          )}
        </div>
      )}

      <PublicControls />
      <style>{ESTILOS}</style>
    </div>
  );
}

const ESTILOS = `
  .ficha-page {
    max-width: 1100px; margin: 0 auto; padding: 20px clamp(14px, 4vw, 32px);
    display: flex; flex-direction: column; gap: 16px; min-height: 100dvh;
  }
  .ficha-topbar {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap;
  }
  .ficha-msg { text-align: center; padding: 40px 0; color: var(--text-muted); }
  .ficha-hero { display: flex; flex-direction: column; gap: 10px; }
  .ficha-hero-top {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  }
  .ficha-titulo {
    font-family: var(--font-display); font-size: 1.5rem;
    font-weight: 800; font-stretch: 118%; text-transform: uppercase;
    color: var(--text); letter-spacing: -0.015em; line-height: 0.98;
    overflow-wrap: anywhere; margin: 0;
  }
  .ficha-desc { color: var(--text-muted); font-size: 0.95rem; margin: 0; }
  .ficha-meta {
    display: flex; gap: 16px; flex-wrap: wrap;
    font-size: 0.92rem; color: var(--text);
  }
  .ficha-resumen {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
    gap: 10px; margin-top: 4px;
  }
  .ficha-stat {
    display: flex; flex-direction: column; align-items: center; gap: 2px;
    padding: 10px 6px; border: 1px solid var(--border);
    border-radius: var(--radius-sm); background: var(--bg-elevated);
  }
  .ficha-stat-num {
    font-family: var(--font-display); font-size: 1.6rem; line-height: 1;
    color: var(--gold);
  }
  .ficha-stat-lbl {
    font-size: 0.75rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-muted); text-align: center;
  }
  .ficha-tabs {
    display: flex; gap: 6px; flex-wrap: wrap;
    border-bottom: 1px solid var(--border); padding-bottom: 8px;
  }
  .ficha-tab {
    padding: 8px 16px; border: 1px solid transparent; border-radius: var(--radius-sm);
    background: transparent; color: var(--text-muted); font: inherit;
    font-weight: 700; font-size: 0.92rem; cursor: pointer; transition: var(--transition);
  }
  .ficha-tab:hover, .ficha-tab:focus-visible {
    color: var(--text); background: var(--bg-elevated); outline: none;
  }
  .ficha-tab[data-activo="true"] {
    background: var(--gold-bg); border-color: var(--gold-border);
    color: var(--gold); font-weight: 800;
  }
  .ficha-secciones { display: flex; flex-direction: column; gap: 12px; }
  .ficha-datos {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 10px; margin: 0;
  }
  .ficha-dato {
    padding: 10px 12px; border: 1px solid var(--border);
    border-radius: var(--radius-sm); min-width: 0;
  }
  .ficha-dato dt {
    font-size: 0.72rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-muted); margin-bottom: 2px;
  }
  .ficha-dato dd {
    margin: 0; font-size: 0.95rem; font-weight: 600; overflow-wrap: anywhere;
  }
  .ficha-aviso {
    margin-top: 12px; padding: 8px 12px; border-radius: var(--radius-sm);
    background: var(--gold-bg); border: 1px solid var(--gold-border);
    color: var(--gold); font-weight: 700; font-size: 0.9rem;
  }
  .ficha-chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .ficha-lista { display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 0; list-style: none; }
  .ficha-fila {
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px; flex-wrap: wrap;
    padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  }
  .ficha-fila-insc {
    display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) auto;
    align-items: center;
  }
  .ficha-fila-nombre { font-weight: 700; overflow-wrap: anywhere; min-width: 0; }
  .ficha-fila-club { color: var(--text-muted); font-size: 0.88rem; overflow-wrap: anywhere; }
  .ficha-vacio { color: var(--text-dim); font-size: 0.9rem; margin: 0; padding: 8px 0; }
  .ficha-vacio-inline { color: var(--text-dim); font-size: 0.8rem; }
  .ficha-inscritos-head {
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px; flex-wrap: wrap; margin-bottom: 10px;
  }
  .ficha-filtros { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
  .ficha-conteo { color: var(--text-muted); font-size: 0.85rem; margin: 0 0 8px; }
  .ficha-tatamis {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px;
  }
  .ficha-tatami {
    display: flex; flex-direction: column; align-items: center; gap: 4px;
    padding: 12px 10px; border: 1px solid var(--chung-border);
    border-radius: var(--radius-sm); background: var(--chung-bg);
  }
  .ficha-tatami[data-inactivo="true"] {
    border-color: var(--border); background: transparent; opacity: 0.6;
  }
  .ficha-tatami-num {
    font-family: var(--font-display); font-size: 1.8rem; line-height: 1;
    color: var(--chung-light);
  }
  .ficha-tatami-lbl {
    font-size: 0.75rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-muted);
  }
  @media (max-width: 560px) {
    .ficha-fila-insc { grid-template-columns: 1fr; }
    .ficha-filtros .input { flex: 1 1 100% !important; width: 100% !important; }
  }
`;
