"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import {
  useCombate,
  marcadorDisplay,
  marcadorFinal,
  formatTime,
  promedioEsquinas,
  puntosJuezCentral,
  fmtSigno,
  type CombateState,
} from "@/hooks/useCombate";
import { useSocketTicket } from "@/hooks/useSocketTicket";
import {
  activarAudio,
  sfxAviso10s,
  sfxFalta,
  sfxGanador,
  sfxGong,
  sfxNotaFiguras,
  sfxOro,
  sfxPodio,
  sfxPuntoChung,
  sfxPuntoHong,
  sfxTurnoFiguras,
} from "@/lib/sfx";
import AlertSystem, {
  useAlertSystem,
  type FaltaFlashData,
  type GanadorData,
  type Alerta12Data,
  type DerrotaData,
} from "@/components/AlertSystem";
import LlavePanel from "@/components/LlavePanel";
import GrupoFigurasPanel from "@/components/GrupoFigurasPanel";
import PanelColapsable from "@/components/PanelColapsable";
import BracketTree from "@/components/BracketTree";
import PodioLlave from "@/components/PodioLlave";
import Logo from "@/components/Logo";
import PublicControls from "@/components/PublicControls";
import SelectMenu from "@/components/SelectMenu";
import { CATEGORIAS_FIGURAS } from "@/lib/categorias";
import { useI18n, type ClaveTexto } from "@/lib/i18n";

// ─── Figuras Types ───────────────────────────────────────────────────────────
interface Criterio { id: string; nombre: string; max_pts: number; }
interface Competidor { id: number; nombre: string; club?: string; especial?: boolean; promedio?: number; }
interface CompetidorRankeado extends Competidor {
  total: number;
  puesto: number;
  empate: boolean;
  /** Todos los jueces activos ya confirmaron su nota */
  completo: boolean;
}
interface FigurasState {
  tipo: "figuras";
  criterios: Criterio[];
  competidores: Competidor[];
  puntuaciones: Record<string, Record<string, number>>; // { comp_id: { juez_id: float } }
  puntuaciones_confirmadas: Record<string, Record<string, boolean>>;
  competidor_activo_id: number | null;
  puntuacion_abierta: boolean;
  nombre_categoria: string;
  descripcion?: string;
  num_jueces: number;
  nombres_jueces: Record<string, string>;
  finalizado: boolean;
  en_desempate?: number[];
  log: { txt: string; color: string; ts: number }[];
  _categoria?: string;
  _tatami_activo?: boolean;
  _nombre_categoria?: string;
  _tatami_numero?: number | null;
  _campeonato_nombre?: string | null;
  _campeonato_id?: number | null;
  _grupo_figuras?: { llave_id: number; nombre: string } | null;
  _roles_conectados?: Record<string, string | null>;
  _num_combate?: number | null;
}

type AnyState = (CombateState & { _categoria?: string }) | (FigurasState & { _categoria?: string });

// ─── Helpers ─────────────────────────────────────────────────────────────────
// Nombres de ronda para PANTALLA (los textos viven en lib/i18n)
const RONDAS_CLAVE: Record<string, ClaveTexto> = {
  r1: "tat.ronda.r1",
  r2: "tat.ronda.r2",
  oro: "tat.ronda.oro",
};

function isFiguras(state: AnyState): state is FigurasState {
  return (state as FigurasState).tipo === "figuras" || state._categoria === "figuras";
}

function combateActivo(state: CombateState): boolean {
  // Combate activo si: hay historial de puntos O el cronómetro ha bajado
  if (!state.historial) return false;
  const hayPuntos = state.historial.length > 0;
  const cronoMovio = state.segundos < state.segundosMax;
  return hayPuntos || cronoMovio;
}

function competidoresConNombre(state: CombateState): boolean {
  const hong = state.nombreHong?.trim();
  const chung = state.nombreChung?.trim();
  return Boolean(hong && chung && hong !== "Hong" && chung !== "Chung");
}

function formatScoreValue(value: number | string) {
  const parsed = typeof value === "number"
    ? value
    : Number(String(value).replace(",", "."));
  if (!Number.isFinite(parsed)) return "";
  return Math.max(0, Math.min(9.99, parsed)).toFixed(2);
}

function normalizeScoreInput(raw: string) {
  const cleaned = raw.trim().replace(",", ".");
  if (!cleaned) return "";
  const parsed = Number(cleaned);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 9.99) return "";
  return parsed.toFixed(2);
}

function isValidScore(raw: string) {
  if (!/^\d\.\d{2}$/.test(raw)) return false;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 9.99;
}

const CATEGORIA_NOMBRE_MAX = 40;

function sanitizeCategoryName(raw: string) {
  // Solo letras y espacios, siempre en MAYÚSCULAS: así "Defensa" y "defensa"
  // no quedan como categorías distintas en el registro.
  return raw.replace(/[^\p{L} ]/gu, "").toUpperCase().slice(0, CATEGORIA_NOMBRE_MAX);
}

function categoriaNombreValido(raw?: string) {
  const value = (raw || "").trim();
  return Boolean(value && /^[\p{L} ]+$/u.test(value));
}

// Máximo 4 jueces de esquina por tatami
const JUECES_FIGURAS = ["j1", "j2", "j3", "j4"];

function juecesActivosFiguras(state: FigurasState) {
  return JUECES_FIGURAS
    .slice(0, state.num_jueces || 4)
    .filter((_, idx) => Boolean(state.criterios[idx]));
}

function figurasPuntuacionesCompletas(state: FigurasState) {
  if (!state.competidores.length) return false;
  const jueces = juecesActivosFiguras(state);
  if (!jueces.length) return false;
  return state.competidores.every((comp) => {
    const compId = String(comp.id);
    return jueces.every((juezId) => state.puntuaciones_confirmadas?.[compId]?.[juezId]);
  });
}

/**
 * Ranking de figuras (espejo de calcular_ranking del backend):
 * - TODOS los de categoría especial reciben el puesto 1 sin importar su
 *   puntuación: comparten el primer puesto con el 1° normal.
 * - Empate de totales en el podio normal = empate REAL: comparten puesto
 *   (1, 2, 2, 4) y se resuelve con presentación de desempate (Reevaluar).
 */
function rankingFiguras(state: FigurasState): CompetidorRankeado[] {
  const jueces = juecesActivosFiguras(state);

  function totalDe(comp: Competidor): number {
    // Solo suman los jueces activos: la nota de un juez de más (ej: j3 con la
    // categoría a 2 jueces) no cuenta en el total, igual que en el backend.
    const notas = state.puntuaciones[String(comp.id)] || {};
    const puntajes = jueces
      .map((j) => notas[j])
      .filter((v) => v !== undefined && v !== null)
      .map(Number);
    return Math.round(puntajes.reduce((s, v) => s + v, 0) * 100) / 100;
  }

  function completoDe(comp: Competidor): boolean {
    return jueces.length > 0 && jueces.every(
      (j) => state.puntuaciones_confirmadas?.[String(comp.id)]?.[j]
    );
  }

  function ordenar(lista: Competidor[], todosPrimero: boolean): CompetidorRankeado[] {
    const items = lista
      .map((c) => ({
        ...c, total: totalDe(c), puesto: 1, empate: false, completo: completoDe(c),
      }))
      .sort((a, b) => b.total - a.total);
    if (todosPrimero) return items;
    let puesto = 0;
    items.forEach((item, idx) => {
      if (idx === 0 || item.total !== items[idx - 1].total) puesto = idx + 1;
      item.puesto = puesto;
    });
    // Empate solo entre competidores con puntuación COMPLETA: dos sin
    // calificar (0.00) no están empatados, les falta puntuar.
    const grupos: Record<number, CompetidorRankeado[]> = {};
    items.forEach((r) => { (grupos[r.puesto] = grupos[r.puesto] || []).push(r); });
    Object.values(grupos).forEach((grupo) => {
      const esEmpate = grupo.length > 1 && grupo.every((g) => g.completo);
      grupo.forEach((g) => { g.empate = esEmpate; });
    });
    return items;
  }

  const especiales = state.competidores.filter((c) => c.especial);
  const normales = state.competidores.filter((c) => !c.especial);
  return [...ordenar(especiales, true), ...ordenar(normales, false)];
}

function colorPuesto(puesto: number, especial?: boolean) {
  if (especial || puesto === 1) return "var(--gold)";
  if (puesto === 2) return "#C0C0C0";
  if (puesto === 3) return "#CD7F32";
  return "var(--text-dim)";
}

function figurasConDatos(state: FigurasState) {
  // Solo competidores o puntuaciones reales bloquean el cambio de categoría;
  // el log o el nombre de la categoría no cuentan como "datos en curso".
  const tienePuntuaciones = Object.values(state.puntuaciones || {})
    .some((puntajes) => Object.keys(puntajes || {}).length > 0);
  return Boolean(state.competidores.length || tienePuntuaciones);
}

// ─── Category Selector ───────────────────────────────────────────────────────
function CatSelector({
  current, onSelect, figurasLabel,
}: { current: string; onSelect: (cat: string) => void; figurasLabel: string }) {
  const { t } = useI18n();
  const labels: Record<string, string> = {
    combate: t("tat.combate"),
    figuras: figurasLabel || t("tat.figuras"),
  };

  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      <span style={{ color: "var(--text-muted)", fontSize: "0.8rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em" }}>{t("tat.cat")}</span>
      {["combate", "figuras"].map((cat) => (
        <button
          key={cat}
          className="btn btn-sm"
          onClick={() => onSelect(cat)}
          style={{
            textTransform: "capitalize",
            background: current === cat ? (cat === "combate" ? "var(--hong-bg)" : "var(--gold-bg)") : undefined,
            borderColor: current === cat ? (cat === "combate" ? "var(--hong-border)" : "var(--gold-border)") : undefined,
            color: current === cat ? (cat === "combate" ? "var(--hong-light)" : "var(--gold)") : undefined,
            padding: "4px 10px", minHeight: 32, fontSize: "0.875rem",
          }}
        >
          {labels[cat]}
        </button>
      ))}
    </div>
  );
}

// ─── Crono Display ────────────────────────────────────────────────────────────
function CronoDisplay({ segundos, activo, big = false }: {
  segundos: number; activo: boolean; segundosMax?: number; big?: boolean;
}) {
  const cls = !activo ? "pause"
    : segundos <= 5 ? "urgente-5"
    : segundos <= 10 ? "urgente"
    : "activo";
  return (
    <div
      className={`crono-display ${cls}`}
      style={{ fontSize: big ? "clamp(3rem,7vw,6rem)" : "2rem" }}
    >
      {formatTime(segundos)}
    </div>
  );
}

// ─── Desglose del marcador ───────────────────────────────────────────────────
// Promedio de esquinas y puntos del Juez Central SIEMPRE por separado. El
// valor del JC no depende de la cantidad de jueces promediados: una falta de
// −0.5 se muestra igual con 2, 3 o 4 jueces de esquina.
function DesgloseMarcador({ state, color, grande = false }: {
  state: CombateState; color: "hong" | "chung"; grande?: boolean;
}) {
  const { t } = useI18n();
  const esq = promedioEsquinas(state, color);
  const jc = puntosJuezCentral(state, color);
  const jcColor = jc < 0 ? "var(--red-alert)" : jc > 0 ? "var(--green)" : "var(--text-dim)";
  return (
    <div style={{
      display: "flex", gap: grande ? 18 : 10, justifyContent: "center", flexWrap: "wrap",
      fontFamily: "var(--font-mono)",
      fontSize: grande ? "clamp(0.875rem,1.5vw,1.1rem)" : "0.68rem",
      marginTop: grande ? 8 : 2, color: "var(--text-muted)",
    }}>
      <span>
        {t("tat.esquinas")} <strong style={{ color: "var(--text)" }}>{esq.toFixed(1)}</strong>
      </span>
      <span>
        {t("tat.jcentral")} <strong style={{ color: jcColor }}>{fmtSigno(jc)}</strong>
      </span>
    </div>
  );
}

