"use client";

import { Fragment, useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import api, { getCampeonatoAPI, idiomaArchivo, listTatamisAPI, resolverApiUrl, exportarResultadosAPI } from "@/lib/api";
import CampoFecha from "@/components/CampoFecha";
import PodioLlave from "@/components/PodioLlave";
import { Cargando } from "@/components/Cargando";
import type { PodioItem } from "@/lib/llaves";
import { useI18n, type ClaveTexto } from "@/lib/i18n";
import { obtenerToken } from "@/lib/sesion";

interface RankingItem {
  id?: number;
  nombre: string;
  club?: string;
  total: number;
  puesto?: number;
  empate?: boolean;
  especial?: boolean;
}

interface Combate {
  id: number;
  tipo?: "combate" | "figuras" | string;
  nombre_categoria?: string;
  descripcion?: string;
  nombre_hong: string;
  nombre_chung: string;
  marcador_hong: number;
  marcador_chung: number;
  ganador: "hong" | "chung" | "empate";
  ronda_final: string;
  rondas_resumen?: string;
  figuras_completas?: boolean | null;
  figuras_desempates?: { nombres: string[]; ts?: number }[];
  llave?: { llave_id: number; nombre: string; ronda_nombre: string } | null;
  num_jueces: number;
  tatami_numero: number;
  created_at: string;
  jueces?: JuezReporte[];
  ranking?: RankingItem[];
  podio_llave?: PodioItem[];
}

interface JuezReporte {
  rol_tatami: string;
  asignacion: string;
  nombre: string;
  email: string;
  origen: string;
}

interface CategoriaResumen {
  nombre: string;
  puntuacion: "combate" | "individual";
  cantidad: number;
}

interface ReportData {
  combates: Combate[];
  total: number;
  page: number;
  pages: number;
  per_page: number;
  categorias?: CategoriaResumen[];
}

interface TatamiOption {
  id: number;
  numero: number;
}

// Clave i18n de cada ronda del reporte (el texto vive en lib/i18n)
const RONDAS_CLAVE: Record<string, ClaveTexto> = {
  r1: "rep.ronda.r1", r2: "rep.ronda.r2", oro: "rep.ronda.oro", figuras: "rep.ronda.figuras",
};

function slugArchivo(texto: string, fallback = "reporte") {
  const limpio = texto
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^A-Za-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
  return limpio.slice(0, 40) || fallback;
}

function fechaArchivo() {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function getExportFilename(disposition: string | null, fallback: string) {
  if (!disposition) return fallback;
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1].replace(/"/g, ""));
  }
  const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
  return filenameMatch?.[1]?.trim() || fallback;
}

async function getExportError(res: Response) {
  const fallback = `No se pudo generar el reporte (${res.status}).`;
  const text = await res.text();
  if (!text) return fallback;
  try {
    const parsed = JSON.parse(text) as { error?: string; message?: string };
    return parsed.error || parsed.message || fallback;
  } catch {
    return text.slice(0, 180) || fallback;
  }
}

export default function ReportesCampeonatoPage() {
  const router = useRouter();
  const { t } = useI18n();
  const params = useParams();
  const campId = String(params.id);

  const [campNombre, setCampNombre] = useState("");
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<string | null>(null);
  const [exportError, setExportError] = useState("");
  const [tatamis, setTatamis] = useState<TatamiOption[]>([]);
  const [splitZip, setSplitZip] = useState(false);
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const [podioAbierto, setPodioAbierto] = useState<Set<number>>(new Set());
  const [filters, setFilters] = useState({
    tatami_id: "",
    tipo: "",
    categoria: "",
    desde: "",
    hasta: "",
    page: 1,
  });

  useEffect(() => {
    const user = localStorage.getItem("dinamyt_user");
    if (!user || JSON.parse(user).rol !== "admin") {
      router.replace("/login"); return;
    }
  }, [router]);

  // Nombre del campeonato + sus tatamis
  useEffect(() => {
    let cancelled = false;
    queueMicrotask(async () => {
      try {
        const [c, t] = await Promise.all([
          getCampeonatoAPI(Number(campId)),
          listTatamisAPI(Number(campId)),
        ]);
        if (cancelled) return;
        setCampNombre(c.nombre);
        setTatamis((t as TatamiOption[]).map((x) => ({ id: x.id, numero: x.numero })));
      } catch {
        if (!cancelled) router.replace("/admin");
      }
    });
    return () => { cancelled = true; };
  }, [campId, router]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const qp: Record<string, string> = {
        per_page: "30",
        campeonato_id: campId,
        page: String(filters.page),
      };
      if (filters.tatami_id) qp.tatami_id = filters.tatami_id;
      if (filters.tipo) qp.tipo = filters.tipo;
      if (filters.categoria) qp.categoria = filters.categoria;
      if (filters.desde) qp.desde = filters.desde;
      if (filters.hasta) qp.hasta = filters.hasta;

      const res = await api.get("/reportes/combates", { params: qp });
      setData(res.data);
    } catch {
      //
    } finally {
      setLoading(false);
    }
  }, [filters, campId]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void fetchData();
    });
    return () => { cancelled = true; };
  }, [fetchData]);

  function toggleSeleccion(id: number) {
    setSeleccion((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSeleccionTodos() {
    if (!data) return;
    setSeleccion((prev) => {
      const visibles = data.combates.map((c) => c.id);
      const todosMarcados = visibles.every((id) => prev.has(id));
      const next = new Set(prev);
      visibles.forEach((id) => (todosMarcados ? next.delete(id) : next.add(id)));
      return next;
    });
  }

  async function descargar(url: string, fallbackName: string, claveExporting: string) {
    setExporting(claveExporting);
    setExportError("");
    try {
      // La descarga va por fetch, no por el cliente axios, así que hay que
      // pedir las cookies a mano: `credentials` es lo que manda la de sesión.
      const token = obtenerToken();
      const res = await fetch(url, {
        credentials: "include",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) throw new Error(await getExportError(res));

      const contentType = res.headers.get("content-type") || "";
      const esArchivo = contentType.includes("application/pdf")
        || contentType.includes("spreadsheetml")
        || contentType.includes("application/zip")
        || contentType.includes("application/octet-stream");
      if (!esArchivo) {
        throw new Error(t("err.reporteNoArchivo"));
      }

      const blob = await res.blob();
      if (blob.size === 0) throw new Error(t("err.reporteVacio"));

      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = getExportFilename(res.headers.get("content-disposition"), fallbackName);
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : t("rep.errorGenerar"));
    } finally {
      setExporting(null);
    }
  }

  function buildParams(extra: Record<string, string> = {}) {
    const qp: Record<string, string> = { campeonato_id: campId, lang: idiomaArchivo(), ...extra };
    if (filters.tatami_id) qp.tatami_id = filters.tatami_id;
    if (filters.tipo) qp.tipo = filters.tipo;
    if (filters.categoria) qp.categoria = filters.categoria;
    if (filters.desde) qp.desde = filters.desde;
    if (filters.hasta) qp.hasta = filters.hasta;
    return new URLSearchParams(qp).toString();
  }

  // Reporte GENERAL de todo el campeonato (con filtros aplicados)
  function handleExportGeneral(type: "pdf" | "excel") {
    const apiUrl = resolverApiUrl();
    const url = splitZip
      ? `${apiUrl}/api/reportes/combates/export/zip?${buildParams({ formato: type })}`
      : `${apiUrl}/api/reportes/combates/export/${type}?${buildParams()}`;
    const ext = splitZip ? "zip" : (type === "pdf" ? "pdf" : "xlsx");
    const fallback = `dinamyt_${slugArchivo(campNombre, "campeonato")}_general_${fechaArchivo()}.${ext}`;
    void descargar(url, fallback, `general-${type}`);
  }

  // Reporte SOLO de los registros seleccionados con checkbox
  function handleExportSeleccion(type: "pdf" | "excel") {
    if (seleccion.size === 0) return;
    const apiUrl = resolverApiUrl();
    const ids = Array.from(seleccion).sort((a, b) => a - b).join(",");
    const qp = new URLSearchParams({ campeonato_id: campId, ids, lang: idiomaArchivo() }).toString();
    const url = `${apiUrl}/api/reportes/combates/export/${type}?${qp}`;
    const fallback = `dinamyt_${slugArchivo(campNombre, "campeonato")}_seleccion-${seleccion.size}_${fechaArchivo()}.${type === "pdf" ? "pdf" : "xlsx"}`;
    void descargar(url, fallback, `seleccion-${type}`);
  }

  // Exporta los resultados del campeonato a un .json para IMPORTARLO en la
  // instancia online (software de la red) y publicarlos ahí. Ver /resultados.
  async function handleExportarResultados() {
    setExporting("resultados-json");
    setExportError("");
    try {
      const blob = await exportarResultadosAPI(Number(campId));
      if (blob.size === 0) throw new Error(t("err.resultadosVacio"));
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `resultados-${slugArchivo(campNombre, "campeonato")}_${fechaArchivo()}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "No se pudo exportar los resultados.");
    } finally {
      setExporting(null);
    }
  }

  function togglePodio(id: number) {
    setPodioAbierto((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function ganadorNombre(c: Combate) {
    if (c.tipo === "figuras") return c.ranking?.[0]?.nombre || c.nombre_hong || "—";
    if (c.ganador === "hong") return c.nombre_hong;
    if (c.ganador === "chung") return c.nombre_chung;
    return t("rep.empate");
  }

  function ganadorColor(c: Combate) {
    if (c.tipo === "figuras") return "badge-gold";
    if (c.ganador === "hong") return "badge-hong";
    if (c.ganador === "chung") return "badge-chung";
    return "badge-gray";
  }

  const todosVisiblesMarcados = Boolean(
    data && data.combates.length > 0 && data.combates.every((c) => seleccion.has(c.id))
  );

  return (
    <div className="reportes-page">
      {/* Header */}
      <div className="reportes-header">
        <div>
          <button className="btn btn-outline btn-sm" onClick={() => router.push(`/admin/campeonato/${campId}`)}
            style={{ marginBottom: 8 }}>
            {t("ins.volver")}
          </button>
          <h1 className="display" style={{ fontSize: "1.5rem" }}>
            {t("rep.titulo")} {campNombre || "..."}
          </h1>
          <p className="text-muted" style={{ fontSize: "0.92rem" }}>
            {data ? t("rep.subtitulo", { n: data.total }) : t("comun.cargando")}
          </p>
        </div>

        {/* Reporte general del campeonato */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-end" }}>
          <span className="microetiqueta">
            {t("rep.general")}
          </span>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              className="btn btn-sm"
              onClick={() => handleExportGeneral("excel")}
              disabled={exporting !== null || loading}
              style={{
                background: "rgba(0, 168, 107, 0.12)",
                borderColor: "rgba(0, 168, 107, 0.35)",
                color: "#00D472",
              }}
            >
              {exporting === "general-excel" ? t("rep.generando") : splitZip ? t("rep.excelZip") : t("rep.excelCompleto")}
            </button>
            <button
              className="btn btn-sm"
              onClick={() => handleExportGeneral("pdf")}
              disabled={exporting !== null || loading}
              style={{
                background: "rgba(255, 68, 68, 0.10)",
                borderColor: "rgba(255, 68, 68, 0.30)",
                color: "#FF6666",
              }}
            >
              {exporting === "general-pdf" ? t("rep.generando") : splitZip ? t("rep.pdfZip") : t("rep.pdfCompleto")}
            </button>
          </div>
          <label style={{
            display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
            fontSize: "0.85rem", color: splitZip ? "var(--gold)" : "var(--text-muted)",
            fontWeight: 700, userSelect: "none",
          }}>
            <input
              type="checkbox"
              checked={splitZip}
              onChange={(e) => setSplitZip(e.target.checked)}
              style={{ accentColor: "var(--gold)", width: 16, height: 16 }}
            />
            {t("rep.dividir")}
          </label>

          {/* Publicar en la web: exporta un .json para importarlo en el sitio online */}
          <span className="microetiqueta" style={{ marginTop: 6 }}>
            Publicar en línea
          </span>
          <button
            className="btn btn-sm"
            onClick={handleExportarResultados}
            disabled={exporting !== null || loading}
            title="Descarga un archivo .json con los resultados para importarlo en el sitio web (software de la red) y publicarlos."
            style={{
              background: "var(--gold-bg)",
              borderColor: "var(--gold-border)",
              color: "var(--gold)",
            }}
          >
            {exporting === "resultados-json" ? t("rep.generando") : "⤓ Exportar resultados (.json)"}
          </button>
        </div>
      </div>

      {exportError && (
        <div className="reportes-error" role="alert">
          {exportError}
        </div>
      )}

      {/* Resumen: total + cada categoría del campeonato */}
      {data && (
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <div className="card" style={{
            padding: "10px 18px", display: "flex", flexDirection: "column",
            alignItems: "center", flex: "0 1 140px",
          }}>
            <span style={{ fontFamily: "var(--font-display)", fontSize: "1.8rem", lineHeight: 1, color: "var(--gold)" }}>
              {data.total}
            </span>
            <span className="microetiqueta" style={{ marginTop: 4 }}>
              {t("rep.registros")}
            </span>
          </div>
          {(data.categorias || []).map((cat) => (
            <button
              key={cat.nombre}
              type="button"
              className="card"
              onClick={() => setFilters(f => ({
                ...f,
                categoria: f.categoria.toLowerCase() === cat.nombre.toLowerCase() ? "" : cat.nombre,
                page: 1,
              }))}
              title={t("rep.filtrarCat", {
                nombre: cat.nombre,
                tipo: cat.puntuacion === "individual" ? t("rep.puntIndividualCorta") : t("rep.puntCombateCorta"),
              })}
              style={{
                padding: "10px 18px", display: "flex", flexDirection: "column",
                alignItems: "center", flex: "0 1 auto", minWidth: 120,
                cursor: "pointer", font: "inherit", color: "inherit",
                borderColor: filters.categoria.toLowerCase() === cat.nombre.toLowerCase()
                  ? "var(--gold)" : undefined,
                background: filters.categoria.toLowerCase() === cat.nombre.toLowerCase()
                  ? "rgba(240,184,0,0.06)" : undefined,
              }}
            >
              <span style={{
                fontFamily: "var(--font-display)", fontSize: "1.8rem", lineHeight: 1,
                color: cat.puntuacion === "individual" ? "var(--chung-light)" : "var(--hong-light)",
              }}>
                {cat.cantidad}
              </span>
              <span className="microetiqueta" style={{
                marginTop: 4,
                maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}>
                {cat.nombre}
              </span>
            </button>
          ))}
          {seleccion.size > 0 && (
            <div className="card" style={{
              padding: "10px 18px", display: "flex", flexDirection: "column",
              alignItems: "center", flex: "0 1 140px", borderColor: "var(--green-border)",
            }}>
              <span style={{ fontFamily: "var(--font-display)", fontSize: "1.8rem", lineHeight: 1, color: "var(--green)" }}>
                {seleccion.size}
              </span>
              <span className="microetiqueta" style={{ marginTop: 4 }}>
                {t("rep.seleccionados")}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="card" style={{ padding: "16px 20px" }}>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: "1 1 150px" }}>
            <label className="login-label" style={{ fontSize: "0.8rem" }}>{t("rep.tatami")}</label>
            <select
              className="input"
              value={filters.tatami_id}
              onChange={(e) => setFilters(f => ({ ...f, tatami_id: e.target.value, page: 1 }))}
              style={{ padding: "8px 12px", minHeight: 36 }}
            >
              <option value="">{t("rep.todosTatamis")}</option>
              {tatamis.map((tt) => (
                <option key={tt.id} value={String(tt.id)}>{t("rep.tatami")} {tt.numero}</option>
              ))}
            </select>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: "1 1 170px" }}>
            <label className="login-label" style={{ fontSize: "0.8rem" }}>{t("rep.puntuacion")}</label>
            <select
              className="input"
              value={filters.tipo}
              onChange={(e) => setFilters(f => ({ ...f, tipo: e.target.value, page: 1 }))}
              style={{ padding: "8px 12px", minHeight: 36 }}
            >
              <option value="">{t("rep.todas")}</option>
              <option value="combate">{t("rep.puntCombate")}</option>
              <option value="figuras">{t("rep.puntIndividual")}</option>
            </select>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: "1 1 170px" }}>
            <label className="login-label" style={{ fontSize: "0.8rem" }}>{t("rep.categoria")}</label>
            <select
              className="input"
              value={filters.categoria}
              onChange={(e) => setFilters(f => ({ ...f, categoria: e.target.value, page: 1 }))}
              style={{ padding: "8px 12px", minHeight: 36 }}
            >
              <option value="">{t("rep.todasCategorias")}</option>
              {(data?.categorias || []).map((cat) => (
                <option key={cat.nombre} value={cat.nombre}>{cat.nombre}</option>
              ))}
            </select>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: "1 1 150px" }}>
            <label className="login-label" style={{ fontSize: "0.8rem" }}>{t("rep.desde")}</label>
            <CampoFecha
              valor={filters.desde}
              ariaLabel={t("rep.desde")}
              onChange={(v) => setFilters(f => ({ ...f, desde: v, page: 1 }))}
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: "1 1 150px" }}>
            <label className="login-label" style={{ fontSize: "0.8rem" }}>{t("rep.hasta")}</label>
            <CampoFecha
              valor={filters.hasta}
              ariaLabel={t("rep.hasta")}
              min={filters.desde || undefined}
              onChange={(v) => setFilters(f => ({ ...f, hasta: v, page: 1 }))}
            />
          </div>
          <button
            className="btn btn-sm"
            onClick={() => setFilters({ tatami_id: "", tipo: "", categoria: "", desde: "", hasta: "", page: 1 })}
            style={{ alignSelf: "flex-end" }}
          >
            {t("rep.limpiar")}
          </button>
        </div>
      </div>

      {/* Barra de selección */}
      {seleccion.size > 0 && (
        <div className="animate-fade" style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          flexWrap: "wrap", gap: 10, padding: "10px 16px",
          background: "rgba(0, 212, 114, 0.08)",
          border: "1px solid var(--green-border)", borderRadius: "var(--radius)",
        }}>
          <span style={{ fontWeight: 700, fontSize: "0.92rem", color: "var(--green)" }}>
            {t("rep.nSeleccionados", { n: seleccion.size })}
          </span>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-sm" disabled={exporting !== null}
              onClick={() => handleExportSeleccion("excel")}
              style={{ background: "rgba(0,168,107,0.12)", borderColor: "rgba(0,168,107,0.35)", color: "#00D472" }}>
              {exporting === "seleccion-excel" ? t("rep.generando") : t("rep.descSelExcel")}
            </button>
            <button className="btn btn-sm" disabled={exporting !== null}
              onClick={() => handleExportSeleccion("pdf")}
              style={{ background: "rgba(255,68,68,0.10)", borderColor: "rgba(255,68,68,0.30)", color: "#FF6666" }}>
              {exporting === "seleccion-pdf" ? t("rep.generando") : t("rep.descSelPdf")}
            </button>
            <button className="btn btn-outline btn-sm" onClick={() => setSeleccion(new Set())}>
              {t("rep.limpiarSel")}
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {loading ? (
          <Cargando mensaje={t("rep.cargandoRegistros")} encajado />
        ) : !data || data.combates.length === 0 ? (
          <div style={{ padding: 48, textAlign: "center", color: "var(--text-dim)" }}>
            <p style={{ fontSize: "2rem", marginBottom: 8 }}>📋</p>
            <p>{t("rep.sinRegistros")}</p>
            <p style={{ fontSize: "0.9rem", marginTop: 6 }}>
              {t("rep.sinRegistrosNota")}
            </p>
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table" style={{ minWidth: 960 }}>
              <thead>
                <tr>
                  <th style={{ width: 36 }}>
                    <input
                      type="checkbox"
                      checked={todosVisiblesMarcados}
                      onChange={toggleSeleccionTodos}
                      title={t("rep.selTodos")}
                      style={{ accentColor: "var(--gold)", width: 16, height: 16, cursor: "pointer" }}
                    />
                  </th>
                  <th>#</th>
                  <th>{t("rep.puntuacion")}</th>
                  <th>{t("rep.tatami")}</th>
                  <th>{t("rep.categoria")}</th>
                  <th>{t("rep.marcador")}</th>
                  <th>{t("rep.ganador")}</th>
                  <th>{t("rep.jueces")}</th>
                  <th>{t("rep.rondas")}</th>
                  <th>{t("rep.fecha")}</th>
                </tr>
              </thead>
              <tbody>
                {data.combates.map((c) => (
                  <Fragment key={c.id}>
                  <tr style={{
                    background: seleccion.has(c.id) ? "rgba(240,184,0,0.05)" : undefined,
                  }}>
                    <td>
                      <input
                        type="checkbox"
                        checked={seleccion.has(c.id)}
                        onChange={() => toggleSeleccion(c.id)}
                        style={{ accentColor: "var(--gold)", width: 16, height: 16, cursor: "pointer" }}
                      />
                    </td>
                    <td className="text-muted font-mono" style={{ fontSize: "0.875rem" }}>{c.id}</td>
                    <td>
                      <span className={`badge ${c.tipo === "figuras" ? "badge-chung" : "badge-hong"}`}>
                        {c.tipo === "figuras" ? t("rep.individual") : t("tat.combate")}
                      </span>
                    </td>
                    <td className="text-center">
                      {c.tatami_numero ? `T${c.tatami_numero}` : "—"}
                    </td>
                    <td style={{ fontWeight: 700 }}>
                      {c.llave ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
                          <span>{c.llave.nombre}</span>
                          <span className="badge badge-gold">
                            {t("rep.eliminacion", { ronda: c.llave.ronda_nombre })}
                          </span>
                        </div>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <span>{c.nombre_categoria || (c.tipo === "figuras" ? t("tat.figuras") : t("tat.combate"))}</span>
                          {c.descripcion && (
                            <span style={{ fontWeight: 500, fontSize: "0.82rem", color: "var(--text-muted)" }}>
                              {c.descripcion}
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="text-center font-mono" style={{ fontSize: "1.05rem" }}>
                      {c.tipo === "figuras" ? (
                        <span style={{ color: "var(--gold)" }}>
                          {c.marcador_hong.toFixed(2)}
                          <span style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginLeft: 6 }}>
                            {t("rep.nComp", { n: c.ranking?.length || 0 })}
                          </span>
                        </span>
                      ) : (
                        <>
                          <span style={{ color: c.ganador === "hong" ? "var(--hong-light)" : "var(--text-muted)" }}>
                            {c.marcador_hong.toFixed(1)}
                          </span>
                          {" — "}
                          <span style={{ color: c.ganador === "chung" ? "var(--chung-light)" : "var(--text-muted)" }}>
                            {c.marcador_chung.toFixed(1)}
                          </span>
                        </>
                      )}
                    </td>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
                        <span className={`badge ${ganadorColor(c)}`}>
                          {c.tipo === "figuras" ? `🥇 ${ganadorNombre(c)}` : ganadorNombre(c)}
                        </span>
                        {c.tipo !== "figuras" && c.ganador !== "empate" && (
                          <span className="microetiqueta" style={{
                            color: c.ganador === "hong" ? "var(--hong-light)" : "var(--chung-light)",
                          }}>
                            {c.ganador === "hong" ? t("rep.rojo") : t("rep.azul")}
                          </span>
                        )}
                        {c.tipo === "figuras" && (c.ranking?.length || 0) > 0 && (
                          <button
                            type="button"
                            className="btn btn-outline btn-sm"
                            onClick={() => togglePodio(c.id)}
                            style={{ padding: "2px 8px", minHeight: 26, fontSize: "0.8rem" }}
                          >
                            {podioAbierto.has(c.id) ? t("rep.ocultarPodio") : t("rep.verPodio", { n: c.ranking?.length || 0 })}
                          </button>
                        )}
                        {c.tipo !== "figuras" && (c.podio_llave?.length || 0) > 0 && (
                          <button
                            type="button"
                            className="btn btn-outline btn-sm"
                            onClick={() => togglePodio(c.id)}
                            style={{ padding: "2px 8px", minHeight: 26, fontSize: "0.8rem" }}
                          >
                            {podioAbierto.has(c.id) ? t("rep.ocultarPodio") : t("rep.verPodioLlave")}
                          </button>
                        )}
                      </div>
                    </td>
                    <td style={{ minWidth: 220 }}>
                      {c.jueces && c.jueces.length > 0 ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          {c.jueces.map((j) => (
                            <span key={`${c.id}-${j.rol_tatami}`} style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>
                              <strong style={{ color: "var(--text)" }}>{j.asignacion}:</strong> {j.nombre} · {j.email}
                              {j.origen !== "asignacion" ? " · Directo" : ""}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="text-muted" style={{ fontSize: "0.875rem", minWidth: 150 }}>
                      {c.tipo === "figuras" ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
                          <span className={`badge ${c.figuras_completas ? "badge-green" : "badge-gray"}`}>
                            {c.figuras_completas ? t("rep.completo") : t("rep.incompleto")}
                          </span>
                          {(c.figuras_desempates?.length || 0) > 0 && (
                            <span
                              className="badge"
                              title={c.figuras_desempates?.map((d) => d.nombres.join(" y ")).join("; ")}
                              style={{
                                background: "rgba(255,140,0,0.12)",
                                border: "1px solid rgba(255,140,0,0.4)",
                                color: "var(--orange)",
                              }}
                            >
                              {t("rep.desempateReev")}
                            </span>
                          )}
                        </div>
                      ) : (
                        c.rondas_resumen && c.rondas_resumen !== "-"
                          ? c.rondas_resumen
                          : (RONDAS_CLAVE[c.ronda_final] ? t(RONDAS_CLAVE[c.ronda_final]) : (c.ronda_final || "—"))
                      )}
                    </td>
                    <td className="text-muted font-mono" style={{ fontSize: "0.85rem" }}>
                      {c.created_at
                        ? new Date(c.created_at).toLocaleString("es-CO", {
                            day: "2-digit", month: "2-digit",
                            hour: "2-digit", minute: "2-digit",
                          })
                        : "—"}
                    </td>
                  </tr>
                  {podioAbierto.has(c.id) && (c.tipo === "figuras" || (c.podio_llave?.length || 0) > 0) && (
                    <tr className="animate-fade">
                      <td colSpan={10} style={{ background: "rgba(255,255,255,0.02)", padding: "10px 16px" }}>
                        {c.tipo === "figuras"
                          ? <PodioFiguras ranking={c.ranking || []} />
                          : <PodioLlave podio={c.podio_llave || []} titulo={t("rep.podioLlave")} />}
                      </td>
                    </tr>
                  )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, flexWrap: "wrap" }}>
          {Array.from({ length: data.pages }, (_, i) => i + 1).map((p) => (
            <button
              key={p}
              className="btn btn-sm"
              onClick={() => setFilters(f => ({ ...f, page: p }))}
              style={{
                background: p === filters.page ? "var(--gold-bg)" : undefined,
                borderColor: p === filters.page ? "var(--gold-border)" : undefined,
                color: p === filters.page ? "var(--gold)" : undefined,
              }}
            >{p}</button>
          ))}
        </div>
      )}

      <style>{`
        .reportes-page {
          max-width: 1200px;
          margin: 0 auto;
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .reportes-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          flex-wrap: wrap;
          gap: 12px;
        }
        .reportes-error {
          padding: 12px 14px;
          border: 1px solid rgba(255, 68, 68, 0.35);
          background: rgba(255, 68, 68, 0.10);
          color: #ff9a9a;
          border-radius: var(--radius);
          font-size: 0.92rem;
          font-weight: 700;
        }
        /* Etiqueta de campo, en minusculas como en Membresias y como en la
           pantalla de entrar. Nacio como copia de la «.login-label» que vivia
           en app/login/page.tsx; esa pantalla se rehizo con la tarjeta del
           ecosistema y su clase se fue con ella, asi que ESTA YA NO ES UNA
           COPIA DE NADA: es la unica, y por eso se queda escrita aqui. Mismos
           valores que «.eco-login-etiqueta» del archivo compartido. El nombre
           se conserva porque lo escriben cinco sitios de este archivo. */
        .login-label {
          font-size: 0.8rem;
          font-weight: 600;
          color: var(--text-muted);
        }
        @media (max-width: 600px) {
          .reportes-page { padding: 14px; }
          .reportes-header { flex-direction: column; }
          .reportes-header > div:last-child { align-items: flex-start; }
        }
      `}</style>
    </div>
  );
}

// Podio completo de una categoría de figuras (no solo el ganador).
function PodioFiguras({ ranking }: { ranking: RankingItem[] }) {
  const { t } = useI18n();
  if (ranking.length === 0) return null;
  const medalla = (puesto?: number) =>
    puesto === 1 ? "🥇" : puesto === 2 ? "🥈" : puesto === 3 ? "🥉" : `${puesto ?? "-"}°`;
  return (
    <div>
      <div className="microetiqueta" style={{ marginBottom: 8 }}>
        {t("podio.titulo")}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {ranking.map((r, i) => (
          <div key={r.id ?? `${r.nombre}-${i}`} style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "6px 12px", borderRadius: "var(--radius-sm)",
            background: r.puesto === 1 ? "var(--gold-bg)" : "var(--bg-elevated)",
            border: `1px solid ${r.puesto === 1 ? "var(--gold-border)" : "var(--border)"}`,
          }}>
            <span style={{ fontSize: "1.1rem", minWidth: 32, textAlign: "center" }}>
              {medalla(r.puesto)}
            </span>
            <span style={{ flex: 1, fontWeight: 700, overflowWrap: "anywhere" }}>
              {r.nombre}
              {r.club && <span style={{ color: "var(--text-muted)", fontWeight: 500, marginLeft: 8, fontSize: "0.875rem" }}>{r.club}</span>}
              {r.especial && <span className="badge badge-chung" style={{ marginLeft: 8 }}>{t("rep.especial")}</span>}
              {r.empate && <span className="badge badge-gray" style={{ marginLeft: 8 }}>{t("rep.empate")}</span>}
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontWeight: 800, color: "var(--gold)" }}>
              {Number(r.total ?? 0).toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
