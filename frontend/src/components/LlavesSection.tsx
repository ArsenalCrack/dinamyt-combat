"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  combinarLlavesAPI,
  createLlaveAPI,
  updateLlaveAPI,
  listLlavesAPI,
  listTatamisAPI,
  marcarGanadorLlaveAPI,
  moverCompetidorLlaveAPI,
  deleteLlaveAPI,
  descargarLlavePdfAPI,
  type LlaveData,
  type TipoLlave,
  type EstadoLlave,
} from "@/lib/api";
import { CATEGORIAS_FIGURAS, CATEGORIA_NOMBRE_MAX, normalizarCategoria } from "@/lib/categorias";
import BracketTree from "@/components/BracketTree";
import PodioLlave from "@/components/PodioLlave";
import SelectMenu from "@/components/SelectMenu";
import { useConfirmDialog } from "@/components/ConfirmDialog";
import { useI18n } from "@/lib/i18n";
import { aviso } from "@/lib/toast";

interface NuevoCompetidor {
  nombre: string;
  club: string;
}

type TipoMensaje = "ok" | "error";
type FiltroTipo = "todas" | "combate" | "figuras";
type FiltroEstado = "todas" | EstadoLlave;

const ORDEN_ESTADO: Record<EstadoLlave, number> = { activa: 0, pendiente: 1, terminada: 2 };

const OTRA = "__otra__";