// ─── Panel de conexiones: qué jueces están conectados AHORA ─────────────────
// El servidor difunde _roles_conectados en cada conexión/desconexión: la mesa
// ve al instante si un juez se cayó antes de seguir puntuando.
function ConexionJueces({ conectados, numJueces }: {
  conectados: Record<string, string | null>;
  numJueces: number;
}) {
  const { t } = useI18n();
  const roles = ["arbitro", ...["j1", "j2", "j3", "j4"].slice(0, numJueces || 4)];
  const etiqueta = (r: string) => (r === "arbitro" ? "JC" : r.toUpperCase());
  const faltan = roles.filter((r) => !(r in conectados));
  return (
    <div style={{
      display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap",
      padding: "6px 14px", borderBottom: "1px solid var(--border)",
      background: "var(--bg-card)", fontSize: "0.78rem",
    }}>
      <span style={{ color: "var(--text-dim)", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {t("tat.conexiones")}
      </span>
      {roles.map((r) => {
        const on = r in conectados;
        return (
          <span
            key={r}
            title={on ? (conectados[r] || t("tat.conectado")) : t("tat.sinConexion")}
            style={{
              display: "inline-flex", alignItems: "center", gap: 4,
              padding: "2px 8px", borderRadius: 999,
              border: `1px solid ${on ? "rgba(0,212,114,0.4)" : "var(--border)"}`,
              color: on ? "var(--green)" : "var(--text-dim)",
              fontWeight: 700,
            }}
          >
            <span className={`status-dot ${on ? "online" : "offline"}`} />
            {etiqueta(r)}
          </span>
        );
      })}
      {faltan.length > 0 && (
        <span style={{ color: "var(--orange)", fontWeight: 700 }}>
          {t("tat.sinConexionLista", { roles: faltan.map(etiqueta).join(", ") })}
        </span>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// FIGURAS — Juez Central (Arbitro)
// ══════════════════════════════════════════════════════════════════════════════
function FigurasArbitro({
  state, enviarEvento, tatamiId, tatamiDbId, onShowConfirm,
}: {
  state: FigurasState;
  enviarEvento: (accion: string, datos?: Record<string, unknown>) => void;
  tatamiId: string;
  tatamiDbId: string;
  onShowConfirm: (data: import("@/components/AlertSystem").ConfirmData) => void;
}) {
  const { t } = useI18n();
  const [newComp, setNewComp] = useState({ nombre: "", club: "", especial: false });
  const [showAddComp, setShowAddComp] = useState(false);
  const [categoriaError, setCategoriaError] = useState("");
  const [categoriaDraft, setCategoriaDraft] = useState(state.nombre_categoria ?? "");
  const [categoriaPendiente, setCategoriaPendiente] = useState(false);
  const nombreCategoriaValido = categoriaNombreValido(categoriaDraft);
  const [descDraft, setDescDraft] = useState(state.descripcion ?? "");
  const [descFocused, setDescFocused] = useState(false);

  // La descripción del servidor se adopta cuando el JC no la está editando.
  useEffect(() => {
    if (!descFocused && (state.descripcion ?? "") !== descDraft) {
      setDescDraft(state.descripcion ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.descripcion, descFocused]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      const serverName = state.nombre_categoria ?? "";
      if (serverName === categoriaDraft) {
        setCategoriaPendiente(false);
        return;
      }
      if (!categoriaPendiente) {
        setCategoriaDraft(serverName);
      }
    });
    return () => { cancelled = true; };
  }, [categoriaDraft, categoriaPendiente, state.nombre_categoria]);

  function commitNombreCategoria() {
    const nombre = sanitizeCategoryName(categoriaDraft);
    if (nombre !== categoriaDraft) {
      setCategoriaDraft(nombre);
    }
    if (nombre !== (state.nombre_categoria ?? "")) {
      setCategoriaPendiente(true);
      enviarEvento("cambiar_nombre_categoria", { nombre });
    }
    return nombre;
  }

  function validarNombreCategoria() {
    const nombre = commitNombreCategoria();
    if (!categoriaNombreValido(nombre)) {
      setCategoriaError(t("tat.fig.errorCategoria"));
      return false;
    }
    setCategoriaError("");
    return true;
  }

  const ranking = rankingFiguras(state);

  const MAX_COMPETIDORES = 50;
  const puedeAgregar = state.competidores.length < MAX_COMPETIDORES;
  const puntuacionesCompletas = figurasPuntuacionesCompletas(state);

  // Empate real en el podio normal (la categoría especial no se reevalúa)
  const empatadosNormales = (puntuacionesCompletas || state.finalizado)
    ? ranking.filter((r) => r.empate && !r.especial)
    : [];

  // Presentación de desempate en curso: solo los empatados se activan
  const enDesempate = state.en_desempate || [];

  function handleReevaluarEmpate() {
    if (!validarNombreCategoria() || empatadosNormales.length === 0) return;
    const nombres = empatadosNormales.map((r) => r.nombre).join(", ");
    onShowConfirm({
      titulo: t("tat.fig.reevaluar.titulo"),
      mensaje: t("tat.fig.reevaluar.mensaje", { nombres }),
      tipo: "advertencia",
      confirmLabel: t("tat.fig.reevaluar.confirmar"),
      cancelLabel: t("comun.cancelar"),
      onConfirm: () => enviarEvento("reevaluar_empate"),
    });
  }

  // No se puede pasar el turno a otro competidor si al activo
  // le falta alguna puntuación por confirmar.
  const juecesActivos = juecesActivosFiguras(state);
  const activoId = state.competidor_activo_id;
  const activoIncompleto = Boolean(
    activoId !== null
    && juecesActivos.length > 0
    && !juecesActivos.every(
      (j) => state.puntuaciones_confirmadas?.[String(activoId)]?.[j]
    )
  );

  return (
    <div className="tatami-fig-root" style={{ maxWidth: 800, margin: "0 auto" }}>
      {/* Grupos de figuras encolados para este tatami (activación rápida) */}
      <GrupoFigurasPanel
        tatamiDbId={tatamiDbId}
        grupoActivo={state._grupo_figuras ?? null}
        enviarEvento={enviarEvento}
        onShowConfirm={onShowConfirm}
      />

      {/* Categoría de figuras: SOLO selección de las predefinidas (sin escribir)
          para no fragmentar el registro. Es obligatorio elegir una antes de
          agregar competidores o empezar. */}
      <div style={{ marginBottom: 16, display: "flex", flexDirection: "column", gap: 8 }}>
        <SelectMenu
          ariaLabel={t("tat.fig.categoriaAria")}
          value={(CATEGORIAS_FIGURAS as readonly string[]).includes(categoriaDraft) ? categoriaDraft : ""}
          placeholder={t("tat.fig.selectCategoria")}
          onChange={(v) => {
            setCategoriaDraft(v);
            setCategoriaPendiente(true);
            setCategoriaError("");
            enviarEvento("cambiar_nombre_categoria", { nombre: v });
          }}
          options={CATEGORIAS_FIGURAS.map((c) => ({ value: c, label: c }))}
          centerLabel
          style={{ width: "100%" }}
          buttonStyle={{
            fontWeight: 800, fontSize: "1.05rem",
            borderColor: nombreCategoriaValido ? "var(--green-border)" : "var(--hong-border)",
          }}
        />
        {!nombreCategoriaValido && (
          <p style={{ color: "var(--orange)", fontSize: "0.85rem", textAlign: "center", margin: 0 }}>
            {t("tat.fig.eligeCategoria")}
          </p>
        )}
        <input
          className="input"
          value={descDraft}
          placeholder={t("tat.fig.descPlaceholder")}
          maxLength={120}
          onChange={(e) => {
            setDescDraft(e.target.value);
            enviarEvento("cambiar_descripcion", { descripcion: e.target.value });
          }}
          onFocus={() => setDescFocused(true)}
          onBlur={() => setDescFocused(false)}
          style={{ width: "100%", textAlign: "center", fontSize: "0.9rem" }}
        />
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          gap: 8, flexWrap: "wrap",
        }}>
          <span className="card-title" style={{ marginBottom: 0, fontSize: "0.875rem" }}>
            {t("tat.fig.jcTatami", { n: tatamiId })}
          </span>
          {state.puntuacion_abierta && state.competidor_activo_id && (
            <button className="btn btn-sm btn-danger" onClick={() => {
              if (validarNombreCategoria()) enviarEvento("cerrar_puntuacion");
            }}>
              {t("tat.fig.cerrarPuntuacion")}
            </button>
          )}
        </div>
      </div>
      {categoriaError && (
        <div style={{ color: "var(--orange)", fontWeight: 700, fontSize: "0.88rem", margin: "-8px 0 12px" }}>
          {categoriaError}
        </div>
      )}

      {/* Número de jueces (máximo 4 de esquina) */}
      <div className="card" style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", flexWrap: "wrap" }}>
        <span style={{ color: "var(--text-muted)", fontSize: "0.88rem", fontWeight: 700 }}>{t("tat.jc.jueces")}</span>
        {[2, 3, 4].map((n) => (
          <button key={n} className="btn btn-sm"
            onClick={() => {
              if (validarNombreCategoria()) enviarEvento("set_num_jueces", { num_jueces: n });
            }}
            style={{
              background: state.num_jueces === n ? "var(--gold-bg)" : undefined,
              borderColor: state.num_jueces === n ? "var(--gold-border)" : undefined,
              color: state.num_jueces === n ? "var(--gold)" : undefined,
              padding: "4px 12px", minHeight: 32,
            }}>
            {n}
          </button>
        ))}
        <span style={{
          marginLeft: "auto",
          color: puntuacionesCompletas ? "var(--green)" : "var(--text-dim)",
          fontSize: "0.85rem", fontWeight: 700,
        }}>
          {puntuacionesCompletas
            ? t("tat.fig.completas")
            : t("tat.fig.podioAparece")}
        </span>
      </div>

      {/* Competidores */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div className="card-title" style={{ marginBottom: 0 }}>
            {t("tat.fig.competidores")} ({state.competidores.length}/{MAX_COMPETIDORES})
          </div>
          <button className="btn btn-sm btn-primary"
            onClick={() => {
              if (validarNombreCategoria()) setShowAddComp(!showAddComp);
            }}
            disabled={!puedeAgregar}>
            {t("tat.fig.agregarBtn")}
          </button>
        </div>

        {!puedeAgregar && (
          <p style={{ color: "var(--orange)", fontSize: "0.88rem", marginBottom: 8 }}>
            {t("tat.fig.maxAlcanzado", { n: MAX_COMPETIDORES })}
          </p>
        )}

        {showAddComp && (
          <div className="animate-fade" style={{ marginBottom: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input className="input" placeholder={t("tat.fig.nombreComp")} value={newComp.nombre}
                onChange={(e) => setNewComp((v) => ({ ...v, nombre: e.target.value }))}
                style={{ flex: "2 1 180px" }} />
              <input className="input" placeholder={t("tat.fig.club")} value={newComp.club}
                onChange={(e) => setNewComp((v) => ({ ...v, club: e.target.value }))}
                style={{ flex: "1 1 140px" }} />
              <button className="btn btn-primary"
                onClick={() => {
                  if (validarNombreCategoria() && newComp.nombre.trim()) {
                    enviarEvento("agregar_competidor", {
                      nombre: newComp.nombre.trim(),
                      club: newComp.club.trim(),
                      especial: newComp.especial,
                    });
                    setNewComp({ nombre: "", club: "", especial: false });
                    setShowAddComp(false);
                  }
                }}>
                {t("tat.fig.agregar")}
              </button>
            </div>
            <label style={{
              display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
              fontSize: "0.88rem", fontWeight: 700, userSelect: "none",
              color: newComp.especial ? "var(--gold)" : "var(--text-muted)",
            }}>
              <input
                type="checkbox"
                checked={newComp.especial}
                onChange={(e) => setNewComp((v) => ({ ...v, especial: e.target.checked }))}
                style={{ accentColor: "var(--gold)", width: 16, height: 16 }}
              />
              {t("tat.fig.especialLabel")}
            </label>
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {ranking.map((comp) => {
            const isActive = state.competidor_activo_id === comp.id;
            const esPrimero = comp.puesto === 1;
            return (
              <div key={comp.id} style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "8px 12px",
                background: isActive ? "rgba(240,184,0,0.1)" : (esPrimero ? "rgba(240,184,0,0.04)" : "var(--bg-elevated)"),
                borderRadius: "var(--radius-sm)",
                border: `1.5px solid ${isActive ? "var(--gold)" : (esPrimero ? "var(--gold-border)" : "var(--border)")}`,
              }}>
                <span style={{
                  fontFamily: "var(--font-display)", fontSize: "1.5rem", minWidth: 32, textAlign: "center",
                  color: colorPuesto(comp.puesto, comp.especial),
                }}>{comp.puesto}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700, color: isActive ? "var(--gold)" : "inherit", overflowWrap: "anywhere" }}>
                    {comp.nombre}
                    {comp.especial && <span className="badge badge-gold" style={{ marginLeft: 8, verticalAlign: "middle" }}>{t("tat.fig.especial")}</span>}
                    {comp.empate && <span className="badge badge-gray" style={{ marginLeft: 8, verticalAlign: "middle", color: "var(--orange)", borderColor: "rgba(255,140,0,0.4)" }}>{t("tat.fig.desempate")}</span>}
                    {enDesempate.includes(comp.id) && !comp.empate && (
                      <span className="badge badge-gray" style={{ marginLeft: 8, verticalAlign: "middle", color: "var(--orange)", borderColor: "rgba(255,140,0,0.4)" }}>{t("tat.fig.reevaluando")}</span>
                    )}
                    {isActive && <span style={{ marginLeft: 8, fontSize: "0.78rem", background: "var(--gold)", color: "#000", padding: "2px 6px", borderRadius: 4 }}>{t("tat.fig.enTurno")}</span>}
                  </div>
                  {comp.club && <div style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>{comp.club}</div>}
                </div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: "1.8rem", color: esPrimero || isActive ? "var(--gold)" : "var(--text)" }}>
                  {comp.total.toFixed(2)}
                </div>
                {!isActive && (() => {
                  const fueraDelDesempate = enDesempate.length > 0 && !enDesempate.includes(comp.id);
                  const bloqueado = activoIncompleto || fueraDelDesempate || comp.completo;
                  return (
                    <button className="btn btn-sm"
                      disabled={bloqueado}
                      title={comp.completo
                        ? t("tat.fig.titleCalificado")
                        : fueraDelDesempate
                          ? t("tat.fig.titleDesempate")
                          : activoIncompleto
                            ? t("tat.fig.titlePendiente")
                            : undefined}
                      onClick={() => {
                        if (!validarNombreCategoria()) return;
                        if (activoIncompleto) {
                          onShowConfirm({
                            titulo: t("tat.fig.turnoCurso.titulo"),
                            mensaje: t("tat.fig.turnoCurso.mensaje"),
                            tipo: "advertencia",
                            solo_ok: true,
                            onConfirm: () => {},
                          });
                          return;
                        }
                        enviarEvento("activar_competidor", { competidor_id: comp.id });
                      }}
                      style={{
                        padding: "4px 8px", fontSize: "0.78rem",
                        background: "var(--bg-card)", borderColor: "var(--gold)",
                        opacity: bloqueado ? 0.45 : 1,
                      }}>
                      {t("tat.fig.activar")}
                    </button>
                  );
                })()}
                <button className="btn btn-sm btn-danger"
                  title={t("tat.fig.eliminarTitle")}
                  onClick={() => {
                    if (!validarNombreCategoria()) return;
                    const tieneNotas = Object.keys(state.puntuaciones[String(comp.id)] || {}).length > 0;
                    onShowConfirm({
                      titulo: t("tat.fig.eliminar.titulo"),
                      mensaje: t("tat.fig.eliminar.mensaje", {
                        nombre: comp.nombre,
                        club: comp.club ? ` (${comp.club})` : "",
                        notas: tieneNotas ? t("tat.fig.eliminar.notas") : "",
                      }),
                      tipo: "peligro",
                      confirmLabel: t("tat.fig.eliminar.confirmar"),
                      cancelLabel: t("comun.cancelar"),
                      onConfirm: () => enviarEvento("eliminar_competidor", { competidor_id: comp.id }),
                    });
                  }}
                  style={{ padding: "3px 8px", minHeight: 30, fontSize: "0.8rem" }}>
                  ✕
                </button>
              </div>
            );
          })}
          {state.competidores.length === 0 && (
            <p style={{ textAlign: "center", color: "var(--text-dim)", padding: "20px 0", fontSize: "0.92rem" }}>
              {t("tat.fig.agregaComp")}
            </p>
          )}
        </div>
      </div>

      {/* Criterios */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-title">{t("tat.fig.criterios")}</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {state.criterios.map((c) => (
            <div key={c.id} style={{
              padding: "6px 14px", background: "var(--bg-elevated)",
              border: "1px solid var(--border-light)", borderRadius: "var(--radius-sm)",
              fontSize: "0.88rem", fontWeight: 700,
            }}>
              {c.nombre} <span style={{ color: "var(--gold)", marginLeft: 4 }}>/{c.max_pts}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Empate real: presentación de desempate solo para los empatados */}
      {empatadosNormales.length > 0 && (
        <div className="animate-fade" style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          gap: 10, flexWrap: "wrap", marginBottom: 12, padding: "10px 14px",
          background: "rgba(255,140,0,0.08)",
          border: "1.5px solid rgba(255,140,0,0.4)",
          borderRadius: "var(--radius)",
        }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ color: "var(--orange)", fontWeight: 800, fontSize: "0.88rem", textTransform: "uppercase", letterSpacing: "0.08em" }}>
              {t("tat.fig.empatePuesto", { n: empatadosNormales[0].puesto })}
            </div>
            <div style={{ fontSize: "0.88rem", color: "var(--text-muted)", marginTop: 2, overflowWrap: "anywhere" }}>
              {empatadosNormales.map((r) => r.nombre).join(" · ")}
            </div>
          </div>
          <button
            className="btn btn-sm"
            onClick={handleReevaluarEmpate}
            style={{
              background: "rgba(255,140,0,0.15)",
              borderColor: "rgba(255,140,0,0.5)",
              color: "var(--orange)",
              fontWeight: 800,
            }}
          >
            {t("tat.fig.reevaluarBtn")}
          </button>
        </div>
      )}

      {/* Acciones — el podio se muestra automáticamente al completar */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 8 }}>
        <button className="btn btn-primary"
          style={{ whiteSpace: "normal", lineHeight: 1.25, padding: "12px 18px", minHeight: 48 }}
          onClick={() => {
            if (!validarNombreCategoria()) return;
            if (!state.competidores.length) {
              setCategoriaError(t("tat.fig.agregaAntes"));
              return;
            }
            onShowConfirm({
              titulo: t("tat.fig.guardarNueva.titulo"),
              mensaje: t("tat.fig.guardarNueva.mensaje", { nombre: state.nombre_categoria || "Figuras" }),
              tipo: "advertencia",
              confirmLabel: t("tat.guardarNuevoLabel"),
              cancelLabel: t("comun.cancelar"),
              onConfirm: () => enviarEvento("nuevo_combate"),
            });
          }}>
          {t("tat.guardarNuevoBtn")}
        </button>
        <button className="btn btn-danger"
          style={{ whiteSpace: "normal", lineHeight: 1.25, padding: "12px 18px", minHeight: 48 }}
          onClick={() => {
            if (!validarNombreCategoria()) return;
            onShowConfirm({
              titulo: t("tat.fig.reiniciar.titulo"),
              mensaje: t("tat.fig.reiniciar.mensaje"),
              tipo: "peligro",
              confirmLabel: t("tat.reiniciarLabel"),
              cancelLabel: t("comun.cancelar"),
              onConfirm: () => enviarEvento("reset_figuras"),
            });
          }}>
          {t("tat.reiniciarBtn")}
        </button>
      </div>
      {!puntuacionesCompletas && state.competidores.length > 0 && (
        <p style={{ color: "var(--text-dim)", fontSize: "0.84rem", marginTop: 8, textAlign: "center" }}>
          {t("tat.fig.podioAuto")}
        </p>
      )}

      {/* Log */}
      {state.log.length > 0 && (
        <div className="card" style={{ marginTop: 12, padding: "10px 14px" }}>
          <div className="card-title" style={{ marginBottom: 6 }}>{t("tat.fig.log")}</div>
          <div style={{ maxHeight: 120, overflowY: "auto", fontSize: "0.85rem" }}>
            {state.log.slice(0, 8).map((l, i) => (
              <div key={i} style={{ padding: "3px 0", borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
                {l.txt}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// FIGURAS — Juez Normal
// ══════════════════════════════════════════════════════════════════════════════
function FigurasScoreCard({
  state, enviarEvento, juezId, miCriterio, comp,
}: {
  state: FigurasState;
  enviarEvento: (accion: string, datos?: Record<string, unknown>) => void;
  juezId: string;
  miCriterio: Criterio;
  comp: Competidor;
}) {
  const { t } = useI18n();
  const compId = String(comp.id);
  const valCommitted = state.puntuaciones[compId]?.[juezId];
  const isConfirmed = state.puntuaciones_confirmadas?.[compId]?.[juezId];
  const [nota, setNota] = useState(
    valCommitted !== undefined ? formatScoreValue(valCommitted) : ""
  );
  const [error, setError] = useState("");

  function handleBlur(val: string) {
    if (!val.trim()) {
      setError("");
      return;
    }
    const formatted = normalizeScoreInput(val);
    if (!formatted) {
      setError(t("tat.fig.notaRango"));
      return;
    }
    setNota(formatted);
    setError("");
  }

  function handleGuardar() {
    if (isConfirmed) return;
    if (!categoriaNombreValido(state.nombre_categoria)) {
      setError(t("tat.fig.jcNombreValido"));
      return;
    }
    const formatted = normalizeScoreInput(nota);
    if (!formatted || !isValidScore(formatted)) {
      setError(t("tat.fig.notaFormato"));
      return;
    }
    setNota(formatted);
    setError("");
    enviarEvento("puntuar", {
      juez_id: juezId, competidor_id: comp.id, valor: formatted,
    });
    enviarEvento("confirmar_puntuacion", {
      juez_id: juezId, competidor_id: comp.id,
    });
  }

  const canSave = Boolean(nota && isValidScore(normalizeScoreInput(nota) || nota) && !isConfirmed);

  return (
    <div style={{ padding: 12, maxWidth: 500, margin: "0 auto" }}>
      <div style={{ textAlign: "center", marginBottom: 14 }}>
        <div className="card-title" style={{ fontSize: "1rem" }}>
          {state.nombre_categoria || "FIGURAS"} — {juezId.toUpperCase()}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 10, textAlign: "center", padding: "20px 10px" }}>
        <div style={{ fontWeight: 800, fontSize: "1.4rem", marginBottom: 4, color: "var(--gold)" }}>
          {comp.nombre}
        </div>
        <div style={{ fontSize: "0.88rem", color: "var(--text-muted)", marginBottom: 20 }}>
          {comp.club}
        </div>

        <label style={{ fontSize: "0.875rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)" }}>
          {t("tat.fig.califica")}
        </label>
        <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--gold)", marginBottom: 16 }}>
          {miCriterio.nombre} ({t("tat.fig.maxPts")} {miCriterio.max_pts})
        </div>

        <input
          className="input"
          type="text"
          inputMode="numeric"
          placeholder="0.00"
          value={nota}
          disabled={isConfirmed}
          onChange={(e) => {
            // Solo números: el punto decimal se inserta automáticamente
            // después del primer dígito (875 → 8.75, 90 → 9.0)
            const digitos = e.target.value.replace(/\D/g, "").slice(0, 3);
            setNota(digitos.length <= 1 ? digitos : `${digitos[0]}.${digitos.slice(1)}`);
            setError("");
          }}
          onBlur={(e) => handleBlur(e.target.value)}
          style={{
            fontFamily: "var(--font-mono)", fontSize: "3rem", textAlign: "center", padding: "16px",
            borderColor: isConfirmed ? "var(--green-border)" : "var(--gold)",
            background: isConfirmed ? "rgba(0, 212, 114, 0.1)" : "var(--bg-elevated)",
            color: isConfirmed ? "var(--green)" : "var(--text)",
            maxWidth: 200, margin: "0 auto", height: 80,
          }}
        />

        {!isConfirmed && (
          <div style={{ marginTop: 8, color: "var(--text-dim)", fontSize: "0.85rem" }}>
            {t("tat.fig.soloNumeros1")} <strong style={{ color: "var(--text-muted)" }}>875</strong>{" "}
            {t("tat.fig.soloNumeros2")} <strong style={{ color: "var(--gold)" }}>8.75</strong>
          </div>
        )}

        {error && (
          <div style={{ marginTop: 10, color: "var(--orange)", fontWeight: 700, fontSize: "0.92rem" }}>
            {error}
          </div>
        )}

        {isConfirmed ? (
          <div style={{ marginTop: 20, color: "var(--green)", fontWeight: 700, fontSize: "1.1rem" }}>
            {t("tat.fig.guardada")} {formatScoreValue(valCommitted ?? 0)}
          </div>
        ) : (
          <button className="btn btn-primary"
            onClick={handleGuardar}
            disabled={!canSave}
            style={{ marginTop: 20, width: "100%", padding: 16, fontSize: "1.1rem", fontWeight: 800 }}>
            {t("tat.fig.guardarPuntuacion")}
          </button>
        )}
      </div>
    </div>
  );
}

function FigurasJuez({
  state, enviarEvento, juezId, connected,
}: {
  state: FigurasState;
  enviarEvento: (accion: string, datos?: Record<string, unknown>) => void;
  juezId: string;
  connected: boolean;
}) {
  const { t } = useI18n();
  const params = useParams();
  const offline = useRegistroOffline(`dinamyt_offline_figuras_${params.id}_${juezId}`);
  const [nombreOff, setNombreOff] = useState("");
  const [notaOff, setNotaOff] = useState("");
  const MAP_JUEZ = { j1: 0, j2: 1, j3: 2, j4: 3 };
  const idxCriterio = MAP_JUEZ[juezId as keyof typeof MAP_JUEZ];
  // Optional chaining: en offline este componente puede montarse con estado
  // de combate (el juez cambió a "Figuras" con el selector local).
  const miCriterio = idxCriterio !== undefined ? state.criterios?.[idxCriterio] : undefined;

  // Rol fuera de la configuración actual (ej: j3 con la categoría a 2 jueces):
  // su nota no se sumaría al total, así que no puntúa (espejo de CombateJuez).
  const numJueces = state.num_jueces || 4;
  const rolInactivo = idxCriterio === undefined || idxCriterio >= numJueces;
  if (rolInactivo) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text-dim)" }}>
        <p style={{ fontSize: "1.4rem", marginBottom: 8 }}>
          {t("tat.fig.noParticipa", { rol: juezId.toUpperCase() })}
        </p>
        <p style={{ fontSize: "0.9rem" }}>
          {t("tat.fig.noParticipaDesc", { n: numJueces })}
        </p>
      </div>
    );
  }

  // Sin conexión el servidor no puede activar competidores: el juez anota
  // sus notas en una libreta local y las reingresa (o dicta a la mesa) después.
  if (!connected) {
    return (
      <div style={{ maxWidth: 520, margin: "0 auto", padding: "12px 14px" }}>
        <PanelRegistroOffline
          modo="resumen"
          conectado={false}
          entradas={offline.entradas}
          onDeshacer={offline.deshacer}
          onLimpiar={offline.limpiar}
          descripcion={t("tat.fig.offDesc")}
        />
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 10 }}>
          <div className="card-title">{t("tat.fig.anotarLocal")}{miCriterio ? ` — ${miCriterio.nombre}` : ""}</div>
          <input
            className="input"
            placeholder={t("tat.fig.nombreComp")}
            value={nombreOff}
            onChange={(e) => setNombreOff(e.target.value)}
          />
          <input
            className="input"
            inputMode="numeric"
            placeholder={t("tat.fig.notaEj")}
            value={notaOff}
            onChange={(e) => {
              // Igual que el input online: solo números, máximo 3 dígitos y
              // el punto decimal se inserta solo (875 → 8.75, 90 → 9.0)
              const digitos = e.target.value.replace(/\D/g, "").slice(0, 3);
              setNotaOff(digitos.length <= 1 ? digitos : `${digitos[0]}.${digitos.slice(1)}`);
            }}
            style={{ fontFamily: "var(--font-mono)", textAlign: "center" }}
          />
          <button
            className="btn btn-primary"
            disabled={!nombreOff.trim() || !notaOff.trim()}
            onClick={() => {
              offline.agregar({ etiqueta: `${nombreOff.trim()}: ${notaOff.trim()}` });
              setNombreOff("");
              setNotaOff("");
            }}
          >
            {t("tat.fig.guardarNota")}
          </button>
        </div>
        <PanelRegistroOffline
          modo="detalle"
          conectado={false}
          entradas={offline.entradas}
          onDeshacer={offline.deshacer}
          onLimpiar={offline.limpiar}
          descripcion=""
        />
      </div>
    );
  }

  // Tras reconectar, recordar las notas locales pendientes de reingresar
  const recordatorioOffline = offline.entradas.length > 0 ? (
    <div style={{ maxWidth: 520, margin: "0 auto", padding: "12px 14px 0" }}>
      <PanelRegistroOffline
        conectado
        entradas={offline.entradas}
        onDeshacer={offline.deshacer}
        onLimpiar={offline.limpiar}
        descripcion={t("tat.fig.reconectadoDesc")}
      />
    </div>
  ) : null;

  if (!categoriaNombreValido(state.nombre_categoria)) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text-dim)" }}>
        <p style={{ fontSize: "1.4rem", marginBottom: 8 }}>{t("tat.fig.esperandoNombre")}</p>
        <p style={{ fontSize: "0.9rem" }}>{t("tat.fig.esperandoNombreDesc")}</p>
      </div>
    );
  }

  if (state.competidores.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text-dim)" }}>
        <p style={{ fontSize: "1.4rem", marginBottom: 8 }}>{t("tat.fig.esperandoComp")}</p>
        <p style={{ fontSize: "0.9rem" }}>{t("tat.fig.esperandoCompDesc")}</p>
      </div>
    );
  }

  if (!state.puntuacion_abierta || !state.competidor_activo_id) {
    return (
      <>
        {recordatorioOffline}
        <div style={{ padding: 40, textAlign: "center", color: "var(--text-dim)" }}>
          <p style={{ fontSize: "1.4rem", marginBottom: 8 }}>{t("tat.fig.esperandoAuth")}</p>
          <p style={{ fontSize: "0.9rem" }}>{t("tat.fig.esperandoAuthDesc")}</p>
        </div>
      </>
    );
  }

  if (!miCriterio) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--red-alert)" }}>
        <p style={{ fontSize: "1.4rem", marginBottom: 8 }}>{t("tat.fig.sinCriterio")}</p>
        <p style={{ fontSize: "0.9rem" }}>{t("tat.fig.sinCriterioDesc")}</p>
      </div>
    );
  }

  const compId = String(state.competidor_activo_id);
  const comp = state.competidores.find((c) => c.id === state.competidor_activo_id);
  if (!comp) return null;

  const valCommitted = state.puntuaciones[compId]?.[juezId];
  const isConfirmed = state.puntuaciones_confirmadas?.[compId]?.[juezId];

  return (
    <>
      {recordatorioOffline}
      <FigurasScoreCard
        key={`${compId}-${juezId}-${isConfirmed ? "ok" : "edit"}-${valCommitted ?? "empty"}`}
        state={state}
        enviarEvento={enviarEvento}
        juezId={juezId}
        miCriterio={miCriterio}
        comp={comp}
      />
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// FIGURAS — Pantalla Pública
// ══════════════════════════════════════════════════════════════════════════════
function FigurasPantalla({ state, tatamiId }: { state: FigurasState; tatamiId: string }) {
  const { t } = useI18n();
  const ranking = rankingFiguras(state);
  const nombreCategoria = state._nombre_categoria || state.nombre_categoria || "Figuras";
  const puntuacionesCompletas = figurasPuntuacionesCompletas(state);
  // El podio aparece automáticamente cuando TODOS los competidores fueron
  // calificados en todos sus criterios (el backend finaliza solo al completar).
  const shouldShowPodio = state.finalizado || puntuacionesCompletas;
  const activeComp = state.competidores.find((c) => c.id === state.competidor_activo_id);

  // ── Sonidos (ver lib/sfx.ts): nuevo turno, nota registrada y podio final.
  // El toggle 🔊 desbloquea el audio (política de autoplay). Se comparan
  // VALORES prev/actual: un resync tras reconectar no repite sonidos. ──
  const [soundOn, setSoundOn] = useState(false);
  function toggleSound() {
    if (!soundOn) activarAudio();
    setSoundOn(!soundOn);
  }
  const notasConfirmadas = Object.values(state.puntuaciones_confirmadas || {})
    .reduce((n, porJuez) => n + Object.values(porJuez || {}).filter(Boolean).length, 0);
  const sfxFigPrevRef = useRef({
    activo: state.competidor_activo_id,
    notas: notasConfirmadas,
    podio: shouldShowPodio,
  });
  useEffect(() => {
    const prev = sfxFigPrevRef.current;
    const ahora = {
      activo: state.competidor_activo_id,
      notas: notasConfirmadas,
      podio: shouldShowPodio,
    };
    sfxFigPrevRef.current = ahora;
    if (!soundOn) return;
    if (ahora.podio && !prev.podio) {
      sfxPodio();
      return;
    }
    if (ahora.activo != null && ahora.activo !== prev.activo) sfxTurnoFiguras();
    if (ahora.notas > prev.notas) sfxNotaFiguras();
  }, [state, soundOn, notasConfirmadas, shouldShowPodio]);
  const juecesActivos = juecesActivosFiguras(state);
  const activeCompId = activeComp ? String(activeComp.id) : "";
  const activeTotal = ranking.find((r) => r.id === activeComp?.id)?.total ?? 0;
  // "Comparten puesto" solo cuando hay categoría especial: la comparten los
  // especiales y el 1° del podio normal
  const hayEspeciales = ranking.some((r) => r.especial);
  // En la vista de puntuación en vivo el logo va sobre "EN TURNO", no arriba
  const vistaEnVivo = !shouldShowPodio && Boolean(activeComp) && ranking.length > 0;

  return (
    <div style={{ height: "100dvh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{
        textAlign: "center", padding: "14px 20px",
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-card)",
        position: "relative",
      }}>
        {/* Toggle de sonido (turnos, notas y podio) */}
        <button
          type="button"
          onClick={toggleSound}
          title={soundOn ? t("tat.pant.sonidoOnTitle") : t("tat.pant.sonidoOffTitle")}
          style={{
            position: "absolute", top: 10, right: 12,
            background: "none", border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)", padding: "3px 10px",
            color: soundOn ? "var(--gold)" : "var(--text-dim)",
            cursor: "pointer", fontSize: "0.82rem", fontFamily: "var(--font-body)",
            fontWeight: 700, zIndex: 2,
          }}
        >
          {soundOn ? t("tat.pant.sonidoOn") : t("tat.pant.sonidoOff")}
        </button>
        {!vistaEnVivo && <Logo fontSize="clamp(1.5rem, 4vw, 2rem)" />}
        {state._campeonato_nombre && (
          <div style={{
            fontSize: "0.85rem", color: "var(--text-muted)", fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.12em", marginTop: 2,
          }}>{state._campeonato_nombre}</div>
        )}
        <div style={{
          fontFamily: "var(--font-display)", fontSize: "clamp(2rem,4vw,3.5rem)",
          color: "var(--gold)", letterSpacing: "0.15em", lineHeight: 1,
          marginTop: 8,
        }}>
          {t("tat.tatamiMayus")} {tatamiId}
        </div>
        <div style={{
          fontFamily: "var(--font-body)", fontSize: "0.9rem",
          color: "var(--gold)", fontWeight: 700, textTransform: "uppercase",
          letterSpacing: "0.15em", marginTop: 2,
        }}>{nombreCategoria}</div>
        {state.descripcion && (
          <div style={{
            fontSize: "clamp(0.875rem, 1.6vw, 1.05rem)", color: "var(--text-muted)",
            fontWeight: 600, marginTop: 4,
          }}>{state.descripcion}</div>
        )}
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "12px 20px" }}>
        {ranking.length === 0 ? (
          <div style={{ textAlign: "center", marginTop: "25%", color: "var(--text-dim)" }}>
            <p style={{ fontSize: "1.6rem" }}>{t("tat.pant.esperandoParticipantes")}</p>
          </div>
        ) : !shouldShowPodio ? (
          activeComp ? (
            /* ── Competidor en turno: puntuación en vivo por criterio ── */
            <div style={{
              height: "100%", display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", textAlign: "center",
              maxWidth: 1100, margin: "0 auto", gap: "clamp(10px, 2vh, 24px)",
            }}>
              <div>
                {/* Logo protagonista, como en el marcador de combates */}
                <Logo
                  soloImagen
                  fontSize="clamp(3.2rem, 16vh, 10.5rem)"
                  style={{ marginBottom: 8 }}
                />
                <div style={{ fontSize: "0.9rem", textTransform: "uppercase", letterSpacing: "0.16em", color: "var(--text-dim)", fontWeight: 800 }}>
                  {t("tat.pant.enTurno")}
                </div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: "clamp(2.2rem,5.5vw,4.5rem)", color: "var(--text)", lineHeight: 1.05 }}>
                  {activeComp.nombre}
                </div>
                {activeComp.club && (
                  <div style={{ marginTop: 4, color: "var(--text-muted)", fontSize: "clamp(0.9rem,1.5vw,1.1rem)" }}>
                    {activeComp.club}
                  </div>
                )}
              </div>

              {/* Criterios según jueces activos */}
              <div style={{
                display: "grid",
                gridTemplateColumns: `repeat(auto-fit, minmax(min(150px, 100%), 1fr))`,
                gap: 12, width: "100%",
              }}>
                {juecesActivos.map((juezId) => {
                  const idx = Number(juezId.slice(1)) - 1;
                  const criterio = state.criterios[idx];
                  if (!criterio) return null;
                  const valor = state.puntuaciones[activeCompId]?.[juezId];
                  const confirmado = Boolean(state.puntuaciones_confirmadas?.[activeCompId]?.[juezId]);
                  const tieneNota = valor !== undefined && valor !== null;
                  return (
                    <div key={juezId} className="animate-fade" style={{
                      padding: "clamp(10px, 2vh, 20px) 12px",
                      background: confirmado ? "rgba(0, 212, 114, 0.08)" : "var(--bg-card)",
                      border: `1.5px solid ${confirmado ? "var(--green-border)" : "var(--border)"}`,
                      borderRadius: "var(--radius)",
                      display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                    }}>
                      <div style={{
                        fontSize: "clamp(0.78rem,1.2vw,0.95rem)", fontWeight: 800,
                        textTransform: "uppercase", letterSpacing: "0.1em",
                        color: "var(--text-muted)",
                      }}>
                        {criterio.nombre}
                      </div>
                      <div style={{
                        fontFamily: "var(--font-display)",
                        fontSize: "clamp(2.2rem,4.5vw,4rem)", lineHeight: 1,
                        color: tieneNota ? (confirmado ? "var(--green)" : "var(--text)") : "var(--text-dim)",
                      }}>
                        {tieneNota ? Number(valor).toFixed(2) : "—"}
                      </div>
                      <div style={{ fontSize: "0.78rem", color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
                        {juezId.toUpperCase()}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Total acumulado */}
              <div style={{
                display: "flex", alignItems: "baseline", gap: 14,
                padding: "clamp(8px,1.5vh,16px) clamp(20px,4vw,48px)",
                background: "rgba(240,184,0,0.08)",
                border: "1.5px solid var(--gold-border)",
                borderRadius: "var(--radius-lg)",
              }}>
                <span style={{ fontSize: "clamp(0.875rem,1.4vw,1.1rem)", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--text-muted)" }}>
                  {t("tat.pant.total")}
                </span>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "clamp(3rem,7vw,6rem)", color: "var(--gold)", lineHeight: 1 }}>
                  {activeTotal.toFixed(2)}
                </span>
              </div>
            </div>
          ) : (
            /* ── Sin competidor activo: esperando ── */
            <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", color: "var(--text-muted)" }}>
              <div style={{ fontFamily: "var(--font-display)", fontSize: "clamp(2rem,5vw,4rem)", color: "var(--gold)", letterSpacing: "0.08em" }}>
                {t("tat.pant.puntuacionesCurso")}
              </div>
              <div style={{ marginTop: 12, fontSize: "clamp(0.9rem,1.6vw,1.2rem)", color: "var(--text-dim)" }}>
                {puntuacionesCompletas
                  ? t("tat.pant.todasRegistradas")
                  : t("tat.pant.esperandoSiguiente")}
              </div>
            </div>
          )
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 960, margin: "0 auto" }}>
            {ranking.map((comp) => {
              const isActive = state.competidor_activo_id === comp.id;
              const esPrimero = comp.puesto === 1;
              return (
                <div key={comp.id} className="animate-fade" style={{
                  display: "flex", alignItems: "center", gap: 16,
                  padding: "16px 24px",
                  background: isActive ? "rgba(240,184,0,0.12)" : (esPrimero ? "rgba(240,184,0,0.08)" : "var(--bg-card)"),
                  border: `1.5px solid ${isActive ? "var(--gold)" : (esPrimero ? "var(--gold-border)" : "var(--border)")}`,
                  borderRadius: "var(--radius)",
                  boxShadow: esPrimero || isActive ? "var(--shadow-gold)" : undefined,
                }}>
                  <span style={{
                    fontFamily: "var(--font-display)", fontSize: "clamp(3rem,6vw,5rem)",
                    color: colorPuesto(comp.puesto, comp.especial),
                    minWidth: 80, textAlign: "center", lineHeight: 1,
                  }}>{comp.puesto}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontFamily: "var(--font-display)",
                      fontSize: "clamp(2rem,4vw,3.5rem)",
                      letterSpacing: "0.04em", lineHeight: 1,
                      overflowWrap: "anywhere",
                      color: isActive || esPrimero ? "var(--gold)" : "var(--text)",
                    }}>
                      {comp.nombre}
                    </div>
                    {comp.club && (
                      <div style={{
                        fontSize: "clamp(0.9rem,1.6vw,1.1rem)",
                        color: "var(--text-muted)", marginTop: 4,
                        overflowWrap: "anywhere",
                      }}>
                        {comp.club}
                      </div>
                    )}
                    {(comp.especial || comp.empate || (hayEspeciales && comp.puesto === 1)) && (
                      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 6 }}>
                        {comp.especial && (
                          <span className="badge badge-gold" style={{ fontSize: "clamp(0.72rem,1.2vw,0.85rem)" }}>
                            {t("tat.pant.catEspecial")}
                          </span>
                        )}
                        {hayEspeciales && comp.puesto === 1 && (
                          <span className="badge badge-gold" style={{ fontSize: "clamp(0.72rem,1.2vw,0.85rem)" }}>
                            {t("tat.pant.compartenPuesto")}
                          </span>
                        )}
                        {comp.empate && (
                          <span className="badge" style={{
                            fontSize: "clamp(0.72rem,1.2vw,0.85rem)",
                            background: "rgba(255,140,0,0.12)",
                            border: "1px solid rgba(255,140,0,0.4)",
                            color: "var(--orange)",
                          }}>
                            {t("tat.pant.desempatePendiente")}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  <div style={{
                    fontFamily: "var(--font-display)",
                    fontSize: "clamp(3rem,5vw,5rem)",
                    color: esPrimero || isActive ? "var(--gold)" : "var(--text)",
                    letterSpacing: "0.04em",
                  }}>
                    {comp.total.toFixed(2)}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// COMBATE — Pantalla Pública
// ══════════════════════════════════════════════════════════════════════════════
function CombatePantalla({
  state, tatamiId, connected,
}: {
  state: CombateState; tatamiId: string; connected: boolean;
}) {
  const { t } = useI18n();
  const totalHong = marcadorDisplay(state, "hong");
  const totalChung = marcadorDisplay(state, "chung");

  const cronoClass = !state.activo ? "pause"
    : state.segundos <= 5 ? "urgente-5"
    : state.segundos <= 10 ? "urgente"
    : "activo";

  // ── Sonidos de la pantalla pública (sintetizados, ver lib/sfx.ts). El
  // toggle 🔊 crea/reanuda el AudioContext (política de autoplay de los
  // navegadores: se necesita un toque del usuario antes de sonar) ──
  const [soundOn, setSoundOn] = useState(false);

  function toggleSound() {
    if (!soundOn) activarAudio();
    setSoundOn(!soundOn);
  }

  // Un solo efecto compara el estado previo con el nuevo y dispara el sonido
  // que corresponda. Se comparan VALORES (no eventos): así un resync completo
  // tras reconectar no repite sonidos, y solo los AUMENTOS suenan (un
  // deshacer/anular o un combate nuevo bajan valores en silencio).
  const sfxPrevRef = useRef({
    hong: marcadorFinal(state, "hong"),
    chung: marcadorFinal(state, "chung"),
    faltas: (state.kyongHong || 0) + (state.kyongChung || 0)
      + (state.faltasHong || 0) + (state.faltasChung || 0),
    oro: Boolean(state.oroPendienteAprobacion),
    ganador: Boolean(state.ganadorPendienteCierre || state.ganadorManualColor),
    segundos: state.segundos,
  });

  useEffect(() => {
    const prev = sfxPrevRef.current;
    const ahora = {
      hong: marcadorFinal(state, "hong"),
      chung: marcadorFinal(state, "chung"),
      faltas: (state.kyongHong || 0) + (state.kyongChung || 0)
        + (state.faltasHong || 0) + (state.faltasChung || 0),
      oro: Boolean(state.oroPendienteAprobacion),
      ganador: Boolean(state.ganadorPendienteCierre || state.ganadorManualColor),
      segundos: state.segundos,
    };
    sfxPrevRef.current = ahora;
    if (!soundOn) return;

    // Cronómetro: gong al llegar a 0; doble tick al entrar a los últimos 10 s
    if (prev.segundos > 0 && ahora.segundos === 0) sfxGong();
    else if (state.activo && prev.segundos > 10 && ahora.segundos <= 10 && ahora.segundos > 0) {
      sfxAviso10s();
    }

    // Ganador declarado: fanfarria (y silenciar el beep del punto que lo causó)
    if (ahora.ganador && !prev.ganador) {
      sfxGanador();
    } else {
      if (ahora.hong > prev.hong) sfxPuntoHong();
      if (ahora.chung > prev.chung) sfxPuntoChung();
    }

    if (ahora.faltas > prev.faltas) sfxFalta();
    if (ahora.oro && !prev.oro) sfxOro();
  }, [state, soundOn]);

  // ── Árbol de la llave en pantalla pública (antes/entre combates) ──
  if (state._mostrar_arbol && state._llave_arbol) {
    return (
      <div style={{ height: "100dvh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{
          textAlign: "center", padding: "12px 20px",
          borderBottom: "1px solid var(--border)", background: "var(--bg-card)",
        }}>
          <Logo fontSize="clamp(1.4rem, 3.5vw, 1.8rem)" />
          {state._campeonato_nombre && (
            <div style={{
              fontSize: "0.82rem", color: "var(--text-muted)", fontWeight: 700,
              textTransform: "uppercase", letterSpacing: "0.12em", marginTop: 2,
            }}>{state._campeonato_nombre} · {t("camp.tatami")} {tatamiId}</div>
          )}
          <div style={{
            fontFamily: "var(--font-display)", fontSize: "clamp(1.6rem,3.5vw,3rem)",
            color: "var(--gold)", letterSpacing: "0.1em", lineHeight: 1.05, marginTop: 6,
          }}>
            {state._llave_arbol.nombre}
          </div>
          {state._combate_llave && (
            <div style={{
              fontSize: "clamp(0.82rem,1.4vw,1rem)", color: "var(--text)",
              fontWeight: 700, marginTop: 4,
            }}>
              {t("tat.pant.proximo")} ({state._combate_llave.ronda_nombre}):{" "}
              <span style={{ color: "var(--hong-light)" }}>{state._combate_llave.comp1.nombre}</span>
              {" vs "}
              <span style={{ color: "var(--chung-light)" }}>{state._combate_llave.comp2.nombre}</span>
            </div>
          )}
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: "clamp(10px,2vh,24px) clamp(12px,2vw,28px)" }}>
          {state._llave_arbol.estructura.campeon && (
            <div style={{ marginBottom: "clamp(14px,3vh,28px)" }}>
              <PodioLlave estructura={state._llave_arbol.estructura} grande titulo={t("tat.pant.podioFinal")} />
            </div>
          )}
          <BracketTree
            estructura={state._llave_arbol.estructura}
            variant="pantalla"
            destacar={state._combate_llave
              ? { ronda: state._combate_llave.ronda, partido: state._combate_llave.partido }
              : null}
          />
        </div>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "8px 24px", borderTop: "1px solid var(--border)",
          fontSize: "0.85rem", color: "var(--text-dim)",
        }}>
          <Logo fontSize="1.1rem" />
          <span>{t("camp.tatami")} {tatamiId}</span>
          <span>
            <span className={`status-dot ${connected ? "online" : "offline"}`} />
            {connected ? t("tat.envivo") : t("tat.desconectado")}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div style={{ height: "100dvh", display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>
      {/* Main scoreboard */}
      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center" }}>
        {/* HONG */}
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", padding: "20px 16px",
          borderRight: "1px solid var(--border)", height: "100%",
        }}>
          <div style={{
            fontFamily: "var(--font-display)", fontSize: "clamp(1.2rem,3vw,2.2rem)",
            color: "var(--hong-light)", letterSpacing: "0.06em", textTransform: "uppercase",
          }}>{state.nombreHong}</div>
          <div
            className="proy-score hong"
            key={`h-${totalHong}`}
            style={{ animation: "boom 0.3s ease-out" }}
          >
            {totalHong}
          </div>
          <DesgloseMarcador state={state} color="hong" grande />
          <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
            {state.kyongHong > 0 && <span style={{ color: "var(--orange)", fontSize: "0.9rem" }}>K:{state.kyongHong}</span>}
            {state.faltasHong > 0 && <span style={{ color: "var(--red-alert)", fontSize: "0.9rem" }}>G:{state.faltasHong}</span>}
          </div>
        </div>

        {/* CENTER */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "0 20px" }}>
          {/* Logo encima del nombre del campeonato — protagonista del centro */}
          <Logo
            soloImagen
            fontSize="clamp(3.2rem, 16vh, 10.5rem)"
            style={{ marginBottom: 8 }}
          />
          {state._campeonato_nombre && (
            <div style={{
              fontSize: "clamp(0.75rem,1.2vw,0.9rem)", color: "var(--text-muted)",
              fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.14em",
              marginBottom: 4,
            }}>
              {state._campeonato_nombre}
            </div>
          )}
          <div style={{
            fontSize: "clamp(2rem,4vw,3.5rem)", fontFamily: "var(--font-display)",
            color: "var(--gold)", letterSpacing: "0.15em", marginBottom: 4,
            lineHeight: 1
          }}>
            {t("tat.tatamiMayus")} {tatamiId}
          </div>
          {typeof state._num_combate === "number" && state._num_combate > 0 && (
            <div style={{
              fontSize: "clamp(0.78rem,1.4vw,1rem)", fontWeight: 800,
              color: "var(--text-muted)", textTransform: "uppercase",
              letterSpacing: "0.18em", marginBottom: 10,
            }}>
              {t("tat.combateNumPant", { n: state._num_combate })}
            </div>
          )}
          <div className={`crono-display ${cronoClass}`} style={{ fontSize: "clamp(2.5rem,7vw,6rem)" }}>
            {formatTime(state.segundos)}
          </div>
          <div style={{
            fontFamily: "var(--font-display)", fontSize: "clamp(0.78rem,1.5vw,1.1rem)",
            letterSpacing: "0.2em",
            color: state.ronda === "oro" ? "var(--gold)" : "var(--text-muted)",
            animation: state.ronda === "oro" ? "glow-oro 1.2s infinite alternate" : undefined,
            padding: "4px 12px",
            border: state.ronda === "oro" ? "1.5px solid var(--gold)" : "1px solid transparent",
            borderRadius: 20,
            marginTop: 6,
          }}>
            {RONDAS_CLAVE[state.ronda] ? t(RONDAS_CLAVE[state.ronda]) : state.ronda}
          </div>
          {state._combate_llave && (
            <div style={{
              fontSize: "clamp(0.75rem,1.2vw,0.95rem)", fontWeight: 800,
              color: "var(--gold)", textTransform: "uppercase",
              letterSpacing: "0.1em", marginTop: 8,
            }}>
              {state._combate_llave.nombre} · {state._combate_llave.ronda_nombre}
            </div>
          )}
        </div>

        {/* CHUNG */}
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", padding: "20px 16px",
          borderLeft: "1px solid var(--border)", height: "100%",
        }}>
          <div style={{
            fontFamily: "var(--font-display)", fontSize: "clamp(1.2rem,3vw,2.2rem)",
            color: "var(--chung-light)", letterSpacing: "0.06em", textTransform: "uppercase",
          }}>{state.nombreChung}</div>
          <div className="proy-score chung" key={`c-${totalChung}`} style={{ animation: "boom 0.3s ease-out" }}>
            {totalChung}
          </div>
          <DesgloseMarcador state={state} color="chung" grande />
          <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
            {state.kyongChung > 0 && <span style={{ color: "var(--orange)", fontSize: "0.9rem" }}>K:{state.kyongChung}</span>}
            {state.faltasChung > 0 && <span style={{ color: "var(--red-alert)", fontSize: "0.9rem" }}>G:{state.faltasChung}</span>}
          </div>
        </div>
      </div>

      {/* Próximos combates de la llave (para que se vayan preparando) */}
      {(state._proximos_llave?.length ?? 0) > 0 && (
        <div style={{
          display: "flex", gap: "clamp(10px,2vw,24px)", alignItems: "center",
          justifyContent: "center", flexWrap: "wrap", padding: "7px 16px",
          borderTop: "1px solid var(--border)",
          fontSize: "clamp(0.8rem,1.4vw,1rem)",
        }}>
          <span style={{ color: "var(--gold)", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.12em" }}>
            {t("tat.pant.proximos")}
          </span>
          {state._proximos_llave!.map((p, i) => (
            <span key={`${p.comp1}-${p.comp2}-${i}`} style={{ color: "var(--text-muted)", whiteSpace: "nowrap" }}>
              <span style={{ color: "var(--hong-light)", fontWeight: 700 }}>{p.comp1}</span>
              {" vs "}
              <span style={{ color: "var(--chung-light)", fontWeight: 700 }}>{p.comp2}</span>
              <span style={{ color: "var(--text-dim)" }}> ({p.ronda_nombre})</span>
            </span>
          ))}
        </div>
      )}

      {/* Footer */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "8px 24px", borderTop: "1px solid var(--border)",
        fontSize: "0.85rem", color: "var(--text-dim)",
      }}>
        <Logo fontSize="1.1rem" />
        <span>{t("camp.tatami")} {tatamiId}</span>
        <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            type="button"
            onClick={toggleSound}
            title={soundOn ? t("tat.pant.sonidoOnTitle") : t("tat.pant.sonidoOffTitle")}
            style={{
              background: "none", border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)", padding: "3px 10px",
              color: soundOn ? "var(--gold)" : "var(--text-dim)",
              cursor: "pointer", fontSize: "0.82rem", fontFamily: "var(--font-body)",
              fontWeight: 700,
            }}
          >
            {soundOn ? t("tat.pant.sonidoOn") : t("tat.pant.sonidoOff")}
          </button>
          <span>
            <span className={`status-dot ${connected ? "online" : "offline"}`} />
            {connected ? t("tat.envivo") : t("tat.desconectado")}
          </span>
        </span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// COMBATE — Juez Esquina (botones VERTICALES, solo sus puntos)
// ══════════════════════════════════════════════════════════════════════════════
function CombateJuez({
  state, rol, enviarEvento, pendingEvents, connected, onFlash, registroResuelto,
}: {
  state: CombateState; rol: string;
  enviarEvento: (accion: string, datos?: Record<string, unknown>) => void;
  pendingEvents: number; connected: boolean;
  onFlash: (ico: string, txt: string) => void;
  registroResuelto?: { rol: string; aplicado: boolean; n: number } | null;
}) {
  const { t } = useI18n();
  const miPuntaje = state.jueces?.[rol] || { hong: 0, chung: 0 };
  const params = useParams();
  const offline = useRegistroOffline(`dinamyt_offline_${params.id}_${rol}`);

  // Al RECONECTAR, el registro local se envía SOLO a la mesa como propuesta:
  // el Juez Central lo aplica o lo descarta (adiós al reingreso manual).
  const propuestoRef = useRef(false);
  useEffect(() => {
    if (!connected) { propuestoRef.current = false; return; }
    if (propuestoRef.current) return;
    const puntos = offline.entradas.filter((e) => e.color && (e.pts || 0) > 0);
    if (puntos.length === 0) return;
    propuestoRef.current = true;
    enviarEvento("proponer_registro_local", { entradas: puntos });
    onFlash("📤", t("tat.flash.registroEnviado"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected, offline.entradas.length]);

  // La mesa resolvió mi registro: limpiar la libreta local y avisar
  const ultimoResueltoRef = useRef(0);
  useEffect(() => {
    if (!registroResuelto || registroResuelto.rol !== rol) return;
    if (registroResuelto.n === ultimoResueltoRef.current) return;
    ultimoResueltoRef.current = registroResuelto.n;
    offline.limpiar();
    onFlash(
      registroResuelto.aplicado ? "✅" : "🗑",
      registroResuelto.aplicado ? t("tat.flash.mesaAplico") : t("tat.flash.mesaDescarto"),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [registroResuelto]);
  const nombresListos = competidoresConNombre(state);
  // Bloqueado con ganador declarado, punto de oro en espera o alerta de
  // superioridad abierta (el combate queda en pausa hasta que el JC la cierre).
  // Sin conexión NO se bloquea: los puntos van al registro local.
  const combateCerrado = Boolean(state.ganadorManualColor);
  const juezBloqueado = connected && (!nombresListos || Boolean(state.ganadorPendienteCierre)
    || combateCerrado || Boolean(state.oroPendienteAprobacion)
    || Boolean(state.alerta12Data));
  // Rol fuera de la configuración actual (ej: j3 en combate de 2 jueces)
  const rolNum = rol.startsWith("j") ? Number(rol.slice(1)) : 0;
  const rolInactivo = rolNum > (state.numJueces || 4);

  // "label" es el nombre CANÓNICO (en español) que viaja al servidor y queda
  // en el historial/reportes: NO cambia con el idioma del juez. "clave" es
  // solo para mostrar el botón en el idioma del dispositivo.
  const PUNTOS: { pts: number; label: string; clave: ClaveTexto }[] = [
    { pts: 1, label: "CUERPO", clave: "tat.pts.cuerpo" },
    { pts: 2, label: "GIRO / PAT. CABEZA", clave: "tat.pts.giroPatCabeza" },
    { pts: 3, label: "GIRO CABEZA", clave: "tat.pts.giroCabeza" },
  ];

  function anotar(color: "hong" | "chung", pts: number, label: string) {
    // Sin conexión: el punto se guarda en el teléfono, no se pierde.
    // Sin flash: el marcador local del panel superior ya refleja el cambio.
    if (!connected) {
      offline.agregar({ etiqueta: `+${pts} ${label}`, color, pts });
      return;
    }
    if (!nombresListos) {
      onFlash("⚠️", t("tat.flash.nombresRequeridos"));
      return;
    }
    if (combateCerrado) {
      onFlash("🏆", t("tat.flash.combateFinalizado"));
      return;
    }
    onFlash(color === "hong" ? "🔴" : "🔵", `+${pts} JEUMSU`);
    enviarEvento("punto_juez", { juez: rol, color, pts, nombre: label });
  }

  if (rolInactivo) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text-dim)" }}>
        <p style={{ fontSize: "1.4rem", marginBottom: 8 }}>
          {t("tat.juez.noParticipa", { rol: rol.toUpperCase() })}
        </p>
        <p style={{ fontSize: "0.9rem" }}>
          {t("tat.juez.noParticipaDesc", { n: state.numJueces })}
        </p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 520, margin: "0 auto", padding: "12px 14px", minHeight: "calc(100dvh - 48px)", display: "flex", flexDirection: "column" }}>
      {/* Mini crono + nombre rol */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 10, padding: "8px 14px",
        background: "var(--bg-card)", borderRadius: "var(--radius)",
        border: "1px solid var(--border)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className={`status-dot ${connected ? "online" : "offline"}`} />
          <span style={{ fontFamily: "var(--font-display)", fontSize: "1rem", letterSpacing: "0.06em" }}>
            {rol.toUpperCase()} · T{state.segundosMax}s
          </span>
        </div>
        <CronoDisplay segundos={state.segundos} activo={state.activo} segundosMax={state.segundosMax} />
      </div>

      {/* Arriba solo el aviso y el marcador local; el detalle va al final */}
      <PanelRegistroOffline
        modo="resumen"
        conectado={connected}
        entradas={offline.entradas}
        onDeshacer={offline.deshacer}
        onLimpiar={offline.limpiar}
        descripcion={connected
          ? t("tat.juez.reconectadoDesc")
          : t("tat.juez.offDesc")}
      />

      {/* Aviso de combate cerrado o punto de oro en espera */}
      {connected && (combateCerrado || state.oroPendienteAprobacion) && (
        <div style={{
          marginBottom: 10, padding: "8px 12px", borderRadius: "var(--radius)",
          border: "1px solid var(--gold)", background: "rgba(212,175,55,0.08)",
          color: "var(--gold)", fontWeight: 700, textAlign: "center", fontSize: "0.9rem",
        }}>
          {state.oroPendienteAprobacion
            ? t("tat.oroEsperaJuez")
            : t("tat.cerradoEsperaJuez")}
        </div>
      )}

      {/* Mis puntos — solo los propios */}
      <div className="grid-2" style={{ marginBottom: 10 }}>
        <div className="card card-hong" style={{ textAlign: "center", padding: "10px 8px" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--hong-light)", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em" }}>
            {state.nombreHong}
          </div>
          <div style={{ fontFamily: "var(--font-display)", fontSize: "2.5rem", color: "var(--hong-vivid)" }}>
            {miPuntaje.hong}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>{t("tat.juez.misPuntos")}</div>
        </div>
        <div className="card card-chung" style={{ textAlign: "center", padding: "10px 8px" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--chung-light)", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em" }}>
            {state.nombreChung}
          </div>
          <div style={{ fontFamily: "var(--font-display)", fontSize: "2.5rem", color: "var(--chung-vivid)" }}>
            {miPuntaje.chung}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>{t("tat.juez.misPuntos")}</div>
        </div>
      </div>

      {/* Botones VERTICALES en 2 columnas */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, flex: 1 }}>
        {/* Columna HONG */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="card-title" style={{ color: "var(--hong-light)", textAlign: "center" }}>
            HONG
          </div>
          {PUNTOS.map((p) => (
            <button
              key={`h${p.pts}`}
              className="combat-btn hong"
              style={{ flex: 1, opacity: (connected && state.oroResuelto) || juezBloqueado ? 0.5 : 1 }}
              onClick={() => anotar("hong", p.pts, p.label)}
              disabled={(connected && state.oroResuelto) || juezBloqueado}
            >
              <span className="pts">+{p.pts}</span>
              <span className="label">{t(p.clave)}</span>
            </button>
          ))}
          <button
            className="btn btn-danger"
            style={{ marginTop: 4, padding: "10px 6px", fontSize: "0.88rem", opacity: (connected && state.oroResuelto) || juezBloqueado ? 0.5 : 1 }}
            disabled={(connected && state.oroResuelto) || juezBloqueado}
            onClick={() => {
              if (!connected) { offline.deshacer(); return; }
              const hay = state.historial?.some((h) => h.juez === rol && h.color === "hong");
              if (hay) enviarEvento("deshacer_juez", { juez: rol, color: "hong" });
              else onFlash("⚠️", t("tat.flash.nadaDeshacer"));
            }}
          >
            {t("tat.deshacer")}
          </button>
        </div>

        {/* Columna CHUNG */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="card-title" style={{ color: "var(--chung-light)", textAlign: "center" }}>
            CHUNG
          </div>
          {PUNTOS.map((p) => (
            <button
              key={`c${p.pts}`}
              className="combat-btn chung"
              style={{ flex: 1, opacity: (connected && state.oroResuelto) || juezBloqueado ? 0.5 : 1 }}
              onClick={() => anotar("chung", p.pts, p.label)}
              disabled={(connected && state.oroResuelto) || juezBloqueado}
            >
              <span className="pts">+{p.pts}</span>
              <span className="label">{t(p.clave)}</span>
            </button>
          ))}
          <button
            className="btn btn-danger"
            style={{ marginTop: 4, padding: "10px 6px", fontSize: "0.88rem", opacity: (connected && state.oroResuelto) || juezBloqueado ? 0.5 : 1 }}
            disabled={(connected && state.oroResuelto) || juezBloqueado}
            onClick={() => {
              if (!connected) { offline.deshacer(); return; }
              const hay = state.historial?.some((h) => h.juez === rol && h.color === "chung");
              if (hay) enviarEvento("deshacer_juez", { juez: rol, color: "chung" });
              else onFlash("⚠️", t("tat.flash.nadaDeshacer"));
            }}
          >
            {t("tat.deshacer")}
          </button>
        </div>
      </div>

      {pendingEvents > 0 && (
        <div style={{ textAlign: "center", marginTop: 8 }}>
          <span className="status-dot pending" />
          <span style={{ color: "var(--orange)", fontSize: "0.85rem" }}>{t("tat.pendientes", { n: pendingEvents })}</span>
        </div>
      )}

      {/* Detalle del registro local: al final para no estorbar la puntuación */}
      <div style={{ marginTop: 10 }}>
        <PanelRegistroOffline
          modo="detalle"
          conectado={connected}
          entradas={offline.entradas}
          onDeshacer={offline.deshacer}
          onLimpiar={offline.limpiar}
          descripcion=""
        />
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════════════════════
// REGISTRO LOCAL SIN CONEXIÓN
// Si se va el internet, cada juez sigue puntuando en su dispositivo: las
// anotaciones se guardan en localStorage (sobreviven recargas) y al final se
// muestran a la mesa de control, que suma manualmente y el JC da el ganador.
// ══════════════════════════════════════════════════════════════════════════════
interface EntradaOffline {
  ts: number;
  etiqueta: string;
  color?: "hong" | "chung";
  pts?: number;
}

function useRegistroOffline(clave: string) {
  const [entradas, setEntradas] = useState<EntradaOffline[]>([]);

  // Carga al montar (en efecto y no en el inicializador para no romper la
  // hidratación de SSR, donde localStorage no existe).
  useEffect(() => {
    try {
      const raw = localStorage.getItem(clave);
      if (raw) setEntradas(JSON.parse(raw));
    } catch { /* almacenamiento no disponible: el registro vive solo en memoria */ }
  }, [clave]);

  // Actualización funcional + escritura inmediata: sin closures viejos, cada
  // cambio queda en localStorage al instante (sobrevive recargas y salidas).
  function persistir(transformar: (prev: EntradaOffline[]) => EntradaOffline[]) {
    setEntradas((prev) => {
      const siguientes = transformar(prev);
      try { localStorage.setItem(clave, JSON.stringify(siguientes)); } catch { /* */ }
      return siguientes;
    });
  }

  return {
    entradas,
    agregar: (e: Omit<EntradaOffline, "ts">) =>
      persistir((prev) => [...prev, { ...e, ts: Date.now() }]),
    deshacer: () => persistir((prev) => prev.slice(0, -1)),
    limpiar: () => persistir(() => []),
  };
}

function PanelRegistroOffline({
  conectado, entradas, onDeshacer, onLimpiar, descripcion, modo = "completo",
}: {
  conectado: boolean;
  entradas: EntradaOffline[];
  onDeshacer: () => void;
  onLimpiar: () => void;
  descripcion: string;
  /**
   * "resumen": solo aviso + marcador local (va arriba, no estorba).
   * "detalle": lista de anotaciones + deshacer/borrar (va abajo).
   * "completo": ambos.
   */
  modo?: "completo" | "resumen" | "detalle";
}) {
  const { t } = useI18n();
  const [confirmandoBorrado, setConfirmandoBorrado] = useState(false);
  // Visible mientras no haya conexión, o mientras quede un registro pendiente
  // de conciliar con la mesa después de reconectar.
  if (conectado && entradas.length === 0) return null;
  if (modo === "detalle" && entradas.length === 0) return null;

  const verResumen = modo !== "detalle";
  const verDetalle = modo !== "resumen";
  const totalHong = entradas.filter((e) => e.color === "hong").reduce((s, e) => s + (e.pts || 0), 0);
  const totalChung = entradas.filter((e) => e.color === "chung").reduce((s, e) => s + (e.pts || 0), 0);
  const hayPuntos = entradas.some((e) => e.color);
  const hora = (ts: number) =>
    new Date(ts).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  return (
    <div style={{
      marginBottom: 10, padding: "12px 14px", borderRadius: "var(--radius)",
      border: `2px solid ${conectado ? "var(--gold)" : "var(--red-alert)"}`,
      background: conectado ? "rgba(212,175,55,0.08)" : "rgba(232,0,42,0.08)",
    }}>
      {verResumen ? (
        <>
          <div style={{
            fontWeight: 800, fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase",
            color: conectado ? "var(--gold)" : "var(--red-alert)", marginBottom: 6,
          }}>
            {conectado ? t("tat.off.pendiente") : t("tat.off.sinConexion")}
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginBottom: hayPuntos ? 10 : 0 }}>
            {descripcion}
          </p>
          {hayPuntos && (
            <div style={{ display: "flex", gap: 16, justifyContent: "center" }}>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--hong-light)", fontWeight: 800 }}>HONG</div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: "2rem", color: "var(--hong-vivid)" }}>
                  {totalHong}
                </div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--chung-light)", fontWeight: 800 }}>CHUNG</div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: "2rem", color: "var(--chung-vivid)" }}>
                  {totalChung}
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <div style={{
          fontWeight: 800, fontSize: "0.88rem", letterSpacing: "0.06em", textTransform: "uppercase",
          color: conectado ? "var(--gold)" : "var(--red-alert)", marginBottom: 8,
        }}>
          {t("tat.off.registro", { n: entradas.length })}
        </div>
      )}

      {verDetalle && entradas.length > 0 && (
        <>
          <div style={{ maxHeight: 160, overflowY: "auto", margin: "10px 0", display: "flex", flexDirection: "column", gap: 2 }}>
            {[...entradas].reverse().map((e) => (
              <div key={e.ts} style={{ fontSize: "0.85rem", color: "var(--text-muted)", display: "flex", gap: 8 }}>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-dim)" }}>{hora(e.ts)}</span>
                {e.color && (
                  <span style={{ color: e.color === "hong" ? "var(--hong-light)" : "var(--chung-light)", fontWeight: 700 }}>
                    {e.color === "hong" ? "HONG" : "CHUNG"}
                  </span>
                )}
                <span>{e.etiqueta}</span>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-sm" onClick={onDeshacer}>{t("tat.off.deshacerUltimo")}</button>
            {confirmandoBorrado ? (
              <>
                <button className="btn btn-sm btn-danger" onClick={() => { onLimpiar(); setConfirmandoBorrado(false); }}>
                  {t("tat.off.siBorrar")}
                </button>
                <button className="btn btn-sm" onClick={() => setConfirmandoBorrado(false)}>{t("comun.cancelar")}</button>
              </>
            ) : (
              <button className="btn btn-sm btn-danger" onClick={() => setConfirmandoBorrado(true)}>
                {t("tat.off.borrar")}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// Inputs de nombres con estado local + debounce. El estado del combate vive en
// el servidor, pero atar el value del input al eco del socket hace que cada
// tecla espere el viaje de ida y vuelta: con latencia real se traga letras.
// Aquí la letra aparece al instante y el envío se agrupa (pausa de 500 ms o blur).
function NombresCombate({ nombreHong, nombreChung, enviarEvento, disabled }: {
  nombreHong: string;
  nombreChung: string;
  enviarEvento: (accion: string, datos?: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  const { t } = useI18n();
  const aDraft = (v: string, def: string) => (v === def ? "" : v);
  const [hong, setHong] = useState(() => aDraft(nombreHong, "Hong"));
  const [chung, setChung] = useState(() => aDraft(nombreChung, "Chung"));
  const editandoRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const draftsRef = useRef({ hong, chung });
  draftsRef.current = { hong, chung };
  const serverRef = useRef({ nombreHong, nombreChung });
  serverRef.current = { nombreHong, nombreChung };

  // Adoptar cambios del servidor solo cuando no se está escribiendo
  // (ej. otra pantalla activa una llave y los nombres llegan solos)
  useEffect(() => {
    if (!editandoRef.current) {
      setHong(aDraft(nombreHong, "Hong"));
      setChung(aDraft(nombreChung, "Chung"));
    }
  }, [nombreHong, nombreChung]);

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  const commit = () => {
    const payload = {
      nombreHong: draftsRef.current.hong || "Hong",
      nombreChung: draftsRef.current.chung || "Chung",
    };
    if (payload.nombreHong === serverRef.current.nombreHong &&
        payload.nombreChung === serverRef.current.nombreChung) return;
    enviarEvento("nombres", payload);
  };

  const programarCommit = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(commit, 500);
  };

  const onBlur = () => {
    editandoRef.current = false;
    if (timerRef.current) clearTimeout(timerRef.current);
    commit();
  };

  return (
    <div className="grid-2" style={{ marginBottom: 10 }}>
      <input className="input" placeholder={t("tat.jc.nombreHong")} value={hong}
        disabled={disabled}
        onFocus={() => { editandoRef.current = true; }}
        onBlur={onBlur}
        onChange={(e) => { setHong(e.target.value); programarCommit(); }}
        style={{
          borderColor: !hong ? "var(--hong-border)" : "var(--green-border)",
          textAlign: "center", fontWeight: 700, color: "var(--hong-light)",
          opacity: disabled ? 0.6 : 1,
        }} />
      <input className="input" placeholder={t("tat.jc.nombreChung")} value={chung}
        disabled={disabled}
        onFocus={() => { editandoRef.current = true; }}
        onBlur={onBlur}
        onChange={(e) => { setChung(e.target.value); programarCommit(); }}
        style={{
          borderColor: !chung ? "var(--chung-border)" : "var(--green-border)",
          textAlign: "center", fontWeight: 700, color: "var(--chung-light)",
          opacity: disabled ? 0.6 : 1,
        }} />
    </div>
  );
}

// COMBATE — Juez Central (Arbitro)
// ══════════════════════════════════════════════════════════════════════════════
function CombateArbitro({
  state, enviarEvento, tatamiDbId, connected,
  onFlash, onFaltaFlash, onShowConfirm, broadcast
}: {
  state: CombateState;
  enviarEvento: (accion: string, datos?: Record<string, unknown>) => void;
  tatamiId: string;
  tatamiDbId: string;
  connected: boolean;
  onFlash: (ico: string, txt: string) => void;
  onFaltaFlash: (data: FaltaFlashData) => void;
  onShowConfirm: (data: import("@/components/AlertSystem").ConfirmData) => void;
  broadcast: (data: Record<string, unknown>) => void;
}) {
  const { t } = useI18n();
  const totalHong = marcadorDisplay(state, "hong");
  const totalChung = marcadorDisplay(state, "chung");
  // El VALOR del motivo es canónico (en español): viaja al servidor y queda
  // en reportes. Solo la etiqueta visible del <option> se traduce.
  const [motivoDq, setMotivoDq] = useState("No presentación");
  const offline = useRegistroOffline(`dinamyt_offline_${tatamiDbId}_arbitro`);
  const nombresListos = competidoresConNombre(state);
  // Con ganador declarado el combate está cerrado: se bloquea todo lo que
  // altere marcador o cronómetro. Solo quedan NUEVO COMBATE (guardar) y REINICIO TOTAL.
  // La alerta de superioridad abierta también pausa el combate.
  const combateCerrado = Boolean(state.ganadorManualColor);
  const cierreBloqueado = !nombresListos || Boolean(state.ganadorPendienteCierre);
  const accionesBloqueadas = cierreBloqueado || combateCerrado || Boolean(state.alerta12Data);
  // La configuración (ronda, duración, jueces) NO requiere nombres: se puede
  // preparar antes de ingresarlos. Solo se bloquea con el combate cerrado, en
  // pausa por alerta, o con un ganador por confirmar.
  const configBloqueada = combateCerrado || Boolean(state.alerta12Data) || Boolean(state.ganadorPendienteCierre);
  // Sin conexión, los puntos y faltas del JC van al registro local
  const puntosArbBloqueados = connected && (state.oroResuelto || accionesBloqueadas);
  const faltasBloqueadas = connected && accionesBloqueadas;

  // "nombre" es el CANÓNICO (español) que viaja al servidor y queda en el
  // historial/reportes; "clave" solo traduce la etiqueta del botón.
  const PUNTOS_ARB: { pts: number; nombre: string; clave: ClaveTexto }[] = [
    { pts: 2, nombre: "Knock Down", clave: "tat.pts.knockDown" },
    { pts: 2, nombre: "Derribo/Barrida", clave: "tat.pts.derribo" },
    { pts: 2, nombre: "Proyeccion", clave: "tat.pts.proyeccion" },
  ];
  const RONDAS_BTN: { id: string; clave: ClaveTexto }[] = [
    { id: "r1", clave: "tat.rondaBtn.r1" }, { id: "r2", clave: "tat.rondaBtn.r2" }, { id: "oro", clave: "tat.rondaBtn.oro" },
  ];
  const DURACIONES = [30, 60, 90, 120];

  // Validar nombres antes de iniciar crono
  function handleCronoStart() {
    if (state.segundos <= 0) {
      // El servidor ignora INICIAR con el tiempo agotado: avisar al JC
      onFlash("⏱", t("tat.flash.tiempoAgotado"));
      return;
    }
    if (!nombresListos) {
      onShowConfirm({
        titulo: t("tat.jc.nombresReq.titulo"),
        mensaje: t("tat.jc.nombresReq.crono"),
        tipo: "advertencia",
        solo_ok: true,
        onConfirm: () => {},
      });
      return;
    }
    enviarEvento("crono_start");
  }

  function handleEspecial(color: "hong" | "chung", pts: number, nombre: string) {
    if (!connected) {
      // Sin flash: el marcador del panel de registro local ya refleja el cambio.
      offline.agregar({ etiqueta: `⭐ ${nombre} +${pts}`, color, pts });
      return;
    }
    if (!nombresListos) {
      onFlash("⚠️", t("tat.flash.nombresRequeridos"));
      return;
    }
    if (state.oroResuelto) {
      onFlash("⚠️", t("tat.flash.oroBloqueado"));
      return;
    }
    const data: FaltaFlashData = {
      ico: "⭐",
      titulo: `+${pts} ${nombre.toUpperCase()}`,
      sub: `${color === "hong" ? "🔴 HONG" : "🔵 CHUNG"}`,
      tipo: "especial",
    };
    onFaltaFlash(data);
    broadcast({ tipo: "falta-flash", ico: data.ico, titulo: data.titulo, sub: data.sub, tipoFalta: data.tipo });
    enviarEvento("especial", { color, pts, nombre });
  }

  function handleKyonggo(color: "hong" | "chung") {
    if (!connected) {
      offline.agregar({ etiqueta: "KyongGo −0.5", color, pts: -0.5 });
      return;
    }
    if (!nombresListos) {
      onFlash("⚠️", t("tat.flash.nombresRequeridos"));
      return;
    }
    const num = (color === "hong" ? state.kyongHong : state.kyongChung) + 1;
    const data: FaltaFlashData = {
      ico: "⚠️",
      titulo: "KYONGGO −0.5",
      sub: `${color === "hong" ? "🔴 HONG" : "🔵 CHUNG"} · Advertencia #${num}`,
      tipo: "adv",
    };
    onFaltaFlash(data);
    broadcast({ tipo: "falta-flash", ico: data.ico, titulo: data.titulo, sub: data.sub, tipoFalta: data.tipo });
    enviarEvento("kyonggo", { color });
  }

  function handleGamjeum(color: "hong" | "chung") {
    if (!connected) {
      offline.agregar({ etiqueta: "GamJeum −1", color, pts: -1 });
      return;
    }
    if (!nombresListos) {
      onFlash("⚠️", t("tat.flash.nombresRequeridos"));
      return;
    }
    const num = (color === "hong" ? state.faltasHong : state.faltasChung) + 1;
    const data: FaltaFlashData = {
      ico: "🚫",
      titulo: "GAMJEUM −1",
      sub: `${color === "hong" ? "🔴 HONG" : "🔵 CHUNG"} · Falta #${num}`,
      tipo: "falta",
    };
    onFaltaFlash(data);
    broadcast({ tipo: "falta-flash", ico: data.ico, titulo: data.titulo, sub: data.sub, tipoFalta: data.tipo });
    enviarEvento("gamjeum", { color });
  }

  function handleDeclararGanador(color: "hong" | "chung", motivo: string) {
    if (!nombresListos) {
      onShowConfirm({
        titulo: t("tat.jc.nombresReq.titulo"),
        mensaje: t("tat.jc.nombresReq.ganador"),
        tipo: "advertencia",
        solo_ok: true,
        onConfirm: () => {},
      });
      return;
    }

    const nombre = color === "hong" ? state.nombreHong : state.nombreChung;
    onShowConfirm({
      // El motivo viaja canónico (español) al servidor; para el TÍTULO del
      // diálogo se muestra traducido si es uno de los conocidos.
      titulo: (motivo === "Superioridad técnica" ? t("alert.superioridad") : motivo).toUpperCase(),
      mensaje: t("tat.jc.declarar.mensaje", { nombre }),
      tipo: "advertencia",
      confirmLabel: t("tat.jc.declarar.confirmar"),
      cancelLabel: t("comun.cancelar"),
      onConfirm: () => enviarEvento("declarar_ganador", { color, motivo }),
    });
  }

  function handleDescalificar(color: "hong" | "chung") {
    if (!nombresListos) {
      onShowConfirm({
        titulo: t("tat.jc.nombresReq.titulo"),
        mensaje: t("tat.jc.nombresReq.dq"),
        tipo: "advertencia",
        solo_ok: true,
        onConfirm: () => {},
      });
      return;
    }
    const nombre = color === "hong" ? state.nombreHong : state.nombreChung;
    const rival = color === "hong" ? state.nombreChung : state.nombreHong;
    onShowConfirm({
      titulo: t("tat.jc.dq.titulo"),
      mensaje: t("tat.jc.dq.mensaje", {
        nombre,
        color: color === "hong" ? "🔴 HONG" : "🔵 CHUNG",
        motivo: motivoDq,
        rival,
      }),
      tipo: "peligro",
      confirmLabel: t("tat.jc.dq.confirmar"),
      cancelLabel: t("comun.cancelar"),
      onConfirm: () => enviarEvento("descalificar", { color, razon: motivoDq }),
    });
  }

  function handleNuevoCombate() {
    onShowConfirm({
      titulo: t("tat.jc.guardarNuevo.titulo"),
      mensaje: t("tat.jc.guardarNuevo.mensaje"),
      tipo: "advertencia",
      confirmLabel: t("tat.guardarNuevoLabel"),
      cancelLabel: t("comun.cancelar"),
      onConfirm: () => {
        onFlash("📁", t("tat.flash.combateGuardado"));
        enviarEvento("nuevo_combate");
      },
    });
  }

  function handleReset() {
    onShowConfirm({
      titulo: t("tat.jc.reiniciarMarcador.titulo"),
      mensaje: t("tat.jc.reiniciarMarcador.mensaje"),
      tipo: "peligro",
      confirmLabel: t("tat.reiniciarLabel"),
      onConfirm: () => enviarEvento("reset"),
    });
  }

  return (
    <div style={{ maxWidth: 780, margin: "0 auto", padding: "10px 14px", position: "relative" }}>
      {state.oroPendienteAprobacion && (
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(15,15,25,0.9)", zIndex: 10,
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          backdropFilter: "blur(5px)", borderRadius: "var(--radius)"
        }}>
          <div style={{ fontSize: "3rem", marginBottom: 12 }}>🏆</div>
          <div style={{ color: "var(--gold)", fontWeight: 800, fontSize: "1.5rem", letterSpacing: "0.05em", textAlign: "center", padding: "0 20px" }}>
            {t("tat.jc.oroPorAprobar")}
          </div>
          {state.oroPuntoDetalle && (
            <div style={{
              marginTop: 12, padding: "8px 16px", borderRadius: "var(--radius)",
              border: "1px solid var(--gold)", color: "var(--gold)",
              fontWeight: 700, fontSize: "1rem", textAlign: "center", maxWidth: 420,
            }}>
              {state.oroPuntoDetalle}
            </div>
          )}
          <div style={{ color: "var(--text)", marginTop: 10, textAlign: "center", maxWidth: 420, fontSize: "0.9rem" }}>
            {t("tat.jc.oroPara")} <strong>{state.oroGanadorNombre || t("tat.jc.elCompetidor")}</strong>
            {t("tat.jc.oroDesc1")} <strong>{t("tat.jc.oroNoSumado")}</strong>
            {t("tat.jc.oroDesc2")}
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 24 }}>
            <button className="btn btn-primary" onClick={() => enviarEvento("aprobar_oro")} style={{ padding: "12px 24px", fontSize: "1.1rem" }}>
              {t("tat.jc.aprobarFinalizar")}
            </button>
            <button className="btn btn-danger" onClick={() => enviarEvento("rechazar_oro")} style={{ padding: "12px 24px", fontSize: "1.1rem" }}>
              {t("tat.jc.rechazarContinuar")}
            </button>
          </div>
        </div>
      )}

      {/* Combates de eliminación (llaves asignadas a este tatami).
          Sin conexión no se muestran: no se pueden activar ni avanzar. */}
      {connected && (
        <LlavePanel
          tatamiDbId={tatamiDbId}
          combateLlave={state._combate_llave}
          mostrarArbol={Boolean(state._mostrar_arbol)}
          hayArbol={Boolean(state._hay_arbol)}
          enviarEvento={enviarEvento}
          onShowConfirm={onShowConfirm}
        />
      )}

      {/* Registro local del JC: arriba solo el aviso y el marcador local */}
      <PanelRegistroOffline
        modo="resumen"
        conectado={connected}
        entradas={offline.entradas}
        onDeshacer={offline.deshacer}
        onLimpiar={offline.limpiar}
        descripcion={connected
          ? t("tat.jc.reconectadoDesc")
          : t("tat.jc.offDesc")}
      />

      {/* Registros locales de jueces de esquina esperando resolución */}
      {state._propuestas_local && Object.keys(state._propuestas_local).length > 0 && (
        <div className="card" style={{ marginBottom: 10, borderColor: "var(--orange)", padding: "10px 14px" }}>
          <div className="card-title" style={{ color: "var(--orange)" }}>
            {t("tat.jc.propuestas.titulo")}
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.82rem", marginBottom: 8 }}>
            {t("tat.jc.propuestas.desc")}
          </p>
          {Object.entries(state._propuestas_local).map(([rolJuez, prop]) => (
            <div key={rolJuez} style={{ marginBottom: 8, paddingBottom: 8, borderBottom: "1px solid var(--border)" }}>
              <div style={{ fontWeight: 800, fontSize: "0.9rem", marginBottom: 4 }}>
                {rolJuez.toUpperCase()}{prop.nombre ? ` · ${prop.nombre}` : ""} — {prop.entradas.length} {t("tat.jc.propuestas.anotaciones")}
              </div>
              <div style={{ maxHeight: 96, overflowY: "auto", fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: 6 }}>
                {prop.entradas.map((e, i) => (
                  <div key={`${e.ts}-${i}`}>
                    <span style={{ color: e.color === "hong" ? "var(--hong-light)" : "var(--chung-light)", fontWeight: 700 }}>
                      {e.color === "hong" ? "HONG" : "CHUNG"}
                    </span>
                    {" "}{e.etiqueta}
                    {e.ts ? (
                      <span style={{ color: "var(--text-dim)" }}>
                        {" · "}
                        {new Date(e.ts).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}
                      </span>
                    ) : null}
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={() => onShowConfirm({
                    titulo: t("tat.jc.aplicarReg.titulo"),
                    mensaje: t("tat.jc.aplicarReg.mensaje", { n: prop.entradas.length, rol: rolJuez.toUpperCase() }),
                    tipo: "advertencia",
                    confirmLabel: t("tat.jc.aplicarReg.confirmar"),
                    cancelLabel: t("comun.cancelar"),
                    onConfirm: () => enviarEvento("resolver_registro_local", { rol: rolJuez, aplicar: true }),
                  })}
                >
                  {t("tat.jc.aplicarBtn")}
                </button>
                <button
                  className="btn btn-sm btn-danger"
                  onClick={() => onShowConfirm({
                    titulo: t("tat.jc.descartarReg.titulo"),
                    mensaje: t("tat.jc.descartarReg.mensaje", { rol: rolJuez.toUpperCase() }),
                    tipo: "peligro",
                    confirmLabel: t("tat.jc.descartarReg.confirmar"),
                    cancelLabel: t("comun.cancelar"),
                    onConfirm: () => enviarEvento("resolver_registro_local", { rol: rolJuez, aplicar: false }),
                  })}
                >
                  {t("tat.jc.descartarBtn")}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Combate cerrado: solo guardar o descartar */}
      {combateCerrado && !state.ganadorPendienteCierre && (
        <div style={{
          marginBottom: 10, padding: "10px 14px", borderRadius: "var(--radius)",
          border: "1px solid var(--gold)", background: "rgba(212,175,55,0.08)",
          color: "var(--gold)", fontWeight: 700, textAlign: "center", fontSize: "0.92rem",
        }}>
          {t("tat.jc.cerradoBanner1")} {state.ganadorManualColor === "hong" ? state.nombreHong : state.nombreChung}
          {state.ganadorManualMotivo ? ` (${state.ganadorManualMotivo})` : ""}.{" "}
          {t("tat.jc.cerradoBanner2")}
        </div>
      )}

      {/* Nombres */}
      <NombresCombate
        nombreHong={state.nombreHong}
        nombreChung={state.nombreChung}
        enviarEvento={enviarEvento}
        disabled={combateCerrado || Boolean(state.ganadorPendienteCierre)}
      />
      {(state.nombreHong === "Hong" || state.nombreChung === "Chung") && (
        <p style={{ color: "var(--orange)", fontSize: "0.85rem", textAlign: "center", marginBottom: 8 }}>
          {t("tat.jc.ingresaNombres")}
        </p>
      )}

      {/* Scores + Timer */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 8, marginBottom: 10 }}>
        <div className="card card-hong" style={{ textAlign: "center", padding: "10px 8px" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--hong-light)", fontWeight: 800 }}>{state.nombreHong}</div>
          <div style={{ fontFamily: "var(--font-display)", fontSize: "3rem", color: "var(--hong-vivid)" }}>{totalHong}</div>
          <DesgloseMarcador state={state} color="hong" />
          <div style={{ fontSize: "0.75rem", marginTop: 2 }}>
            {state.kyongHong > 0 && <span style={{ color: "var(--orange)", marginRight: 4 }}>K:{state.kyongHong}</span>}
            {state.faltasHong > 0 && <span style={{ color: "var(--red-alert)" }}>G:{state.faltasHong}</span>}
          </div>
        </div>

        {/* Timer */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minWidth: 100 }}>
          <CronoDisplay segundos={state.segundos} activo={state.activo} segundosMax={state.segundosMax} />
          <div style={{ display: "flex", gap: 5, marginTop: 6 }}>
            <button className="btn btn-sm"
              onClick={state.activo ? () => enviarEvento("crono_pause") : handleCronoStart}
              disabled={Boolean(state.ganadorPendienteCierre)}
              style={{
                padding: "5px 10px", fontWeight: 800,
                opacity: state.ganadorPendienteCierre ? 0.45 : 1,
                background: state.activo ? "rgba(255,68,68,0.15)" : "rgba(0,212,114,0.15)",
                borderColor: state.activo ? "rgba(255,68,68,0.4)" : "rgba(0,212,114,0.4)",
                color: state.activo ? "var(--red-alert)" : "var(--green)",
              }}>
              {state.activo ? t("tat.jc.pausa") : t("tat.jc.iniciar")}
            </button>
            <button className="btn btn-sm"
              onClick={() => enviarEvento("crono_reset", { segundosMax: state.segundosMax })}
              disabled={accionesBloqueadas}
              style={{ padding: "5px 8px", opacity: accionesBloqueadas ? 0.45 : 1 }}>{t("tat.jc.reiniciarCrono")}</button>
          </div>
        </div>

        <div className="card card-chung" style={{ textAlign: "center", padding: "10px 8px" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--chung-light)", fontWeight: 800 }}>{state.nombreChung}</div>
          <div style={{ fontFamily: "var(--font-display)", fontSize: "3rem", color: "var(--chung-vivid)" }}>{totalChung}</div>
          <DesgloseMarcador state={state} color="chung" />
          <div style={{ fontSize: "0.75rem", marginTop: 2 }}>
            {state.kyongChung > 0 && <span style={{ color: "var(--orange)", marginRight: 4 }}>K:{state.kyongChung}</span>}
            {state.faltasChung > 0 && <span style={{ color: "var(--red-alert)" }}>G:{state.faltasChung}</span>}
          </div>
        </div>
      </div>

      {/* Configuración (ronda, duración, jueces): se fija al inicio, por eso
          va colapsada con un resumen en el badge para no estorbar en vivo */}
      <PanelColapsable
        titulo={t("tat.jc.config")}
        icono="⚙"
        acento="oro"
        badge={`${t(RONDAS_BTN.find((r) => r.id === state.ronda)?.clave ?? "tat.rondaBtn.r1")} · ${state.segundosMax}s · ${state.numJueces}J`}
      >
      <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 8 }}>
        {RONDAS_BTN.map((r) => (
          <button key={r.id} className="btn btn-sm"
            onClick={() => enviarEvento("ronda", { ronda: r.id })}
            disabled={configBloqueada}
            style={{
              opacity: configBloqueada ? 0.45 : 1,
              background: state.ronda === r.id ? "var(--gold-bg)" : undefined,
              borderColor: state.ronda === r.id ? "var(--gold-border)" : undefined,
              color: state.ronda === r.id ? "var(--gold)" : undefined,
              animation: state.ronda === "oro" && r.id === "oro" ? "glow-oro 1.2s infinite alternate" : undefined,
            }}>{t(r.clave)}</button>
        ))}
        <span style={{ color: "var(--border-light)", alignSelf: "center", fontSize: "1.2rem" }}>|</span>
        {DURACIONES.map((d) => (
          <button key={d} className="btn btn-sm"
            onClick={() => enviarEvento("crono_reset", { segundosMax: d })}
            disabled={configBloqueada}
            style={{
              opacity: configBloqueada ? 0.45 : 1,
              background: state.segundosMax === d ? "var(--chung-bg)" : undefined,
              borderColor: state.segundosMax === d ? "var(--chung-border)" : undefined,
            }}>{d}s</button>
        ))}
        <span style={{ color: "var(--border-light)", alignSelf: "center", fontSize: "1.2rem" }}>|</span>
        <span style={{ color: "var(--text-muted)", fontSize: "0.85rem", alignSelf: "center", fontWeight: 700 }}>{t("tat.jc.jueces")}</span>
        {[2, 3, 4].map((n) => (
          <button key={n} className="btn btn-sm"
            onClick={() => enviarEvento("set_num_jueces", { numJueces: n })}
            disabled={configBloqueada}
            style={{
              opacity: configBloqueada ? 0.45 : 1,
              background: state.numJueces === n ? "var(--gold-bg)" : undefined,
              borderColor: state.numJueces === n ? "var(--gold-border)" : undefined,
              color: state.numJueces === n ? "var(--gold)" : undefined,
            }}>{n}</button>
        ))}
      </div>
      </PanelColapsable>

      {/* Puntos árbitro */}
      <div className="card-title">{t("tat.jc.puntosJC")}</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 8 }}>
        {PUNTOS_ARB.map((p) => (
          <div key={p.nombre} style={{ display: "contents" }}>
            <button
              className="combat-btn hong"
              onClick={() => handleEspecial("hong", p.pts, p.nombre)}
              disabled={puntosArbBloqueados}
              style={{ opacity: puntosArbBloqueados ? 0.5 : 1 }}
            >
              <span className="pts">+{p.pts}</span>
              <span className="label">{t(p.clave)}</span>
            </button>
            <button
              className="combat-btn chung"
              onClick={() => handleEspecial("chung", p.pts, p.nombre)}
              disabled={puntosArbBloqueados}
              style={{ opacity: puntosArbBloqueados ? 0.5 : 1 }}
            >
              <span className="pts">+{p.pts}</span>
              <span className="label">{t(p.clave)}</span>
            </button>
          </div>
        ))}
      </div>

      {/* Faltas */}
      <div className="card-title">{t("tat.jc.faltas")}</div>
      <div className="grid-2" style={{ marginBottom: 8 }}>
        <button className="combat-btn hong" onClick={() => handleKyonggo("hong")} disabled={faltasBloqueadas} style={{ opacity: faltasBloqueadas ? 0.5 : 1 }}>
          <span className="pts">−0.5</span><span className="label">KyongGo HONG</span>
        </button>
        <button className="combat-btn chung" onClick={() => handleKyonggo("chung")} disabled={faltasBloqueadas} style={{ opacity: faltasBloqueadas ? 0.5 : 1 }}>
          <span className="pts">−0.5</span><span className="label">KyongGo CHUNG</span>
        </button>
        <button className="combat-btn falta" onClick={() => handleGamjeum("hong")} disabled={faltasBloqueadas} style={{ opacity: faltasBloqueadas ? 0.5 : 1 }}>
          <span className="pts">−1</span><span className="label">GamJeum HONG</span>
        </button>
        <button className="combat-btn falta" onClick={() => handleGamjeum("chung")} disabled={faltasBloqueadas} style={{ opacity: faltasBloqueadas ? 0.5 : 1 }}>
          <span className="pts">−1</span><span className="label">GamJeum CHUNG</span>
        </button>
      </div>

      {/* Finalizar: decisión y descalificación — solo se usan al cerrar el
          combate, así que van colapsadas para no saturar la vista en vivo */}
      <PanelColapsable titulo={t("tat.jc.finalizar")} icono="🏁" acento="rojo">
      <div className="card-title" style={{ marginTop: 4 }}>{t("tat.jc.decision")}</div>
      <div className="grid-2" style={{ marginBottom: 8 }}>
        <button
          className="combat-btn hong"
          onClick={() => handleDeclararGanador("hong", "Superioridad técnica")}
          disabled={accionesBloqueadas}
          style={{ opacity: accionesBloqueadas ? 0.5 : 1 }}
        >
          <span className="pts">S.T.</span><span className="label">{t("tat.jc.superioridadHong")}</span>
        </button>
        <button
          className="combat-btn chung"
          onClick={() => handleDeclararGanador("chung", "Superioridad técnica")}
          disabled={accionesBloqueadas}
          style={{ opacity: accionesBloqueadas ? 0.5 : 1 }}
        >
          <span className="pts">S.T.</span><span className="label">{t("tat.jc.superioridadChung")}</span>
        </button>
        <button
          className="combat-btn hong"
          onClick={() => handleDeclararGanador("hong", "Decisión del Juez Central")}
          disabled={accionesBloqueadas}
          style={{ opacity: accionesBloqueadas ? 0.5 : 1 }}
        >
          <span className="pts">SUNG</span><span className="label">{t("tat.jc.ganadorHong")}</span>
        </button>
        <button
          className="combat-btn chung"
          onClick={() => handleDeclararGanador("chung", "Decisión del Juez Central")}
          disabled={accionesBloqueadas}
          style={{ opacity: accionesBloqueadas ? 0.5 : 1 }}
        >
          <span className="pts">SUNG</span><span className="label">{t("tat.jc.ganadorChung")}</span>
        </button>
      </div>

      {/* Descalificación directa (no presentación, conducta, etc.) */}
      <div className="card-title">{t("tat.jc.descalificacion")}</div>
      <select
        className="input"
        value={motivoDq}
        onChange={(e) => setMotivoDq(e.target.value)}
        disabled={accionesBloqueadas}
        style={{ marginBottom: 8, textAlign: "center", fontWeight: 700, opacity: accionesBloqueadas ? 0.5 : 1 }}
      >
        <option value="No presentación">{t("tat.motivo.noPresentacion")}</option>
        <option value="Conducta antideportiva">{t("tat.motivo.conducta")}</option>
        <option value="Decisión del Juez Central">{t("tat.motivo.decision")}</option>
      </select>
      <div className="grid-2" style={{ marginBottom: 8 }}>
        <button
          className="combat-btn falta"
          onClick={() => handleDescalificar("hong")}
          disabled={accionesBloqueadas}
          style={{ opacity: accionesBloqueadas ? 0.5 : 1 }}
        >
          <span className="pts">🚫</span><span className="label">{t("tat.jc.dqHong")}</span>
        </button>
        <button
          className="combat-btn falta"
          onClick={() => handleDescalificar("chung")}
          disabled={accionesBloqueadas}
          style={{ opacity: accionesBloqueadas ? 0.5 : 1 }}
        >
          <span className="pts">🚫</span><span className="label">{t("tat.jc.dqChung")}</span>
        </button>
      </div>
      </PanelColapsable>

      {/* Deshacer + Guardar */}
      <div className="grid-2" style={{ marginBottom: 8 }}>
        <button className="btn btn-sm btn-danger"
          disabled={accionesBloqueadas}
          style={{ opacity: accionesBloqueadas ? 0.5 : 1 }}
          onClick={() => enviarEvento("deshacer_arbitro", { color: "hong" })}>
          {t("tat.jc.deshacerHong")}
        </button>
        <button className="btn btn-sm btn-danger"
          disabled={accionesBloqueadas}
          style={{ opacity: accionesBloqueadas ? 0.5 : 1 }}
          onClick={() => enviarEvento("deshacer_arbitro", { color: "chung" })}>
          {t("tat.jc.deshacerChung")}
        </button>
      </div>

      <div className="grid-2" style={{ marginBottom: 10 }}>
        <button className="btn btn-primary" onClick={handleNuevoCombate} disabled={cierreBloqueado} style={{ opacity: cierreBloqueado ? 0.5 : 1 }}>
          {t("tat.guardarNuevoBtn")}
        </button>
        <button className="btn btn-danger" onClick={handleReset} disabled={cierreBloqueado} style={{ opacity: cierreBloqueado ? 0.5 : 1 }}>
          {t("tat.jc.reinicioTotal")}
        </button>
      </div>

      {/* Historial de puntos: anular una entrada ESPECÍFICA (no solo la última) */}
      {state.historial && state.historial.filter((h) => !h.esDecision).length > 0 && (
        <PanelColapsable
          titulo={t("tat.jc.historial.titulo")}
          icono="⛔"
          acento="rojo"
          badge={String(state.historial.filter((h) => !h.esDecision).length)}
        >
          <div style={{ maxHeight: 240, overflowY: "auto", marginTop: 6, display: "flex", flexDirection: "column", gap: 2 }}>
            {[...state.historial].reverse().filter((h) => !h.esDecision).map((h) => {
              const idx = state.historial.indexOf(h);
              const hora = h.momento
                ? new Date(h.momento).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })
                : "—";
              return (
                <div
                  key={`${h.momento || "h"}-${idx}`}
                  style={{
                    display: "flex", alignItems: "center", gap: 8, fontSize: "0.84rem",
                    padding: "3px 0", borderBottom: "1px solid var(--border)",
                  }}
                >
                  <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-dim)", flexShrink: 0, fontSize: "0.78rem" }}>
                    {hora}
                  </span>
                  <span style={{ color: h.color === "hong" ? "var(--hong-light)" : "var(--chung-light)", fontWeight: 700, flexShrink: 0 }}>
                    {h.color === "hong" ? "HONG" : "CHUNG"}
                  </span>
                  <span style={{ flex: 1, minWidth: 0, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {h.pts > 0 ? `+${h.pts}` : h.pts} {h.nombre} · {h.juez_asignacion || h.juez.toUpperCase()}
                  </span>
                  <button
                    className="btn btn-sm btn-danger"
                    style={{ padding: "2px 8px", minHeight: 26, fontSize: "0.78rem", flexShrink: 0, opacity: accionesBloqueadas ? 0.5 : 1 }}
                    disabled={accionesBloqueadas}
                    onClick={() => onShowConfirm({
                      titulo: t("tat.jc.anular.titulo"),
                      mensaje: t("tat.jc.anular.mensaje", {
                        punto: h.nombre,
                        pts: h.pts > 0 ? `+${h.pts}` : h.pts,
                        juez: (h.juez_asignacion || h.juez).toString().toUpperCase(),
                        nombre: h.color === "hong" ? state.nombreHong : state.nombreChung,
                      }),
                      tipo: "peligro",
                      confirmLabel: t("tat.jc.anular.confirmar"),
                      cancelLabel: t("comun.cancelar"),
                      onConfirm: () => enviarEvento("anular_entrada", {
                        idx,
                        firma: { juez: h.juez, color: h.color, pts: h.pts, momento: h.momento },
                      }),
                    })}
                  >
                    {t("tat.jc.anularBtn")}
                  </button>
                </div>
              );
            })}
          </div>
          <p style={{ color: "var(--text-dim)", fontSize: "0.78rem", marginTop: 6 }}>
            {t("tat.jc.historial.nota")}
          </p>
        </PanelColapsable>
      )}

      {/* Log completo del combate (de inicio a fin): hora real de cada
          acción + tiempo del cronómetro en ese momento (⏱ corriendo,
          ⏸ en pausa) para que los jueces ubiquen la acción en el reloj. */}
      {state.log && state.log.length > 0 && (
        <PanelColapsable titulo={t("tat.jc.log.titulo")} icono="📜" badge={String(state.log.length)}>
          <div style={{ maxHeight: 280, overflowY: "auto", fontSize: "0.84rem", marginTop: 6 }}>
            {state.log.map((l, i) => (
              <div
                key={`${l.ts}-${i}`}
                style={{
                  padding: "3px 0", borderBottom: "1px solid var(--border)",
                  display: "flex", gap: 8, alignItems: "baseline",
                  color: l.color === "hong" ? "var(--hong-light)"
                    : l.color === "chung" ? "var(--chung-light)"
                    : "var(--text-muted)",
                }}
              >
                <span style={{
                  fontFamily: "var(--font-mono)", color: "var(--text-dim)",
                  flexShrink: 0, fontSize: "0.78rem",
                }}>
                  {new Date(l.ts).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}
                </span>
                {typeof l.crono === "number" && (
                  <span
                    title={l.cronoActivo ? t("tat.jc.cronoCorriendo") : t("tat.jc.cronoPausa")}
                    style={{
                      fontFamily: "var(--font-mono)", flexShrink: 0, fontSize: "0.78rem",
                      color: l.cronoActivo ? "var(--green)" : "var(--text-dim)",
                    }}
                  >
                    {l.cronoActivo ? "⏱" : "⏸"} {formatTime(l.crono)}
                  </span>
                )}
                <span>{l.txt}</span>
              </div>
            ))}
          </div>
          <p style={{ color: "var(--text-dim)", fontSize: "0.78rem", marginTop: 6 }}>
            {t("tat.jc.log.nota")}
          </p>
        </PanelColapsable>
      )}

      {/* Detalle del registro local del JC: al final para no estorbar */}
      <div style={{ marginTop: 10 }}>
        <PanelRegistroOffline
          modo="detalle"
          conectado={connected}
          entradas={offline.entradas}
          onDeshacer={offline.deshacer}
          onLimpiar={offline.limpiar}
          descripcion=""
        />
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ══════════════════════════════════════════════════════════════════════════════
function TatamiContent() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();

  const tatamiId = params.id as string;
  const rol = searchParams.get("rol") || "pantalla";

  // La sesión vive en una cookie httpOnly, ilegible desde aquí: el socket usa
  // un ticket que se pide al backend (null en la pantalla pública, que no tiene
  // sesión y conecta sin identidad).
  const token = useSocketTicket();
  const { state, connected, offline, sesionReemplazada, reconectar, registroResuelto, hasServerState, socketError, pendingEvents, enviarEvento, broadcast, alerts: socketAlerts, clearAlert } = useCombate(tatamiId, rol, token);
  // En modo offline el juez elige localmente qué necesita puntuar
  // (no se sabe cuánto dura la caída ni qué categoría corre el tatami).
  const [catOffline, setCatOffline] = useState<"combate" | "figuras" | null>(null);

  const alertSystem = useAlertSystem();

  // Wire socket alerts → alertSystem
  useEffect(() => {
    if (socketAlerts.faltaFlash) {
      alertSystem.showFaltaFlash({
        ico: socketAlerts.faltaFlash.ico,
        titulo: socketAlerts.faltaFlash.titulo,
        sub: socketAlerts.faltaFlash.sub,
        tipo: (socketAlerts.faltaFlash.tipoFalta as "adv" | "falta" | "especial") || "adv",
      });
      clearAlert("faltaFlash");
    }
  }, [socketAlerts.faltaFlash]);

  useEffect(() => {
    if (socketAlerts.ganador) {
      alertSystem.showGanador(socketAlerts.ganador as GanadorData);
      clearAlert("ganador");
    }
  }, [socketAlerts.ganador]);

  // Superioridad técnica: la alerta vive en el ESTADO del servidor
  // (alerta12Data) — visible para todos hasta que el Juez Central decida
  // (reanudar o declarar ganador). No se usa el evento transitorio del socket.
  useEffect(() => {
    if (state.alerta12Data) {
      const liderNombre = state.alerta12Data.lider === "Hong" ? state.nombreHong : state.nombreChung;
      alertSystem.showAlerta12({ ...state.alerta12Data, liderNombre } as Alerta12Data);
    } else {
      alertSystem.clearAlerta12();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.alerta12Data]);

  useEffect(() => {
    if (socketAlerts.derrota) {
      alertSystem.showDerrota(socketAlerts.derrota as DerrotaData);
      clearAlert("derrota");
    }
  }, [socketAlerts.derrota]);

  useEffect(() => {
    if (socketAlerts.rechazo) {
      alertSystem.showConfirm({
        titulo: t("tat.accionRechazada"),
        mensaje: socketAlerts.rechazo.message,
        tipo: "advertencia",
        solo_ok: true,
        onConfirm: () => {},
      });
      clearAlert("rechazo");
    }
  }, [socketAlerts.rechazo]);

  const anyState = state as unknown as AnyState;
  const categoria = anyState._categoria || "combate";
  // Sin conexión ni estado del servidor, usar la última categoría conocida
  // del tatami (guardada abajo); en offline el juez puede cambiarla a mano.
  const categoriaGuardada = typeof window !== "undefined"
    ? localStorage.getItem(`dinamyt_categoria_${tatamiId}`)
    : null;
  const catServidor = hasServerState
    ? (isFiguras(anyState) ? "figuras" : "combate")
    : (categoriaGuardada === "figuras" ? "figuras" : "combate");
  const catActiva = offline && catOffline ? catOffline : catServidor;
  const esFiguras = catActiva === "figuras";
  const nombreCategoria = anyState._nombre_categoria || (isFiguras(anyState) ? anyState.nombre_categoria : "") || t("tat.figuras");
  // Número visible del tatami dentro de su campeonato (no el ID interno)
  const tatamiLabel = String(anyState._tatami_numero ?? tatamiId);

  // Recordar la categoría activa para el arranque sin conexión
  useEffect(() => {
    if (hasServerState) {
      try {
        localStorage.setItem(`dinamyt_categoria_${tatamiId}`, isFiguras(anyState) ? "figuras" : "combate");
      } catch { /* */ }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasServerState, categoria, tatamiId]);

  const isArbitro = rol === "arbitro";
  const isPantalla = rol === "pantalla";

  useEffect(() => {
    if (
      state.ganadorPendienteCierre
      && state.ganadorPendienteNombre
      && (state.ganadorPendienteColor === "hong" || state.ganadorPendienteColor === "chung")
    ) {
      alertSystem.showGanador({
        nombre: state.ganadorPendienteNombre,
        color: state.ganadorPendienteColor,
        motivo: state.ganadorPendienteMotivo,
      });
    } else if (!state.ganadorPendienteCierre) {
      alertSystem.clearGanador();
    }
  }, [
    state.ganadorPendienteCierre,
    state.ganadorPendienteNombre,
    state.ganadorPendienteColor,
    state.ganadorPendienteMotivo,
  ]);

  // Auth check
  useEffect(() => {
    if (!isPantalla) {
      const user = localStorage.getItem("dinamyt_user");
      if (!user) { router.replace("/login"); }
    }
  }, [isPantalla, router]);

  function getRolBack() {
    const user = localStorage.getItem("dinamyt_user");
    if (!user) return "/login";
    if (JSON.parse(user).rol !== "admin") return "/juez";
    // El admin vuelve a los tatamis del campeonato de este tatami,
    // no hasta la lista general de campeonatos.
    const campId = anyState._campeonato_id;
    return campId ? `/admin/campeonato/${campId}` : "/admin";
  }

  function handleVolver() {
    alertSystem.showConfirm({
      titulo: t("tat.volver.titulo"),
      mensaje: t("tat.volver.mensaje"),
      tipo: "info",
      confirmLabel: t("alert.volver"),
      onConfirm: () => router.push(getRolBack()),
    });
  }

  function handleChangeCategoria(cat: string) {
    if (cat === categoria) return;
    if (esFiguras && figurasConDatos(anyState as FigurasState)) {
      alertSystem.showConfirm({
        titulo: t("tat.figCurso.titulo"),
        mensaje: t("tat.figCurso.mensaje"),
        tipo: "peligro",
        solo_ok: true,
        onConfirm: () => {},
      });
      return;
    }
    const combateState = state as CombateState;
    if (combateActivo(combateState)) {
      alertSystem.showConfirm({
        titulo: t("tat.combCurso.titulo"),
        mensaje: t("tat.combCurso.mensaje"),
        tipo: "peligro",
        solo_ok: true,
        onConfirm: () => {},
      });
      return;
    }
    enviarEvento("cambiar_categoria", { categoria: cat });
  }

  function handleClearGanador() {
    if (isArbitro && state.ganadorPendienteCierre) {
      enviarEvento("cerrar_ganador");
    }
    alertSystem.clearGanador();
  }

  // Este rol se abrió en otro dispositivo/pestaña: el servidor reemplazó esta
  // sesión (así una recarga en otro equipo nunca queda bloqueada afuera).
  // No pelear la conexión: el juez decide si retoma aquí.
  if (sesionReemplazada && !isPantalla) {
    return (
      <div style={{ minHeight: "100dvh", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
        <div className="card" style={{ maxWidth: 460, width: "100%", textAlign: "center" }}>
          <Logo stacked fontSize="1.9rem" style={{ marginBottom: 12 }} />
          <div style={{ color: "var(--orange)", fontWeight: 800, fontSize: "1.05rem", marginBottom: 8 }}>
            {t("tat.sesion.titulo")}
          </div>
          <p style={{ color: "var(--text-muted)", marginBottom: 16, fontSize: "0.9rem" }}>
            {t("tat.sesion.mensaje", { rol: rol === "arbitro" ? t("rol.arbitro") : rol.toUpperCase() })}
          </p>
          <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
            <button className="btn btn-primary" onClick={reconectar}>
              {t("tat.sesion.retomar")}
            </button>
            <button className="btn" onClick={() => router.push(getRolBack())}>
              {t("alert.volver")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Solo es un rechazo real si el SERVIDOR negó el rol (mensaje en español
  // desde nuestro backend). Los fallos de red ("websocket error", "timeout",
  // "xhr poll error"...) NO expulsan al juez: se atienden con el modo offline.
  const esRechazoDeRol = Boolean(
    socketError && !/websocket|xhr|timeout|transport|polling|network/i.test(socketError)
  );
  if (esRechazoDeRol && !isPantalla) {
    return (
      <div style={{ minHeight: "100dvh", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
        <div className="card" style={{ maxWidth: 460, width: "100%", textAlign: "center" }}>
          <Logo stacked fontSize="1.9rem" style={{ marginBottom: 12 }} />
          <div style={{ color: "var(--gold)", fontWeight: 800, fontSize: "1rem", marginBottom: 8 }}>
            {t("tat.rolNoDisponible")}
          </div>
          <p style={{ color: "var(--text-muted)", marginBottom: 16 }}>
            {socketError}
          </p>
          <button className="btn btn-primary" onClick={() => router.push(getRolBack())}>
            {t("alert.volver")}
          </button>
        </div>
      </div>
    );
  }

  // Sin estado del servidor: mientras no se confirme el corte es una espera
  // breve (splash). Con el corte confirmado, los jueces NO se quedan
  // esperando: entran directo al modo de registro local (la pantalla pública
  // sí necesita el servidor). La pantalla pública nunca se queda muda en
  // "Cargando": muestra el corte y sigue reintentando sola.
  if (!hasServerState && (!offline || isPantalla)) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 18, alignItems: "center", justifyContent: "center", height: "100dvh", padding: 20 }}>
        <Logo stacked className="animate-fade" fontSize="2.4rem" />
        {offline ? (
          <div style={{ textAlign: "center", maxWidth: 440 }}>
            <p style={{ color: "var(--red-alert)", fontWeight: 800, fontSize: "1rem", letterSpacing: "0.06em", marginBottom: 6 }}>
              {t("tat.offline.titulo")}
            </p>
            <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginBottom: 14 }}>
              {t("tat.offline.mensaje")}
            </p>
            <button className="btn btn-primary btn-sm" onClick={() => window.location.reload()}>
              {t("tat.offline.reintentar")}
            </button>
          </div>
        ) : (
          <p style={{ color: "var(--text-dim)", fontSize: "0.9rem" }}>
            {t("tat.conectando")}
          </p>
        )}
      </div>
    );
  }

  // Pantalla pública — sin auth, renderizar inmediatamente
  if (isPantalla) {
    if (anyState._tatami_activo === false) {
      return (
        <div style={{ height: "100dvh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
          <Logo stacked fontSize="clamp(2rem, 6vw, 3rem)" style={{ marginBottom: 16 }} />
          <div style={{ fontSize: "2.5rem", color: "var(--text-dim)", fontFamily: "var(--font-display)", letterSpacing: "0.15em", marginBottom: 8 }}>
            {t("tat.tatamiMayus")} {tatamiLabel}
          </div>
          <div style={{ color: "var(--orange)", fontSize: "1.2rem", fontWeight: 700, letterSpacing: "0.1em" }}>
            {t("tat.desactivadoPantalla")}
          </div>
          <PublicControls />
        </div>
      );
    }

    return (
      <div style={{ position: "relative" }}>
        <AlertSystem
          alerts={alertSystem.alerts}
          onClearGanador={handleClearGanador}
          onClearDerrota={alertSystem.clearDerrota}
          onClearConfirm={alertSystem.clearConfirm}
          isPantalla
          canCloseGanador={false}
          canCloseAlerta12={false}
        />
        {esFiguras
          ? <FigurasPantalla state={anyState as FigurasState} tatamiId={tatamiLabel} />
          : <CombatePantalla
              state={state}
              tatamiId={tatamiLabel}
              connected={connected}
            />
        }
        {/* Sin sesión no hay menú global: controles propios de tema e idioma */}
        <PublicControls />
      </div>
    );
  }

  // Juez / Árbitro
  return (
    <div style={{ minHeight: "100dvh" }}>
      {/* Global alert system */}
      <AlertSystem
        alerts={alertSystem.alerts}
        onClearGanador={handleClearGanador}
        onClearDerrota={alertSystem.clearDerrota}
        onClearConfirm={alertSystem.clearConfirm}
        canCloseGanador={isArbitro}
        canCloseAlerta12={isArbitro}
        onAlerta12Reanudar={() => {
          if (isArbitro) enviarEvento("cerrar_alerta12", { reanudar: true });
        }}
        onAlerta12Ganador={() => {
          if (!isArbitro || !state.alerta12Data) return;
          const color = state.alerta12Data.lider === "Hong" ? "hong" : "chung";
          enviarEvento("declarar_ganador", { color, motivo: "Superioridad técnica" });
        }}
      />

      {/* Top bar */}
      <div className="tatami-topbar" style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "8px 14px",
        background: "var(--bg-card)", borderBottom: "1px solid var(--border)",
        position: "sticky", top: 0, zIndex: 100,
      }}>
        {/* Left: Volver */}
        <button className="btn btn-ghost btn-sm" onClick={handleVolver}
          style={{ gap: 4 }}>
          {t("comun.volver")}
        </button>

        {/* Center: estado + categoría selector */}
        <div className="tatami-topbar-center" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className={`status-dot ${connected ? "online" : "offline"}`} />
          <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>T{tatamiLabel}</span>
          {!esFiguras && typeof anyState._num_combate === "number" && anyState._num_combate > 0 && (
            <span style={{
              fontSize: "0.8rem", fontWeight: 800, color: "var(--gold)",
              border: "1px solid var(--gold-border)", background: "var(--gold-bg)",
              borderRadius: "var(--radius-sm)", padding: "2px 8px", whiteSpace: "nowrap",
            }}>
              {t("tat.combateNumTop", { n: anyState._num_combate })}
            </span>
          )}
          {/* El selector online de categoría se oculta sin conexión:
              en offline manda el selector local de la barra roja */}
          {isArbitro && !offline && <CatSelector current={categoria} onSelect={handleChangeCategoria} figurasLabel={nombreCategoria} />}
          {!isArbitro && (
            <span style={{ fontSize: "0.8rem", color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
              {categoria === "figuras" ? t("tat.figuras") : t("tat.combate")} · {rol.toUpperCase()}
            </span>
          )}
        </div>

        {/* Right: rol label + tatami activo */}
        <div className="tatami-topbar-right" style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {isArbitro && (
            <button
              className={`tatami-active-btn btn btn-sm ${anyState._tatami_activo ? "btn-primary" : "btn-danger"}`}
              onClick={() => {
                if (anyState._tatami_activo) {
                  alertSystem.showConfirm({
                    titulo: t("tat.desactivarTatami.titulo"),
                    mensaje: t("tat.desactivarTatami.mensaje"),
                    tipo: "peligro",
                    confirmLabel: t("comun.desactivar"),
                    onConfirm: () => enviarEvento("desactivar_tatami"),
                  });
                } else {
                  enviarEvento("activar_tatami");
                }
              }}
              style={{ fontWeight: 800, padding: "6px 12px", fontSize: "0.78rem", minHeight: 32 }}
            >
              {anyState._tatami_activo ? t("tat.activo") : t("tat.desactivado")}
            </button>
          )}
          <span className="tatami-topbar-rol-label" style={{ fontSize: "0.8rem", color: "var(--text-dim)" }}>
            {isArbitro ? t("rol.arbitro") : rol.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Estilos del topbar — a nivel de página para que apliquen en
          combate Y figuras (antes vivían dentro de FigurasScoreCard). */}
      <style>{`
        .tatami-topbar {
          flex-wrap: wrap;
          gap: 8px;
          max-width: 100%;
        }
        .tatami-topbar > * {
          min-width: 0;
        }
        .tatami-topbar-center {
          min-width: 0;
          flex: 1 1 auto;
          justify-content: center;
          flex-wrap: wrap;
        }
        .tatami-topbar-right {
          flex: 0 1 auto;
          flex-wrap: wrap;
          justify-content: flex-end;
          min-width: 0;
        }
        .tatami-active-btn {
          min-width: 0;
          max-width: 100%;
          line-height: 1.1;
          white-space: nowrap;
          flex: 0 1 auto;
        }
        @media (max-width: 640px) {
          .tatami-topbar {
            align-items: stretch !important;
            padding: 8px 10px !important;
          }
          .tatami-topbar > .btn {
            flex: 0 1 auto;
          }
          .tatami-topbar-center {
            order: 3;
            flex-basis: 100%;
            justify-content: flex-start;
            overflow-x: auto;
            padding-bottom: 2px;
          }
          .tatami-topbar-right {
            flex: 1 1 auto;
            gap: 8px !important;
            align-items: center;
          }
          .tatami-topbar-rol-label {
            display: none;
          }
          .tatami-active-btn {
            min-height: 40px;
            height: auto !important;
            padding: 8px 10px !important;
            flex: 1 1 auto;
            font-size: 0.8rem !important;
          }
        }
        @media (max-width: 380px) {
          .tatami-active-btn {
            white-space: normal;
            word-break: break-word;
          }
        }
      `}</style>

      {/* Panel de conexiones: solo el Juez Central, con datos frescos */}
      {isArbitro && connected && (
        <ConexionJueces
          conectados={anyState._roles_conectados || {}}
          numJueces={esFiguras
            ? ((anyState as FigurasState).num_jueces || 4)
            : ((state as CombateState).numJueces || 4)}
        />
      )}

      {/* Content */}
      <div style={{ position: "relative", flex: 1 }}>
        {!offline && anyState._tatami_activo === false && !isArbitro && (
          <div style={{
            position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(15,15,25,0.85)", zIndex: 50,
            display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
            backdropFilter: "blur(4px)"
          }}>
            <div style={{ fontSize: "2rem", marginBottom: 12 }}>⏸️</div>
            <div style={{ color: "var(--orange)", fontWeight: 800, fontSize: "1.2rem", letterSpacing: "0.05em" }}>{t("tat.desactivadoOverlay")}</div>
            <div style={{ color: "var(--text-muted)", marginTop: 8 }}>{t("tat.esperandoActivacion")}</div>
          </div>
        )}

        {/* Selector offline: el juez decide qué registrar mientras no haya conexión */}
        {offline && (
          <div style={{
            display: "flex", flexDirection: "column", gap: 8, alignItems: "center",
            padding: "10px 14px", marginBottom: 4,
            background: "rgba(232,0,42,0.08)", borderBottom: "1px solid var(--red-alert)",
          }}>
            <span style={{ color: "var(--red-alert)", fontWeight: 800, fontSize: "0.85rem", letterSpacing: "0.06em", textAlign: "center" }}>
              {t("tat.offSelector")}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className={`btn btn-sm ${!esFiguras ? "btn-primary" : ""}`}
                onClick={() => setCatOffline("combate")}
              >
                {t("tat.combate")}
              </button>
              <button
                className={`btn btn-sm ${esFiguras ? "btn-primary" : ""}`}
                onClick={() => setCatOffline("figuras")}
              >
                {t("tat.figuras")}
              </button>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", textAlign: "center", margin: 0, maxWidth: 420 }}>
              {t("tat.offSelectorNota")}
            </p>
          </div>
        )}

        {esFiguras ? (
          // En offline el JC también usa la libreta local de figuras
          // (el panel de gestión necesita servidor)
          isArbitro && !offline
            ? <FigurasArbitro
                state={anyState as FigurasState}
                enviarEvento={enviarEvento}
                tatamiId={tatamiLabel}
                tatamiDbId={tatamiId}
                onShowConfirm={alertSystem.showConfirm}
              />
            : <FigurasJuez state={anyState as FigurasState} enviarEvento={enviarEvento} juezId={rol} connected={connected} />
        ) : (
          isArbitro
            ? <CombateArbitro
                state={state}
                enviarEvento={enviarEvento}
                tatamiId={tatamiLabel}
                tatamiDbId={tatamiId}
                connected={connected}
                onFlash={alertSystem.showFlash}
                onFaltaFlash={alertSystem.showFaltaFlash}
                onShowConfirm={alertSystem.showConfirm}
                broadcast={broadcast}
              />
            : <CombateJuez
                state={state}
                rol={rol}
                enviarEvento={enviarEvento}
                pendingEvents={pendingEvents}
                connected={connected}
                onFlash={alertSystem.showFlash}
                registroResuelto={registroResuelto}
              />
        )}
      </div>
    </div>
  );
}

export default function TatamiPage() {
  return (
    <Suspense fallback={
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100dvh" }}>
        <Logo stacked className="animate-fade" fontSize="2.4rem" />
      </div>
    }>
      <TatamiContent />
    </Suspense>
  );
}
