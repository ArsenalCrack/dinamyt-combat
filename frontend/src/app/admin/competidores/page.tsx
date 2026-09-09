"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  createCompetidorAPI,
  deleteCompetidorAPI,
  exportarCompetidoresAPI,
  listClubesAPI,
  listCompetidoresAPI,
  updateCompetidorAPI,
  type CompetidorData,
} from "@/lib/api";
import CompetidorFormFields, {
  COMPETIDOR_FORM_VACIO,
  competidorToForm,
  edadDesde,
  formToPayload,
  type CompetidorFormState,
} from "@/components/CompetidorFormFields";
import ImportarExcelPanel from "@/components/ImportarExcelPanel";
import ImportarPaquetePanel from "@/components/ImportarPaquetePanel";
import { useConfirmDialog } from "@/components/ConfirmDialog";
import { useI18n } from "@/lib/i18n";
import { aviso } from "@/lib/toast";

export default function CompetidoresPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [competidores, setCompetidores] = useState<CompetidorData[]>([]);
  const [clubes, setClubes] = useState<string[]>([]);
  const [busqueda, setBusqueda] = useState("");
  const [mostrarInactivos, setMostrarInactivos] = useState(false);
  const [cargando, setCargando] = useState(true);

  const [formAbierto, setFormAbierto] = useState(false);
  const [importAbierto, setImportAbierto] = useState(false);
  // Traspaso entre instalaciones (paquete .json), aparte del Excel
  const [paqueteAbierto, setPaqueteAbierto] = useState(false);
  const [exportando, setExportando] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [form, setForm] = useState<CompetidorFormState>(COMPETIDOR_FORM_VACIO);
  const [guardando, setGuardando] = useState(false);

  const { pedirConfirmacion, dialogo } = useConfirmDialog();

  const cargar = useCallback(async () => {
    try {
      const data = await listCompetidoresAPI("", mostrarInactivos);
      setCompetidores(data);
    } catch { /* */ } finally {
      setCargando(false);
    }
  }, [mostrarInactivos]);

  useEffect(() => {
    const saved = localStorage.getItem("dinamyt_user");
    if (!saved || JSON.parse(saved).rol !== "admin") {
      router.replace("/login");
      return;
    }
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      void cargar();
      listClubesAPI().then((c) => { if (!cancelled) setClubes(c); }).catch(() => {});
    });
    return () => { cancelled = true; };
  }, [cargar, router]);

  /** Avisa del resultado de una acción con la nube flotante (ver lib/toast). */
  function flash(texto: string, tipo: "ok" | "error" = "ok") {
    aviso(texto, tipo);
  }

  function abrirCrear() {
    setEditandoId(null);
    setForm(COMPETIDOR_FORM_VACIO);
    setFormAbierto(true);
    setImportAbierto(false);
  }

  function abrirEditar(c: CompetidorData) {
    setEditandoId(c.id);
    setForm(competidorToForm(c));
    setFormAbierto(true);
    setImportAbierto(false);
  }

  async function handleGuardar(e: React.FormEvent) {
    e.preventDefault();
    if (!form.nombre_completo.trim()) return;
    setGuardando(true);
    try {
      const editando = Boolean(editandoId);
      if (editandoId) {
        await updateCompetidorAPI(editandoId, formToPayload(form));
      } else {
        await createCompetidorAPI(formToPayload(form));
      }
      setFormAbierto(false);
      // El aviso va DESPUÉS de recargar: así sale cuando la lista ya enseña el
      // cambio. Antes se anunciaba "registrado" mientras la tabla seguía sin
      // él, y a quien mirara la lista le parecía que se había perdido.
      await cargar();
      flash(editando ? t("comp.actualizado") : t("comp.registrado"));
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("comp.errorGuardar"), "error");
    } finally {
      setGuardando(false);
    }
  }

  async function handleToggleActivo(c: CompetidorData) {
    try {
      await updateCompetidorAPI(c.id, { nombre_completo: c.nombre_completo, activo: !c.activo });
      await cargar();
      flash(c.activo ? t("comp.desactivadoMsg", { nombre: c.nombre_completo }) : t("comp.reactivadoMsg", { nombre: c.nombre_completo }));
    } catch { flash(t("comp.errorEstado"), "error"); }
  }

  function handleEliminar(c: CompetidorData) {
    pedirConfirmacion({
      titulo: t("comp.eliminar.titulo"),
      mensaje: t("comp.eliminar.mensaje", { nombre: c.nombre_completo }),
      tipo: "peligro",
      confirmLabel: t("comun.eliminar"),
      onConfirm: async () => {
        try {
          await deleteCompetidorAPI(c.id);
          await cargar();
          flash(t("comp.eliminado"));
        } catch { flash(t("comp.errorEliminar"), "error"); }
      },
    });
  }

  const termino = busqueda.trim().toLowerCase();
  const visibles = competidores.filter((c) => {
    if (!termino) return true;
    return `${c.nombre_completo} ${c.documento || ""} ${c.club || ""}`
      .toLowerCase()
      .includes(termino);
  });

  return (
    <div className="competidores-page">
      <div style={{ marginBottom: 18 }}>
        <button className="btn btn-outline btn-sm" onClick={() => router.push("/admin")}
          style={{ marginBottom: 8 }}>
          {t("comp.volverPanel")}
        </button>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10, flexWrap: "wrap" }}>
          <div>
            <h1 className="display" style={{ fontSize: "1.5rem" }}>{t("comp.titulo")}</h1>
            <p className="text-muted" style={{ fontSize: "0.92rem" }}>
              {t("comp.desc")}
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-sm" onClick={() => { setImportAbierto(!importAbierto); setFormAbierto(false); }}>
              {t("comp.importarExcel")}
            </button>
            {/* Traspaso entre instalaciones: JSON con todos los campos, a
                diferencia del Excel, que es para capturar listas a mano. */}
            <button
              className="btn btn-sm"
              disabled={exportando}
              onClick={async () => {
                setExportando(true);
                try {
                  await exportarCompetidoresAPI();
                  flash(t("sync.exportado"));
                } catch { flash(t("sync.errorExportar"), "error"); }
                finally { setExportando(false); }
              }}
            >
              {exportando ? t("sync.exportando") : t("sync.exportarCompetidores")}
            </button>
            <button
              className={`btn btn-sm ${paqueteAbierto ? "btn-primary" : ""}`}
              onClick={() => { setPaqueteAbierto(!paqueteAbierto); setFormAbierto(false); }}
            >
              {t("sync.importarCompetidores")}
            </button>
            <button className="btn btn-primary btn-sm" onClick={abrirCrear}>
              {t("comp.nuevo")}
            </button>
          </div>
        </div>
      </div>

      {dialogo}

      {importAbierto && (
        <div style={{ marginBottom: 14 }}>
          <ImportarExcelPanel onImportado={cargar} onMensaje={flash} />
        </div>
      )}

      {paqueteAbierto && (
        <div style={{ marginBottom: 14 }}>
          <ImportarPaquetePanel
            onImportado={async (informe) => {
              setPaqueteAbierto(false);
              await cargar();
              flash(informe.message);
            }}
          />
        </div>
      )}

      {formAbierto && (
        <form onSubmit={handleGuardar} className="card animate-slide"
          style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 14 }}>
          <div className="card-title" style={{ marginBottom: 0 }}>
            {editandoId ? t("comp.editarTitulo") : t("comp.nuevoTitulo")}
          </div>
          <CompetidorFormFields value={form} onChange={setForm} clubes={clubes} />
          <p style={{ color: "var(--text-dim)", fontSize: "0.84rem", margin: 0 }}>
            {t("comp.notaDatos")}
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn btn-primary" disabled={guardando || !form.nombre_completo.trim()}>
              {guardando ? t("comp.guardando") : editandoId ? t("comun.guardarCambios") : t("comp.registrar")}
            </button>
            <button type="button" className="btn" onClick={() => setFormAbierto(false)}>{t("comun.cancelar")}</button>
          </div>
        </form>
      )}

      {/* Filtros */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <input
          className="input"
          placeholder={t("comp.buscar")}
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          style={{ flex: "1 1 240px", maxWidth: 380 }}
        />
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.88rem", color: "var(--text-muted)", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={mostrarInactivos}
            onChange={(e) => setMostrarInactivos(e.target.checked)}
          />
          {t("comp.verInactivos")}
        </label>
        <span style={{ fontSize: "0.875rem", color: "var(--text-dim)", marginLeft: "auto" }}>
          {t("comp.deTotal", { n: visibles.length, total: competidores.length })}
        </span>
      </div>

      {/* Lista */}
      {cargando ? (
        <div className="card" style={{ textAlign: "center", padding: 30, color: "var(--text-dim)" }}>{t("comun.cargando")}</div>
      ) : visibles.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 30, color: "var(--text-dim)" }}>
          {competidores.length === 0
            ? t("comp.vacio")
            : t("comp.sinCoincidencias")}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {visibles.map((c) => {
            const edad = edadDesde(c.fecha_nacimiento);
            return (
              <div key={c.id} className="card comp-row" style={{ padding: "12px 14px", opacity: c.activo ? 1 : 0.55 }}>
                <div style={{ minWidth: 0, flex: "1 1 240px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 800, overflowWrap: "anywhere" }}>{c.nombre_completo}</span>
                    {!c.activo && <span className="badge badge-gray">{t("comun.inactivo")}</span>}
                    {c.grupo_cinturon && (
                      <span className="badge badge-chung">{c.grupo_cinturon}</span>
                    )}
                    {c.categoria_especial && (
                      <span className="badge badge-gold" title={t("comp.especialTitle")}>
                        {t("comp.especialBadge")}
                      </span>
                    )}
                    {(c.num_inscripciones || 0) > 0 && (
                      <span className="badge badge-gray">{c.num_inscripciones} {t("comp.campeonatos")}</span>
                    )}
                  </div>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: 4, display: "flex", gap: 12, flexWrap: "wrap" }}>
                    {c.documento && <span>{t("comp.doc")} {c.documento}</span>}
                    {edad != null && <span>{edad} {t("comp.anios")}</span>}
                    {c.genero && <span>{c.genero === "MASCULINO" ? t("comp.masc") : t("comp.fem")}</span>}
                    {c.peso != null && <span>{c.peso} kg</span>}
                    {c.cinturon && <span>{t("comp.cinturonLabel")} {c.cinturon}</span>}
                    {c.club && <span>{c.club}</span>}
                  </div>
                  {/* Fechas: registro y última actualización de datos */}
                  <div style={{ color: "var(--text-dim)", fontSize: "0.78rem", marginTop: 3, display: "flex", gap: 12, flexWrap: "wrap" }}>
                    {c.created_at && (
                      <span>{t("comp.creadoEl")} {new Date(c.created_at).toLocaleDateString()}</span>
                    )}
                    {c.updated_at && c.updated_at !== c.created_at && (
                      <span>{t("comp.actualizadoEl")} {new Date(c.updated_at).toLocaleDateString()}</span>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, flexShrink: 0, flexWrap: "wrap" }}>
                  <button className="btn btn-sm" onClick={() => abrirEditar(c)}>{t("comun.editar")}</button>
                  <button className="btn btn-sm" onClick={() => handleToggleActivo(c)}>
                    {c.activo ? t("comun.desactivar") : t("comun.reactivar")}
                  </button>
                  <button className="btn btn-danger btn-sm" onClick={() => handleEliminar(c)}>{t("comun.eliminar")}</button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <style>{`
        .competidores-page {
          max-width: 1100px; margin: 0 auto; padding: 24px clamp(16px, 4vw, 40px);
        }
        .comp-row {
          display: flex; justify-content: space-between; align-items: center;
          gap: 10px; flex-wrap: wrap;
        }
        @media (max-width: 560px) {
          .competidores-page { padding: 14px; }
          .comp-row > div:last-child { margin-left: auto; }
        }
      `}</style>
    </div>
  );
}