export default function LlavesSection({ campeonatoId }: { campeonatoId: number }) {
  const { t } = useI18n();
  const [llaves, setLlaves] = useState<LlaveData[]>([]);
  const [tatamis, setTatamis] = useState<{ id: number; numero: number }[]>([]);
  const [filtroTatami, setFiltroTatami] = useState("");
  const [filtroTipo, setFiltroTipo] = useState<FiltroTipo>("todas");
  const [filtroEstado, setFiltroEstado] = useState<FiltroEstado>("todas");
  const [abierta, setAbierta] = useState<number | null>(null);
  // Selección múltiple de llaves pendientes para combinarlas en una sola
  const [seleccionadas, setSeleccionadas] = useState<Set<number>>(new Set());

  // ── Formulario (crear / editar) ──
  const [creando, setCreando] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [tipoForm, setTipoForm] = useState<TipoLlave>("combate");
  const [nombre, setNombre] = useState("");
  const [categoriaSel, setCategoriaSel] = useState<string>(CATEGORIAS_FIGURAS[0]);
  const [descripcion, setDescripcion] = useState("");
  const [tatamiId, setTatamiId] = useState("");
  const [compNombre, setCompNombre] = useState("");
  const [compClub, setCompClub] = useState("");
  const [competidores, setCompetidores] = useState<NuevoCompetidor[]>([]);

  const [guardando, setGuardando] = useState(false);
  const { pedirConfirmacion, dialogo } = useConfirmDialog();

  const cargar = useCallback(async () => {
    try {
      const [data, tt] = await Promise.all([
        listLlavesAPI(campeonatoId),
        listTatamisAPI(campeonatoId),
      ]);
      setLlaves(data);
      setTatamis(
        (tt as { id: number; numero: number }[]).map((x) => ({ id: x.id, numero: x.numero }))
      );
      // Limpiar selecciones de llaves que ya no existen o dejaron de estar pendientes
      setSeleccionadas((prev) => {
        const validas = new Set(
          data.filter((l) => l.estado === "pendiente").map((l) => l.id)
        );
        return new Set([...prev].filter((id) => validas.has(id)));
      });
    } catch { /* */ }
  }, [campeonatoId]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => { if (!cancelled) void cargar(); });
    return () => { cancelled = true; };
  }, [cargar]);

  /** Avisa del resultado de una acción con la nube flotante (ver lib/toast). */
  function flash(texto: string, tipo: TipoMensaje = "error") {
    aviso(texto, tipo);
  }

  const MAX_COMPETIDORES = tipoForm === "figuras" ? 50 : 64;
  const MIN_COMPETIDORES = tipoForm === "figuras" ? 2 : 3;

  // ── Alta de competidores (nombre y club por aparte) ──
  function agregarCompetidor() {
    const nom = compNombre.trim();
    if (!nom) return;
    if (competidores.length >= MAX_COMPETIDORES) {
      flash(t("llv.maxComp", { n: MAX_COMPETIDORES }));
      return;
    }
    if (competidores.some((c) => c.nombre.toLowerCase() === nom.toLowerCase())) {
      flash(t("llv.yaEnLista", { nombre: nom }));
      return;
    }
    setCompetidores((prev) => [...prev, { nombre: nom, club: compClub.trim() }]);
    setCompNombre("");
    setCompClub("");
  }

  function quitarCompetidor(idx: number) {
    const comp = competidores[idx];
    if (!comp) return;
    pedirConfirmacion({
      titulo: t("llv.quitarComp.titulo"),
      mensaje: t("llv.quitarComp.mensaje", {
        nombre: comp.nombre,
        club: comp.club ? ` (${comp.club})` : "",
      }),
      tipo: "advertencia",
      confirmLabel: t("comun.quitar"),
      onConfirm: () => setCompetidores((prev) => prev.filter((_, i) => i !== idx)),
    });
  }

  // ── Abrir formulario ──
  function resetForm() {
    setNombre("");
    setCategoriaSel(CATEGORIAS_FIGURAS[0]);
    setDescripcion("");
    setTatamiId("");
    setCompNombre("");
    setCompClub("");
    setCompetidores([]);
  }

  function abrirCrear() {
    resetForm();
    setEditandoId(null);
    setTipoForm("combate");
    setCreando(true);
  }

  function abrirEditar(llave: LlaveData) {
    setEditandoId(llave.id);
    setTipoForm(llave.tipo);
    setNombre(llave.nombre);
    setDescripcion(llave.descripcion || "");
    setTatamiId(llave.tatami_id ? String(llave.tatami_id) : "");
    if (llave.tipo === "figuras") {
      setCategoriaSel(
        (CATEGORIAS_FIGURAS as readonly string[]).includes(llave.nombre) ? llave.nombre : OTRA
      );
    }
    setCompetidores(
      (llave.estructura.competidores || []).map((c) => ({ nombre: c.nombre, club: c.club || "" }))
    );
    setCompNombre("");
    setCompClub("");
    setCreando(true);
    setAbierta(null);
  }

  function cerrarForm() {
    setCreando(false);
    setEditandoId(null);
    resetForm();
  }

  // El nombre efectivo de figuras viene del desplegable (o del texto si "Otra")
  const nombreFiguras = categoriaSel === OTRA ? normalizarCategoria(nombre) : categoriaSel;
  const nombreEfectivo = tipoForm === "figuras" ? nombreFiguras : nombre.trim();

  async function handleGuardar(e: React.FormEvent) {
    e.preventDefault();
    if (!nombreEfectivo) {
      flash(tipoForm === "figuras" ? t("llv.seleccionaCat") : t("llv.escribeNombre"));
      return;
    }
    if (competidores.length < MIN_COMPETIDORES) {
      flash(
        tipoForm === "figuras"
          ? t("llv.minFiguras", { n: MIN_COMPETIDORES })
          : t("llv.minCombate")
      );
      return;
    }
    setGuardando(true);
    try {
      if (editandoId) {
        const res = await updateLlaveAPI(editandoId, {
          nombre: nombreEfectivo,
          descripcion: tipoForm === "figuras" ? descripcion.trim() : undefined,
          tatami_id: tatamiId ? Number(tatamiId) : null,
          competidores,
        });
        cerrarForm();
        await cargar();
        setAbierta(res.llave.id);
        flash(t("llv.actualizada"), "ok");
      } else {
        const res = await createLlaveAPI({
          campeonato_id: campeonatoId,
          tipo: tipoForm,
          tatami_id: tatamiId ? Number(tatamiId) : null,
          nombre: nombreEfectivo,
          descripcion: tipoForm === "figuras" ? descripcion.trim() : undefined,
          competidores,
        });
        cerrarForm();
        await cargar();
        setAbierta(res.llave.id);
        flash(tipoForm === "figuras" ? t("llv.grupoCreado") : t("llv.creada"), "ok");
      }
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("llv.errorGuardar"));
    } finally {
      setGuardando(false);
    }
  }

  async function handleGanador(llave: LlaveData, ronda: number | "bronce", partido: number, lado: 1 | 2) {
    const p = ronda === "bronce" ? llave.estructura.bronce : llave.estructura.rondas[ronda]?.[partido];
    if (!p) return;
    // Si ya era el ganador, des-marcar (corrección); si no, marcar.
    const nuevo = p.ganador === lado ? null : lado;
    try {
      const res = await marcarGanadorLlaveAPI(llave.id, { ronda, partido, ganador: nuevo });
      setLlaves((prev) => prev.map((l) => (l.id === llave.id ? res.llave : l)));
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("llv.errorResultado"));
    }
  }

  async function handleDescargarPdf(llave: LlaveData) {
    try {
      const blob = await descargarLlavePdfAPI(llave.id);
      const slug = llave.nombre.replace(/[^A-Za-z0-9]+/g, "-").toLowerCase().slice(0, 40) || "llave";
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `dinamyt_llave_${slug}.pdf`;
      a.click();
      URL.revokeObjectURL(a.href);
      flash(t("llv.pdfOk"), "ok");
    } catch {
      flash(t("llv.pdfError"));
    }
  }

  function handleEliminar(llave: LlaveData) {
    pedirConfirmacion({
      titulo: t("llv.eliminar.titulo"),
      mensaje: t("llv.eliminar.mensaje", { nombre: llave.nombre }),
      tipo: "peligro",
      confirmLabel: t("comun.eliminar"),
      onConfirm: async () => {
        try {
          await deleteLlaveAPI(llave.id);
          setLlaves((prev) => prev.filter((l) => l.id !== llave.id));
          if (abierta === llave.id) setAbierta(null);
          flash(t("llv.eliminada"), "ok");
        } catch {
          flash(t("llv.errorEliminar"));
        }
      },
    });
  }

  // ── Combinar llaves pendientes seleccionadas ──
  function toggleSeleccion(id: number) {
    setSeleccionadas((prev) => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id);
      else s.add(id);
      return s;
    });
  }

  function handleCombinar() {
    const ids = [...seleccionadas];
    if (ids.length < 2) return;
    const primera = llaves.find((l) => l.id === ids[0]);
    pedirConfirmacion({
      titulo: t("llv.combinar.titulo"),
      mensaje: t("llv.combinar.mensaje", { n: ids.length, nombre: primera?.nombre || "" }),
      tipo: "advertencia",
      confirmLabel: t("llv.combinar.confirmar"),
      onConfirm: async () => {
        try {
          const res = await combinarLlavesAPI({ llave_ids: ids });
          setSeleccionadas(new Set());
          await cargar();
          setAbierta(res.llave.id);
          flash(res.message, "ok");
        } catch (err) {
          const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
          flash(m || t("llv.combinar.error"));
        }
      },
    });
  }

  // ── Mover un competidor a otra llave pendiente del mismo tipo ──
  function handleMover(origen: LlaveData, competidorId: number, destinoId: number) {
    const destino = llaves.find((l) => l.id === destinoId);
    const comp = (origen.estructura.competidores || []).find((c) => c.id === competidorId);
    if (!destino || !comp) return;
    const quedaVacia = (origen.estructura.competidores || []).length === 1;
    pedirConfirmacion({
      titulo: t("llv.mover.titulo"),
      mensaje: t("llv.mover.mensaje", {
        nombre: comp.nombre,
        origen: origen.nombre,
        destino: destino.nombre,
        vacia: quedaVacia ? t("llv.mover.origenVacia") : "",
      }),
      tipo: "advertencia",
      confirmLabel: t("llv.mover.confirmar"),
      onConfirm: async () => {
        try {
          const res = await moverCompetidorLlaveAPI({
            origen_id: origen.id,
            destino_id: destinoId,
            competidor_id: competidorId,
          });
          await cargar();
          setAbierta(res.destino.id);
          flash(res.message, "ok");
        } catch (err) {
          const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
          flash(m || t("llv.mover.error"));
        }
      },
    });
  }

  // ── Filtrado + orden ──
  const conteo = useMemo(() => ({
    todas: llaves.length,
    combate: llaves.filter((l) => l.tipo === "combate").length,
    figuras: llaves.filter((l) => l.tipo === "figuras").length,
  }), [llaves]);

  const llavesVisibles = useMemo(() => {
    return llaves
      .filter((l) => filtroTipo === "todas" || l.tipo === filtroTipo)
      .filter((l) => filtroEstado === "todas" || l.estado === filtroEstado)
      .filter((l) => {
        if (!filtroTatami) return true;
        if (filtroTatami === "__pool__") return !l.tatami_id;
        return String(l.tatami_id) === filtroTatami;
      })
      .sort((a, b) => ORDEN_ESTADO[a.estado] - ORDEN_ESTADO[b.estado]);
  }, [llaves, filtroTipo, filtroEstado, filtroTatami]);

  const estadoBadge: Record<EstadoLlave, { clase: string; texto: string }> = {
    pendiente: { clase: "badge-gray", texto: t("llv.estado.pendiente") },
    activa: { clase: "badge-green", texto: t("llv.estado.activa") },
    terminada: { clase: "badge-gold", texto: t("llv.estado.terminada") },
  };

  return (
    <div>
      {/* ── Cabecera: filtros de tipo + combinar + nueva ── */}
      <div className="llaves-toolbar">
        <div className="seg" role="tablist" aria-label={t("llv.filtroTipoAria")}>
          {(["todas", "combate", "figuras"] as FiltroTipo[]).map((ft) => (
            <button
              key={ft}
              type="button"
              role="tab"
              className={`seg-btn ${filtroTipo === ft ? "seg-on" : ""}`}
              onClick={() => setFiltroTipo(ft)}
              aria-selected={filtroTipo === ft}
            >
              {ft === "todas" ? t("llv.todas") : ft === "combate" ? t("tat.combate") : t("tat.figuras")}
              <span className="seg-count">{conteo[ft]}</span>
            </button>
          ))}
        </div>
        <div className="llaves-toolbar-right">
          <select
            className="input input-compact"
            value={filtroEstado}
            onChange={(e) => setFiltroEstado(e.target.value as FiltroEstado)}
            aria-label={t("llv.filtroEstadoAria")}
          >
            <option value="todas">{t("llv.todosEstados")}</option>
            <option value="pendiente">{t("llv.pendientes")}</option>
            <option value="activa">{t("llv.activas")}</option>
            <option value="terminada">{t("llv.terminadas")}</option>
          </select>
          <select
            className="input input-compact"
            value={filtroTatami}
            onChange={(e) => setFiltroTatami(e.target.value)}
            aria-label={t("llv.filtroTatamiAria")}
          >
            <option value="">{t("llv.todosTatamis")}</option>
            <option value="__pool__">{t("llv.sinAsignar")}</option>
            {tatamis.map((tt) => (
              <option key={tt.id} value={String(tt.id)}>{t("camp.tatami")} {tt.numero}</option>
            ))}
          </select>
          {seleccionadas.size >= 2 && (
            <button className="btn btn-sm" onClick={handleCombinar} style={{
              background: "var(--gold-bg)", borderColor: "var(--gold-border)", color: "var(--gold)",
            }}>
              {t("llv.combinarBtn", { n: seleccionadas.size })}
            </button>
          )}
          {!creando && (
            <button className="btn btn-primary btn-sm" onClick={abrirCrear}>{t("llv.nueva")}</button>
          )}
        </div>
      </div>

      {dialogo}

      {/* ── Formulario crear / editar ── */}
      {creando && (
        <form onSubmit={handleGuardar} className="card animate-slide"
          style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 14 }}>
          <div className="card-title">
            {editandoId ? t("llv.editarForm") : t("llv.nuevaForm")}{" "}
            {tipoForm === "figuras" ? t("llv.grupoFiguras") : t("llv.llaveElim")}
          </div>

          {/* Tipo (bloqueado al editar: no se cambia el tipo de una llave) */}
          <div className="seg" role="tablist" aria-label={t("llv.tipoAria")}>
            {(["combate", "figuras"] as TipoLlave[]).map((tp) => (
              <button
                key={tp}
                type="button"
                role="tab"
                className={`seg-btn ${tipoForm === tp ? "seg-on" : ""}`}
                onClick={() => !editandoId && setTipoForm(tp)}
                disabled={Boolean(editandoId) && tipoForm !== tp}
                aria-selected={tipoForm === tp}
                style={{ flex: 1 }}
              >
                {tp === "combate" ? t("llv.combateTab") : t("llv.figurasTab")}
              </button>
            ))}
          </div>

          {/* Nombre / categoría + tatami */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {tipoForm === "figuras" ? (
              <SelectMenu
                ariaLabel={t("tat.fig.categoriaAria")}
                value={categoriaSel}
                onChange={setCategoriaSel}
                options={[
                  ...CATEGORIAS_FIGURAS.map((c) => ({ value: c, label: c })),
                  { value: OTRA, label: t("llv.otraCategoria") },
                ]}
                style={{ flex: "2 1 220px" }}
              />
            ) : (
              <input
                className="input"
                placeholder={t("llv.nombrePh")}
                value={nombre}
                maxLength={120}
                onChange={(e) => setNombre(e.target.value)}
                style={{ flex: "2 1 220px" }}
                required
              />
            )}
            <select
              className="input"
              value={tatamiId}
              onChange={(e) => setTatamiId(e.target.value)}
              style={{ flex: "1 1 160px" }}
            >
              <option value="">{t("llv.sinAsignar")}</option>
              {tatamis.map((tt) => (
                <option key={tt.id} value={String(tt.id)}>{t("camp.tatami")} {tt.numero}</option>
              ))}
            </select>
          </div>

          {/* Figuras: nombre libre si "Otra" + descripción pública */}
          {tipoForm === "figuras" && (
            <>
              {categoriaSel === OTRA && (
                <input
                  className="input"
                  placeholder={t("llv.categoriaPh")}
                  value={nombre}
                  maxLength={CATEGORIA_NOMBRE_MAX}
                  onChange={(e) => setNombre(normalizarCategoria(e.target.value))}
                  style={{ textTransform: "uppercase" }}
                />
              )}
              <input
                className="input"
                placeholder={t("tat.fig.descPlaceholder")}
                value={descripcion}
                maxLength={120}
                onChange={(e) => setDescripcion(e.target.value)}
              />
            </>
          )}

          {/* Competidores */}
          <div className="card" style={{ background: "var(--bg-elevated)", padding: 12 }}>
            <div className="microetiqueta" style={{ marginBottom: 8 }}>
              {t("llv.competidoresMin", { n: competidores.length, min: MIN_COMPETIDORES })}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: competidores.length ? 10 : 0 }}>
              <input className="input" placeholder={t("tat.fig.nombreComp")} value={compNombre}
                onChange={(e) => setCompNombre(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); agregarCompetidor(); } }}
                style={{ flex: "2 1 180px" }} />
              <input className="input" placeholder={t("tat.fig.club")} value={compClub}
                onChange={(e) => setCompClub(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); agregarCompetidor(); } }}
                style={{ flex: "1 1 140px" }} />
              <button type="button" className="btn btn-primary"
                onClick={agregarCompetidor}
                disabled={!compNombre.trim() || competidores.length >= MAX_COMPETIDORES}>
                {t("tat.fig.agregarBtn")}
              </button>
            </div>
            {competidores.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 220, overflowY: "auto" }}>
                {competidores.map((c, i) => (
                  <div key={`${c.nombre}-${i}`} style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 10px", background: "var(--bg-card)",
                    border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                  }}>
                    <span style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: "0.82rem", minWidth: 22 }}>
                      {i + 1}.
                    </span>
                    <span style={{ flex: 1, fontWeight: 700, overflowWrap: "anywhere" }}>
                      {c.nombre}
                      {c.club && <span style={{ color: "var(--text-muted)", fontWeight: 500, marginLeft: 8, fontSize: "0.875rem" }}>{c.club}</span>}
                    </span>
                    <button type="button" className="btn btn-sm btn-danger"
                      onClick={() => quitarCompetidor(i)}
                      style={{ padding: "2px 8px", minHeight: 28, fontSize: "0.8rem" }}>
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", margin: 0 }}>
            {tipoForm === "figuras" ? t("llv.notaFiguras") : t("llv.notaCombate")}
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="submit" className="btn btn-primary" disabled={guardando || competidores.length < MIN_COMPETIDORES}>
              {guardando
                ? t("comp.guardando")
                : editandoId
                  ? t("comun.guardarCambios")
                  : tipoForm === "figuras"
                    ? t("llv.crearGrupo", { n: competidores.length })
                    : t("llv.crearSortear", { n: competidores.length })}
            </button>
            <button type="button" className="btn" onClick={cerrarForm}>{t("comun.cancelar")}</button>
          </div>
        </form>
      )}

      {/* ── Nota de combinar (visible cuando hay 2+ pendientes) ── */}
      {!creando && llaves.filter((l) => l.estado === "pendiente").length >= 2 && (
        <p style={{ color: "var(--text-dim)", fontSize: "0.82rem", margin: "0 0 10px" }}>
          {t("llv.combinar.nota")}
        </p>
      )}

      {/* ── Lista ── */}
      {llavesVisibles.length === 0 && !creando ? (
        <div className="card" style={{ textAlign: "center", padding: 24, color: "var(--text-dim)" }}>
          {llaves.length === 0 ? t("llv.vacio") : t("llv.sinFiltros")}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {llavesVisibles.map((llave) => (
            <LlaveCard
              key={llave.id}
              llave={llave}
              estadoBadge={estadoBadge}
              expandida={abierta === llave.id}
              seleccionada={seleccionadas.has(llave.id)}
              onSeleccionar={() => toggleSeleccion(llave.id)}
              destinosMover={llaves.filter(
                (l) => l.id !== llave.id && l.tipo === llave.tipo && l.estado === "pendiente"
              )}
              onToggle={() => setAbierta(abierta === llave.id ? null : llave.id)}
              onGanador={(r, p, lado) => handleGanador(llave, r, p, lado)}
              onMover={(compId, destinoId) => handleMover(llave, compId, destinoId)}
              onEditar={() => abrirEditar(llave)}
              onEliminar={() => handleEliminar(llave)}
              onPdf={() => handleDescargarPdf(llave)}
            />
          ))}
        </div>
      )}

      <style>{`
        .llaves-toolbar {
          display: flex; justify-content: space-between; align-items: center;
          gap: 10px; flex-wrap: wrap; margin-bottom: 12px;
        }
        .llaves-toolbar-right {
          display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
        }
        .seg {
          display: inline-flex; background: var(--bg-elevated);
          border: 1px solid var(--border); border-radius: var(--radius-sm);
          padding: 3px; gap: 2px;
        }
        .seg-btn {
          display: inline-flex; align-items: center; gap: 6px;
          padding: 6px 12px; min-height: 34px; border: none; cursor: pointer;
          background: transparent; color: var(--text-muted);
          font: inherit; font-size: 0.88rem; font-weight: 700;
          border-radius: calc(var(--radius-sm) - 2px); transition: all 0.15s;
        }
        .seg-btn:hover:not(.seg-on) { color: var(--text); }
        .seg-btn.seg-on { background: var(--gold); color: var(--text-on-gold, #1a1a1a); }
        .seg-btn:disabled { opacity: 0.45; cursor: not-allowed; }
        .seg-count {
          font-size: 0.78rem; font-weight: 800; padding: 1px 6px;
          border-radius: 999px; background: rgba(0,0,0,0.18);
        }
        .seg-btn.seg-on .seg-count { background: rgba(0,0,0,0.22); }
        .input-compact {
          width: auto; min-width: 140px; padding: 6px 30px 6px 12px; min-height: 34px;
        }
        .llave-check {
          width: 18px; height: 18px; accent-color: var(--gold);
          cursor: pointer; flex-shrink: 0;
        }
        @media (max-width: 560px) {
          .llaves-toolbar, .llaves-toolbar-right { width: 100%; }
          .seg { width: 100%; }
          .seg-btn { flex: 1; justify-content: center; }
          .input-compact { flex: 1 1 140px; min-width: 0; }
        }
      `}</style>
    </div>
  );
}

