"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  generarLlavesAPI,
  getCampeonatoAPI,
  getConfigCategoriasAPI,
  getSeccionesPreviewAPI,
  saveConfigCategoriasAPI,
  GRUPOS_CINTURON,
  type CategoriaConfigItem,
  type ConfigCategorias,
  type ModalidadConfigData,
  type SeccionPreview,
} from "@/lib/api";
import { useConfirmDialog } from "@/components/ConfirmDialog";
import { useI18n } from "@/lib/i18n";
import { aviso } from "@/lib/toast";
import { Cargando } from '@/components/Cargando';

type Paso = "config" | "preview";

interface ResultadoGeneracion {
  message: string;
  creadas: { clave: string; nombre: string; competidores: number }[];
  omitidas: { clave: string; nombre: string; motivo: string }[];
  avisos: string[];
}

export default function GenerarLlavesPage() {
  const router = useRouter();
  const { t } = useI18n();
  const params = useParams();
  const campId = Number(params.id);

  const [campNombre, setCampNombre] = useState("");
  const [paso, setPaso] = useState<Paso>("config");
  const [config, setConfig] = useState<ConfigCategorias | null>(null);
  const [configGuardada, setConfigGuardada] = useState(false);
  const [guardando, setGuardando] = useState(false);

  const [preview, setPreview] = useState<{
    secciones: SeccionPreview[];
    avisos: string[];
    total_inscripciones: number;
  } | null>(null);
  const [cargandoPreview, setCargandoPreview] = useState(false);
  const [verVacias, setVerVacias] = useState(false);
  const [seccionAbierta, setSeccionAbierta] = useState<string | null>(null);

  const [reemplazar, setReemplazar] = useState(false);
  const [asignarTatamis, setAsignarTatamis] = useState(false);
  const [generando, setGenerando] = useState(false);
  const [resultado, setResultado] = useState<ResultadoGeneracion | null>(null);

  const { pedirConfirmacion, dialogo } = useConfirmDialog();

  useEffect(() => {
    const saved = localStorage.getItem("dinamyt_user");
    if (!saved || JSON.parse(saved).rol !== "admin") {
      router.replace("/login");
      return;
    }
    let cancelled = false;
    queueMicrotask(async () => {
      try {
        const [c, cfg] = await Promise.all([
          getCampeonatoAPI(campId),
          getConfigCategoriasAPI(campId),
        ]);
        if (cancelled) return;
        setCampNombre(c.nombre);
        setConfig(cfg.config);
        setConfigGuardada(cfg.guardada);
      } catch {
        if (!cancelled) router.replace("/admin");
      }
    });
    return () => { cancelled = true; };
  }, [campId, router]);

  /** Avisa del resultado de una acción con la nube flotante (ver lib/toast). */
  function flash(texto: string, tipo: "ok" | "error" = "ok") {
    aviso(texto, tipo);
  }

  // ── Mutadores de config (inmutables) ──
  function setModalidad(idx: number, nueva: ModalidadConfigData) {
    if (!config) return;
    const modalidades = config.modalidades.map((m, i) => (i === idx ? nueva : m));
    setConfig({ ...config, modalidades });
  }

  function setLista(
    idx: number,
    campo: "cinturon" | "edad" | "peso",
    lista: CategoriaConfigItem[]
  ) {
    if (!config) return;
    const m = config.modalidades[idx];
    setModalidad(idx, {
      ...m,
      categorias: { ...m.categorias, [campo]: lista },
    });
  }

  async function handleGuardarConfig(irAPreview = false) {
    if (!config) return;
    setGuardando(true);
    try {
      await saveConfigCategoriasAPI(campId, config);
      setConfigGuardada(true);
      flash(t("gen.configGuardada"));
      if (irAPreview) {
        setPaso("preview");
        await cargarPreview();
      }
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("gen.errorConfig"), "error");
    } finally {
      setGuardando(false);
    }
  }

  const cargarPreview = useCallback(async () => {
    setCargandoPreview(true);
    try {
      const data = await getSeccionesPreviewAPI(campId);
      setPreview(data);
    } catch {
      flash(t("gen.errorPreview"), "error");
    } finally {
      setCargandoPreview(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campId]);

  function handleGenerar() {
    const conGente = (preview?.secciones || []).filter((s) => s.competidores.length >= 2);
    pedirConfirmacion({
      titulo: t("gen.confirm.titulo"),
      mensaje: t("gen.confirm.mensaje", {
        n: conGente.length,
        destino: asignarTatamis ? t("gen.confirm.tatamis") : t("gen.confirm.pool"),
        resorteo: reemplazar ? t("gen.confirm.resorteo") : "",
      }),
      tipo: "advertencia",
      confirmLabel: t("gen.confirm.generar"),
      onConfirm: async () => {
        setGenerando(true);
        setResultado(null);
        try {
          const res = await generarLlavesAPI(campId, {
            reemplazar,
            asignar_tatamis: asignarTatamis,
          });
          setResultado(res);
          flash(res.message, "ok");
          await cargarPreview();
        } catch (err) {
          const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
          flash(m || t("gen.errorGenerar"), "error");
        } finally {
          setGenerando(false);
        }
      },
    });
  }

  if (!config) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        <Cargando />
      </div>
    );
  }

  const seccionesVisibles = (preview?.secciones || []).filter(
    (s) => verVacias || s.competidores.length > 0
  );

  return (
    <div className="genllaves-page">
      <div style={{ marginBottom: 16 }}>
        <button className="btn btn-outline btn-sm" onClick={() => router.push(`/admin/campeonato/${campId}`)}
          style={{ marginBottom: 8 }}>
          {t("ins.volver")}
        </button>
        <h1 className="display" style={{ fontSize: "1.5rem", overflowWrap: "anywhere" }}>
          {t("gen.titulo")} {campNombre || "..."}
        </h1>
        <p className="text-muted" style={{ fontSize: "0.92rem" }}>
          {t("gen.desc")}
        </p>
      </div>

      {dialogo}

      {/* Pasos */}
      <div className="seg" role="tablist" aria-label={t("gen.pasoAria")} style={{ marginBottom: 14 }}>
        <button
          type="button" role="tab" aria-selected={paso === "config"}
          className={`seg-btn ${paso === "config" ? "seg-on" : ""}`}
          onClick={() => setPaso("config")}
        >
          {t("gen.paso1")}
        </button>
        <button
          type="button" role="tab" aria-selected={paso === "preview"}
          className={`seg-btn ${paso === "preview" ? "seg-on" : ""}`}
          onClick={() => { setPaso("preview"); void cargarPreview(); }}
        >
          {t("gen.paso2")}
        </button>
      </div>

      {/* ══════════ PASO 1: CONFIG ══════════ */}
      {paso === "config" && (
        <div className="animate-fade" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {!configGuardada && (
            <div className="card" style={{ padding: "10px 14px", fontSize: "0.88rem", color: "var(--text-muted)" }}>
              {t("gen.sugerida")}
            </div>
          )}
          {config.modalidades.map((m, idx) => (
            <EditorModalidad
              key={m.nombre}
              modalidad={m}
              onChange={(nueva) => setModalidad(idx, nueva)}
              onLista={(campo, lista) => setLista(idx, campo, lista)}
            />
          ))}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-primary" disabled={guardando} onClick={() => handleGuardarConfig(true)}>
              {guardando ? t("comp.guardando") : t("gen.guardarVer")}
            </button>
            <button className="btn" disabled={guardando} onClick={() => handleGuardarConfig(false)}>
              {t("gen.soloGuardar")}
            </button>
          </div>
        </div>
      )}

      {/* ══════════ PASO 2: PREVIEW + GENERAR ══════════ */}
      {paso === "preview" && (
        <div className="animate-fade" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {cargandoPreview ? (
            <div className="card" style={{ textAlign: "center", padding: 28, color: "var(--text-dim)" }}>
              {t("gen.calculando")}
            </div>
          ) : !preview ? (
            <div className="card" style={{ textAlign: "center", padding: 28, color: "var(--text-dim)" }}>
              <button className="btn btn-primary btn-sm" onClick={() => void cargarPreview()}>
                {t("gen.calcular")}
              </button>
            </div>
          ) : (
            <>
              <div className="card" style={{ padding: "12px 16px", display: "flex", gap: 18, flexWrap: "wrap", fontSize: "0.9rem" }}>
                <span><strong>{preview.total_inscripciones}</strong> {t("gen.inscritos")}</span>
                <span>
                  <strong>{preview.secciones.filter((s) => s.competidores.length > 0).length}</strong> {t("gen.seccionesCon")}
                </span>
                <span>
                  <strong style={{ color: "var(--green)" }}>
                    {preview.secciones.filter((s) => s.competidores.length >= 2).length}
                  </strong> {t("gen.listasPara")}
                </span>
                {preview.avisos.length > 0 && (
                  <span style={{ color: "var(--orange)" }}>
                    <strong>{preview.avisos.length}</strong> {t("gen.avisos")}
                  </span>
                )}
                <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, cursor: "pointer", color: "var(--text-muted)" }}>
                  <input type="checkbox" checked={verVacias} onChange={(e) => setVerVacias(e.target.checked)} />
                  {t("gen.verVacias")}
                </label>
              </div>

              {preview.avisos.length > 0 && (
                <div className="card" style={{ padding: "12px 16px", borderColor: "rgba(255,150,0,0.35)" }}>
                  <div style={{ fontWeight: 800, color: "var(--orange)", fontSize: "0.9rem", marginBottom: 6 }}>
                    {t("gen.sinSeccion")}
                  </div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: "0.875rem", color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: 3 }}>
                    {preview.avisos.map((a, i) => <li key={i}>{a}</li>)}
                  </ul>
                  <p style={{ fontSize: "0.84rem", color: "var(--text-dim)", margin: "8px 0 0" }}>
                    {t("gen.sinSeccionNota")}
                  </p>
                </div>
              )}

              {seccionesVisibles.length === 0 ? (
                <div className="card" style={{ textAlign: "center", padding: 28, color: "var(--text-dim)" }}>
                  {t("gen.ningunaSeccion")}
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {seccionesVisibles.map((s) => (
                    <SeccionCard
                      key={s.clave}
                      seccion={s}
                      abierta={seccionAbierta === s.clave}
                      onToggle={() => setSeccionAbierta(seccionAbierta === s.clave ? null : s.clave)}
                    />
                  ))}
                </div>
              )}

              {/* Generación */}
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10, padding: 16 }}>
                <div className="card-title" style={{ marginBottom: 0 }}>{t("gen.generarTitulo")}</div>
                <label style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: "0.9rem", cursor: "pointer" }}>
                  <input type="checkbox" checked={asignarTatamis} onChange={(e) => setAsignarTatamis(e.target.checked)} style={{ marginTop: 3 }} />
                  <span>
                    <strong>{t("gen.repartir")}</strong>
                    <span style={{ color: "var(--text-muted)" }}>{t("gen.repartirDesc")}</span>
                  </span>
                </label>
                <label style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: "0.9rem", cursor: "pointer" }}>
                  <input type="checkbox" checked={reemplazar} onChange={(e) => setReemplazar(e.target.checked)} style={{ marginTop: 3 }} />
                  <span>
                    <strong>{t("gen.resortear")}</strong>
                    <span style={{ color: "var(--text-muted)" }}>{t("gen.resortearDesc")}</span>
                  </span>
                </label>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <button className="btn btn-primary" disabled={generando} onClick={handleGenerar}>
                    {generando ? t("gen.generando") : t("gen.generarBtn")}
                  </button>
                  <button className="btn btn-sm" onClick={() => void cargarPreview()}>{t("gen.recalcular")}</button>
                  <button className="btn btn-sm" onClick={() => router.push(`/admin/campeonato/${campId}/llaves`)}>
                    {t("gen.verLlaves")}
                  </button>
                </div>
                {resultado && (
                  <div style={{ fontSize: "0.9rem", display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{ fontWeight: 800, color: "var(--green)" }}>{resultado.message}</div>
                    {resultado.creadas.length > 0 && (
                      <ul style={{ margin: 0, paddingLeft: 18, color: "var(--text-muted)" }}>
                        {resultado.creadas.map((c) => (
                          <li key={c.clave}>{c.nombre} — {c.competidores} {t("gen.competidores")}</li>
                        ))}
                      </ul>
                    )}
                    {resultado.omitidas.length > 0 && (
                      <details>
                        <summary style={{ cursor: "pointer", color: "var(--orange)", fontWeight: 700 }}>
                          {t("gen.omitidas", { n: resultado.omitidas.length })}
                        </summary>
                        <ul style={{ margin: "6px 0 0", paddingLeft: 18, color: "var(--text-muted)" }}>
                          {resultado.omitidas.map((o) => (
                            <li key={o.clave}>{o.nombre}: {o.motivo}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      <style>{`
        .genllaves-page {
          max-width: 1100px; margin: 0 auto; padding: 24px clamp(16px, 4vw, 40px);
        }
        .seg {
          display: inline-flex; background: var(--bg-elevated);
          border: 1px solid var(--border); border-radius: var(--radius-sm);
          padding: 3px; gap: 2px;
        }
        .seg-btn {
          display: inline-flex; align-items: center; gap: 6px;
          padding: 8px 16px; min-height: 36px; border: none; cursor: pointer;
          background: transparent; color: var(--text-muted);
          font: inherit; font-size: 0.9rem; font-weight: 700;
          border-radius: calc(var(--radius-sm) - 2px); transition: all 0.15s;
        }
        .seg-btn:hover:not(.seg-on) { color: var(--text); }
        .seg-btn.seg-on { background: var(--gold); color: var(--text-on-gold, #1a1a1a); }
        @media (max-width: 560px) {
          .genllaves-page { padding: 14px; }
          .seg { width: 100%; }
          .seg-btn { flex: 1; justify-content: center; }
        }
      `}</style>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  Editor de una modalidad (género + cinturones + edades + pesos)
// ══════════════════════════════════════════════════════════════════

function EditorModalidad({
  modalidad,
  onChange,
  onLista,
}: {
  modalidad: ModalidadConfigData;
  onChange: (m: ModalidadConfigData) => void;
  onLista: (campo: "cinturon" | "edad" | "peso", lista: CategoriaConfigItem[]) => void;
}) {
  const { t } = useI18n();
  const [abierta, setAbierta] = useState(modalidad.activa);
  const cat = modalidad.categorias;

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden", opacity: modalidad.activa ? 1 : 0.6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={() => setAbierta(!abierta)}
          style={{
            display: "flex", alignItems: "center", gap: 8, flex: 1, minWidth: 0,
            background: "transparent", border: "none", color: "var(--text)",
            cursor: "pointer", font: "inherit", textAlign: "left", padding: 0,
          }}
        >
          <span style={{ fontWeight: 800, fontSize: "1rem" }}>{modalidad.nombre}</span>
          <span className={`badge ${modalidad.tipo_llave === "figuras" ? "badge-chung" : "badge-hong"}`}>
            {modalidad.tipo_llave === "figuras" ? t("tat.figuras") : t("tat.combate")}
          </span>
          <span style={{ color: "var(--text-dim)", marginLeft: "auto" }}>{abierta ? "▲" : "▼"}</span>
        </button>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.875rem", color: "var(--text-muted)", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={modalidad.activa}
            onChange={(e) => onChange({ ...modalidad, activa: e.target.checked })}
          />
          {t("gen.incluir")}
        </label>
      </div>

      {abierta && (
        <div className="animate-fade" style={{ padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Género */}
          <div>
            <TituloNivel texto={t("gen.genero")} />
            <div style={{ display: "flex", gap: 6 }}>
              {[
                { valor: "separado", label: t("gen.generoSeparado") },
                { valor: "mixto", label: t("gen.generoMixto") },
              ].map((op) => (
                <button
                  key={op.valor}
                  type="button"
                  className="btn btn-sm"
                  onClick={() => onChange({ ...modalidad, categorias: { ...cat, genero: op.valor } })}
                  style={{
                    background: cat.genero === op.valor ? "var(--gold-bg)" : undefined,
                    borderColor: cat.genero === op.valor ? "var(--gold-border)" : undefined,
                    color: cat.genero === op.valor ? "var(--gold)" : undefined,
                    fontSize: "0.82rem",
                  }}
                >
                  {op.label}
                </button>
              ))}
            </div>
          </div>

          {/* Cinturones */}
          <div>
            <TituloNivel texto={t("gen.cinturones")} hint={t("gen.cinturonesHint")} />
            <SelectorCinturones
              lista={cat.cinturon || []}
              onChange={(lista) => onLista("cinturon", lista)}
            />
          </div>

          {/* Edades */}
          <div>
            <TituloNivel texto={t("gen.edades")} hint={t("gen.edadesHint")} />
            <SelectorRangos
              lista={cat.edad || []}
              onChange={(lista) => onLista("edad", lista)}
            />
          </div>

          {/* Pesos */}
          <div>
            <TituloNivel texto={t("gen.pesos")} hint={t("gen.pesosHint")} />
            <SelectorRangos
              lista={cat.peso || []}
              onChange={(lista) => onLista("peso", lista)}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function TituloNivel({ texto, hint }: { texto: string; hint?: string }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <div className="microetiqueta">{texto}</div>
      {hint && <div style={{ fontSize: "0.82rem", color: "var(--text-dim)", marginTop: 2 }}>{hint}</div>}
    </div>
  );
}

/** Etiqueta visible de una categoría (soporta configs guardadas con rango). */
function etiquetaItem(c: CategoriaConfigItem): string {
  if (c.valor) return c.valor;
  if (c.desde || c.hasta) return `${c.desde || ""}-${c.hasta || ""}`;
  return "?";
}

/**
 * Convierte una etiqueta a intervalo numérico [min, max] (extremos abiertos →
 * ±Infinity): "12-14" → [12,14] · "18+" → [18,∞] · "-50" → [-∞,50].
 */
function intervaloDeEtiqueta(etiqueta: string): [number, number] | null {
  const s = etiqueta.trim();
  let m = s.match(/^(\d+(?:\.\d+)?)\+$/);
  if (m) return [parseFloat(m[1]), Infinity];
  m = s.match(/^-(\d+(?:\.\d+)?)$/);
  if (m) return [-Infinity, parseFloat(m[1])];
  m = s.match(/^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$/);
  if (m) return [parseFloat(m[1]), parseFloat(m[2])];
  return null;
}

/** Los rangos son inclusivos en ambos extremos: 15-17 y 17-19 SÍ se cruzan. */
function seCruzan(a: [number, number], b: [number, number]): boolean {
  return a[0] <= b[1] && b[0] <= a[1];
}

/**
 * Si la etiqueta nueva se cruza con alguna ya agregada, retorna la etiqueta
 * en conflicto; null si no hay choque.
 */
function etiquetaEnConflicto(
  nueva: string,
  lista: CategoriaConfigItem[],
): string | null {
  const intervalo = intervaloDeEtiqueta(nueva);
  if (!intervalo) return null;
  for (const c of lista) {
    const otra = etiquetaItem(c);
    const otro = intervaloDeEtiqueta(otra);
    if (otro && seCruzan(intervalo, otro)) return otra;
  }
  return null;
}

/** Chip pequeño de una categoría: clic alterna activa, ✕ la quita. */
function Chip({ item, onToggle, onQuitar, title }: {
  item: CategoriaConfigItem;
  onToggle: () => void;
  onQuitar: () => void;
  title?: string;
}) {
  const { t } = useI18n();
  return (
    <span
      className="chip-cat"
      style={{ opacity: item.activa ? 1 : 0.45 }}
      title={title || (item.activa ? t("gen.chipActiva") : t("gen.chipInactiva"))}
    >
      <button type="button" className="chip-cat-label" onClick={onToggle}>
        {etiquetaItem(item)}
      </button>
      <button type="button" className="chip-cat-x" aria-label={t("gen.chipQuitar", { etiqueta: etiquetaItem(item) })} onClick={onQuitar}>
        ✕
      </button>
      <style>{`
        .chip-cat {
          display: inline-flex; align-items: center; gap: 2px;
          background: var(--gold-bg); border: 1px solid var(--gold-border);
          border-radius: 999px; padding: 2px 4px 2px 10px;
        }
        .chip-cat-label {
          background: none; border: none; color: var(--gold); cursor: pointer;
          font: inherit; font-size: 0.84rem; font-weight: 800; padding: 0;
        }
        .chip-cat-x {
          background: none; border: none; color: var(--text-muted); cursor: pointer;
          font-size: 0.75rem; padding: 2px 6px; border-radius: 999px;
        }
        .chip-cat-x:hover { color: var(--red-alert); }
      `}</style>
    </span>
  );
}

// Rangos de cinturón disponibles en el desplegable (grupos que agrupa cada uno)
const RANGOS_CINTURON: { label: string; grupos: string[] }[] = [
  { label: "Blancos", grupos: ["BLANCO"] },
  { label: "Principiantes", grupos: ["PRINCIPIANTE"] },
  { label: "Intermedios", grupos: ["INTERMEDIO"] },
  { label: "Avanzados", grupos: ["AVANZADO"] },
  { label: "Negros", grupos: ["NEGRO"] },
  { label: "Blancos y Principiantes", grupos: ["BLANCO", "PRINCIPIANTE"] },
  { label: "Intermedios y Avanzados", grupos: ["INTERMEDIO", "AVANZADO"] },
  { label: "Avanzados y Negros", grupos: ["AVANZADO", "NEGRO"] },
  { label: "Todos juntos", grupos: [...GRUPOS_CINTURON] },
];

function SelectorCinturones({ lista, onChange }: {
  lista: CategoriaConfigItem[];
  onChange: (lista: CategoriaConfigItem[]) => void;
}) {
  const { t } = useI18n();
  const [rangoSel, setRangoSel] = useState("");

  // Un rango deja de ofrecerse si alguno de sus grupos ya está cubierto por
  // una etiqueta agregada (evita que un competidor caiga en dos categorías).
  const gruposUsados = new Set(lista.flatMap((c) => c.grupos || []));
  const disponibles = RANGOS_CINTURON.filter(
    (r) =>
      !lista.some((c) => (c.valor || "") === r.label) &&
      !r.grupos.some((g) => gruposUsados.has(g))
  );
  const seleccion = disponibles.some((r) => r.label === rangoSel)
    ? rangoSel
    : disponibles[0]?.label || "";

  function agregar() {
    const rango = disponibles.find((r) => r.label === seleccion);
    if (!rango) return;
    onChange([...lista, {
      activa: true, tipo: "individual", valor: rango.label, grupos: [...rango.grupos],
    }]);
    setRangoSel("");
  }

  return (
    <div className="sel-cat-fila">
      {lista.map((c, i) => (
        <Chip
          key={`${etiquetaItem(c)}-${i}`}
          item={c}
          title={(c.grupos || []).length ? t("gen.agrupa", { grupos: (c.grupos || []).join(", ") }) : undefined}
          onToggle={() => {
            const nueva = [...lista];
            nueva[i] = { ...c, activa: !c.activa };
            onChange(nueva);
          }}
          onQuitar={() => onChange(lista.filter((_, j) => j !== i))}
        />
      ))}
      {disponibles.length > 0 ? (
        <>
          <select
            className="input sel-cat-mini"
            value={seleccion}
            onChange={(e) => setRangoSel(e.target.value)}
            aria-label={t("gen.rangoAria")}
          >
            {disponibles.map((r) => (
              <option key={r.label} value={r.label}>{r.label}</option>
            ))}
          </select>
          <button type="button" className="btn btn-sm sel-cat-add" onClick={agregar}>＋</button>
        </>
      ) : (
        <span style={{ fontSize: "0.82rem", color: "var(--text-dim)" }}>
          {t("gen.todosCubiertos")}
        </span>
      )}
      <style>{`
        .sel-cat-fila {
          display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
        }
        .sel-cat-mini {
          width: auto; min-width: 120px; max-width: 210px;
          padding: 4px 26px 4px 10px; min-height: 30px; font-size: 0.85rem;
        }
        .sel-cat-add {
          padding: 2px 10px; min-height: 30px; font-weight: 900;
        }
      `}</style>
    </div>
  );
}

function SelectorRangos({ lista, onChange }: {
  lista: CategoriaConfigItem[];
  onChange: (lista: CategoriaConfigItem[]) => void;
}) {
  const { t } = useI18n();
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [error, setError] = useState<string | null>(null);

  function agregar() {
    const d = desde.trim();
    const h = hasta.trim();
    if (!d && !h) return;
    if (d && h && Number(d) > Number(h)) {
      setError(t("gen.desdeMayor"));
      return;
    }
    const valor = d && h ? `${d}-${h}` : d ? `${d}+` : `-${h}`;
    // Los rangos no pueden cruzarse: un competidor caería en dos categorías.
    const choque = etiquetaEnConflicto(valor, lista);
    if (choque) {
      setError(t("gen.seCruza", { nuevo: valor, otro: choque }));
      return;
    }
    onChange([...lista, { activa: true, tipo: "individual", valor }]);
    setDesde("");
    setHasta("");
    setError(null);
  }

  return (
    <div>
      <div className="sel-cat-fila" style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        {lista.map((c, i) => (
          <Chip
            key={`${etiquetaItem(c)}-${i}`}
            item={c}
            onToggle={() => {
              const nueva = [...lista];
              nueva[i] = { ...c, activa: !c.activa };
              onChange(nueva);
            }}
            onQuitar={() => {
              onChange(lista.filter((_, j) => j !== i));
              setError(null);
            }}
          />
        ))}
        <input
          className="input rango-mini"
          type="number"
          placeholder={t("gen.desde")}
          value={desde}
          onChange={(e) => { setDesde(e.target.value); setError(null); }}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); agregar(); } }}
          aria-label={t("gen.desde")}
        />
        <span style={{ color: "var(--text-dim)", fontSize: "0.82rem" }}>{t("gen.a")}</span>
        <input
          className="input rango-mini"
          type="number"
          placeholder={t("gen.hasta")}
          value={hasta}
          onChange={(e) => { setHasta(e.target.value); setError(null); }}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); agregar(); } }}
          aria-label={t("gen.hasta")}
        />
        <button
          type="button"
          className="btn btn-sm"
          style={{ padding: "2px 10px", minHeight: 30, fontWeight: 900 }}
          onClick={agregar}
          disabled={!desde.trim() && !hasta.trim()}
        >
          ＋
        </button>
        <style>{`
          .rango-mini {
            width: 76px; padding: 4px 8px; min-height: 30px; font-size: 0.85rem;
          }
        `}</style>
      </div>
      {error && (
        <div role="alert" style={{
          color: "var(--red-alert)", fontSize: "0.82rem", fontWeight: 700, marginTop: 4,
        }}>
          ⚠ {error}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  Tarjeta de una sección en la vista previa
// ══════════════════════════════════════════════════════════════════

function SeccionCard({
  seccion, abierta, onToggle,
}: {
  seccion: SeccionPreview;
  abierta: boolean;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  const n = seccion.competidores.length;
  const lista = n >= 2;
  const existente = seccion.llave_existente;

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <button
        type="button"
        onClick={onToggle}
        style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          gap: 10, width: "100%", padding: "12px 14px",
          background: "transparent", border: "none", color: "var(--text)",
          cursor: "pointer", font: "inherit", textAlign: "left",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            <span style={{ fontWeight: 800, overflowWrap: "anywhere" }}>{seccion.nombre}</span>
            <span className={`badge ${seccion.tipo_llave === "figuras" ? "badge-chung" : "badge-hong"}`}>
              {seccion.tipo_llave === "figuras" ? t("tat.figuras") : t("tat.combate")}
            </span>
            <span className={`badge ${lista ? "badge-green" : "badge-gray"}`}>
              {n === 1 ? t("gen.comp1") : t("gen.compN", { n })}
            </span>
            {n === 1 && <span className="badge badge-gray">{t("gen.insuficiente")}</span>}
            {existente && (
              <span className="badge badge-gold">
                {t("gen.llaveGenerada", { estado: existente.estado })}
              </span>
            )}
          </div>
        </div>
        <span style={{ color: "var(--text-dim)", flexShrink: 0 }}>{abierta ? "▲" : "▼"}</span>
      </button>
      {abierta && n > 0 && (
        <div className="animate-fade" style={{
          padding: "0 14px 12px",
          display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 6,
        }}>
          {seccion.competidores.map((c) => (
            <div key={c.inscripcion_id} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
              background: "var(--bg-elevated)", border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)", fontSize: "0.88rem",
            }}>
              <span style={{ fontWeight: 700, overflowWrap: "anywhere" }}>{c.nombre}</span>
              <span style={{ color: "var(--text-muted)", fontSize: "0.82rem", marginLeft: "auto", flexShrink: 0 }}>
                {[
                  c.edad != null ? `${c.edad}a` : null,
                  c.peso != null ? `${c.peso}kg` : null,
                ].filter(Boolean).join(" · ")}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