// ── Tarjeta de una llave (combate o figuras) ──
function LlaveCard({
  llave, estadoBadge, expandida, seleccionada, destinosMover,
  onToggle, onGanador, onMover, onSeleccionar, onEditar, onEliminar, onPdf,
}: {
  llave: LlaveData;
  estadoBadge: Record<EstadoLlave, { clase: string; texto: string }>;
  expandida: boolean;
  seleccionada: boolean;
  destinosMover: LlaveData[];
  onToggle: () => void;
  onGanador: (ronda: number | "bronce", partido: number, lado: 1 | 2) => void;
  onMover: (competidorId: number, destinoId: number) => void;
  onSeleccionar: () => void;
  onEditar: () => void;
  onEliminar: () => void;
  onPdf: () => void;
}) {
  const { t } = useI18n();
  const esFiguras = llave.tipo === "figuras";
  const estado = estadoBadge[llave.estado];
  const totalRondas = llave.estructura.rondas?.length || 0;
  const campeon = llave.estructura.campeon;
  const numComp = llave.estructura.competidores?.length || 0;
  const editable = llave.estado === "pendiente";

  return (
    <div className="card" style={{
      padding: 0, overflow: "hidden",
      borderColor: seleccionada ? "var(--gold-border)" : undefined,
    }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        {/* Checkbox de combinación: solo llaves pendientes */}
        {editable && (
          <label style={{ padding: "0 0 0 14px", display: "flex", alignItems: "center" }}>
            <input
              type="checkbox"
              className="llave-check"
              checked={seleccionada}
              onChange={onSeleccionar}
              aria-label={t("llv.seleccionarCombinar", { nombre: llave.nombre })}
              title={t("llv.combinar.nota")}
            />
          </label>
        )}
        <button
          type="button"
          onClick={onToggle}
          style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            gap: 10, width: "100%", padding: "14px 16px",
            background: "transparent", border: "none", color: "var(--text)",
            cursor: "pointer", font: "inherit", textAlign: "left",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              <span style={{ fontWeight: 800, fontSize: "1rem", overflowWrap: "anywhere" }}>
                {llave.nombre}
              </span>
              <span className={`badge ${esFiguras ? "badge-chung" : "badge-hong"}`}>
                {esFiguras ? t("tat.figuras") : t("tat.combate")}
              </span>
              {llave.seccion_clave && (
                <span className="badge badge-gray" title={t("llv.autoTitle")}>
                  {t("llv.auto")}
                </span>
              )}
              <span className={`badge ${estado.clase}`}>{estado.texto}</span>
              <span className="badge badge-gray">
                {llave.tatami_numero ? `${t("camp.tatami")} ${llave.tatami_numero}` : t("llv.sinTatami")}
              </span>
            </div>
            {llave.descripcion && (
              <div style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginTop: 4, overflowWrap: "anywhere" }}>
                {llave.descripcion}
              </div>
            )}
            <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: 2 }}>
              {numComp} {t("gen.competidores")}
              {!esFiguras && <> · {totalRondas} {t("llv.rondas")}</>}
              {campeon && (
                <span style={{ color: "var(--gold)", fontWeight: 800 }}> · 🏆 {campeon.nombre}</span>
              )}
            </div>
          </div>
          <span style={{ color: "var(--text-dim)", flexShrink: 0 }}>{expandida ? "▲" : "▼"}</span>
        </button>
      </div>

      {expandida && (
        <div className="animate-fade" style={{ padding: "0 16px 16px" }}>
          {esFiguras ? (
            <ListaCompetidores competidores={llave.estructura.competidores || []} />
          ) : (
            <>
              {campeon && (
                <div style={{ marginBottom: 12 }}>
                  <PodioLlave estructura={llave.estructura} titulo={t("llv.podio")} />
                </div>
              )}
              <BracketTree
                estructura={llave.estructura}
                variant="admin"
                onGanador={(r, p, lado) => onGanador(r, p, lado)}
              />
            </>
          )}

          {/* ── Mover competidores a otra llave pendiente del mismo tipo ── */}
          {editable && destinosMover.length > 0 && (llave.estructura.competidores || []).length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div className="microetiqueta" style={{ marginBottom: 6 }}>
                {t("llv.mover.competidores")}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {(llave.estructura.competidores || []).map((c) => (
                  <div key={c.id} style={{
                    display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
                    padding: "5px 10px", background: "var(--bg-elevated)",
                    border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                  }}>
                    <span style={{ flex: "1 1 140px", fontWeight: 700, fontSize: "0.9rem", overflowWrap: "anywhere" }}>
                      {c.nombre}
                      {c.club && <span style={{ color: "var(--text-muted)", fontWeight: 500, marginLeft: 6, fontSize: "0.84rem" }}>{c.club}</span>}
                    </span>
                    <select
                      className="input"
                      value=""
                      aria-label={`${t("llv.mover.label")} ${c.nombre}`}
                      onChange={(e) => {
                        const destinoId = Number(e.target.value);
                        if (destinoId) onMover(c.id, destinoId);
                        e.target.value = "";
                      }}
                      style={{ width: "auto", minWidth: 150, padding: "4px 26px 4px 10px", minHeight: 30, fontSize: "0.82rem" }}
                    >
                      <option value="">{t("llv.mover.label")}</option>
                      {destinosMover.map((d) => (
                        <option key={d.id} value={d.id}>{d.nombre}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <p style={{ color: "var(--text-dim)", fontSize: "0.82rem", margin: 0, flex: "1 1 200px" }}>
              {esFiguras
                ? editable
                  ? t("llv.notaEditableFig")
                  : t("llv.notaNoEditableFig")
                : t("llv.notaMarcar")}
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                className="btn btn-sm"
                onClick={onPdf}
                title={esFiguras ? t("llv.pdfFigTitle") : t("llv.pdfCombTitle")}
              >
                📄 PDF
              </button>
              {editable && (
                <button className="btn btn-sm" onClick={onEditar}>{t("llv.editarForm")}</button>
              )}
              <button className="btn btn-danger btn-sm" onClick={onEliminar}>{t("comun.eliminar")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ListaCompetidores({ competidores }: { competidores: { nombre: string; club?: string }[] }) {
  const { t } = useI18n();
  if (competidores.length === 0) {
    return <p style={{ color: "var(--text-dim)", fontSize: "0.88rem" }}>{t("llv.sinCompetidores")}</p>;
  }
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
      gap: 6, marginTop: 4,
    }}>
      {competidores.map((c, i) => (
        <div key={`${c.nombre}-${i}`} style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "6px 10px", background: "var(--bg-elevated)",
          border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
        }}>
          <span style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: "0.8rem", minWidth: 20 }}>
            {i + 1}.
          </span>
          <span style={{ fontWeight: 700, overflowWrap: "anywhere", fontSize: "0.9rem" }}>
            {c.nombre}
            {c.club && <span style={{ color: "var(--text-muted)", fontWeight: 500, marginLeft: 6, fontSize: "0.85rem" }}>{c.club}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}
