"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  getCampeonatoAPI,
  listUsersAPI,
  getTatamiAPI,
  ajustarTatamisAPI,
  asignarJuezAPI,
  desasignarJuezAPI,
  updateCampeonatoAPI,
  deleteCampeonatoAPI,
  accesoQrAPI,
  exportarCampeonatoAPI,
  origenParaQr,
  MAX_TATAMIS,
  MIN_TATAMIS,
  type EstadoCampeonato,
  type OpcionesExportCampeonato,
  type UserData,
} from "@/lib/api";
import CampoFecha from "@/components/CampoFecha";
import { useConfirmDialog } from "@/components/ConfirmDialog";
import PaisCiudadSelect from "@/components/PaisCiudadSelect";
import { useI18n, type ClaveTexto } from "@/lib/i18n";
import { aviso } from "@/lib/toast";
import { enMayusculas } from "@/lib/texto";
import QRCode from "qrcode";
import { Cargando } from '@/components/Cargando';

interface Tatami {
  id: number;
  numero: number;
  activo: boolean;
  num_asignaciones: number;
  asignaciones?: Asignacion[];
}

interface Asignacion {
  id: number;
  usuario_id: number;
  tatami_id: number;
  rol_tatami: string;
  nombre_display: string;
  asignado_at?: string;
  asignado_por?: { id: number; nombre: string; email: string } | null;
  usuario?: UserData;
}

interface Campeonato {
  id: number;
  nombre: string;
  descripcion: string;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  lugar: string | null;
  ciudad: string | null;
  pais: string | null;
  estado: EstadoCampeonato;
  activo: boolean;
  num_pendientes?: number;
  tatamis: Tatami[];
}

// Los textos por rol viven en lib/i18n (claves rol.*)
const ROLES_TATAMI: { value: string; labelKey: ClaveTexto }[] = [
  { value: "arbitro", labelKey: "rol.arbitro" },
  { value: "j1", labelKey: "rol.j1" },
  { value: "j2", labelKey: "rol.j2" },
  { value: "j3", labelKey: "rol.j3" },
  { value: "j4", labelKey: "rol.j4" },
];

export default function CampeonatoDetailPage() {
  const router = useRouter();
  const { t } = useI18n();
  const params = useParams();
  const campId = Number(params.id);

  const [camp, setCamp] = useState<Campeonato | null>(null);
  const [users, setUsers] = useState<UserData[]>([]);
  const [selectedTatami, setSelectedTatami] = useState<Tatami | null>(null);
  const [assigning, setAssigning] = useState(false);
  // rol_tatami vacío = "aún sin elegir": el render cae al primer rol libre
  const [assignData, setAssignData] = useState({ usuario_id: 0, rol_tatami: "" });
  const [judgeSearch, setJudgeSearch] = useState("");
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState({
    nombre: "", descripcion: "", fecha_inicio: "", fecha_fin: "",
    lugar: "", ciudad: "", pais: "",
  });
  // Nº de tatamis (editable solo en preparación): se escribe como texto para
  // permitir borrar el campo mientras se teclea, y se valida al aplicar.
  const [numTatamis, setNumTatamis] = useState("");
  const [ajustandoTatamis, setAjustandoTatamis] = useState(false);
  // Exportar el campeonato para llevarlo a la otra instalación
  const [panelExportar, setPanelExportar] = useState(false);
  const [exportando, setExportando] = useState(false);
  const [incluir, setIncluir] = useState<Required<OpcionesExportCampeonato>>({
    usuarios: true, competidores: true, llaves: true,
  });
  // QR de acceso directo de un juez: {nombre, rol, url, dataUrl}
  const [qrInfo, setQrInfo] = useState<{
    nombre: string; rol: string; url: string; dataUrl: string;
  } | null>(null);
  const { pedirConfirmacion, dialogo } = useConfirmDialog();

  async function handleQr(tatamiId: number, usuarioId: number) {
    try {
      const data = await accesoQrAPI(tatamiId, usuarioId);
      // El token viaja en el fragmento (#): no queda en logs del servidor.
      // origenParaQr evita QRs con "localhost" (ilegibles desde un teléfono):
      // usa la IP de red del servidor o NEXT_PUBLIC_QR_ORIGIN si está definida.
      const url = `${origenParaQr(data.ip_local)}/acceso#token=${encodeURIComponent(data.token)}`
        + `&tatami=${data.tatami_id}&rol=${encodeURIComponent(data.rol_tatami)}`;
      const dataUrl = await QRCode.toDataURL(url, { width: 320, margin: 2 });
      setQrInfo({ nombre: data.nombre, rol: data.rol_tatami, url, dataUrl });
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("camp.qr.error"), "error");
    }
  }

  const loadData = useCallback(async () => {
    try {
      const [c, u] = await Promise.all([
        getCampeonatoAPI(campId),
        listUsersAPI(),
      ]);
      setCamp(c);
      setNumTatamis(String(c.tatamis?.length || 0));
      // Asignables a un tatami: jueces y maestros con permiso de juez.
      setUsers(u.filter((x: UserData) => x.rol === "juez" || (x.rol === "maestro" && x.puede_juzgar)));
    } catch { router.replace("/admin"); }
  }, [campId, router]);

  useEffect(() => {
    const saved = localStorage.getItem("dinamyt_user");
    if (!saved || JSON.parse(saved).rol !== "admin") {
      router.replace("/login"); return;
    }
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadData();
    });
    return () => { cancelled = true; };
  }, [loadData, router]);

  const detailRef = useRef<HTMLDivElement | null>(null);

  async function loadTatamiDetail(tId: number) {
    try {
      const t = await getTatamiAPI(tId);
      setSelectedTatami(t);
      // En móvil (una sola columna) llevar el detalle a la vista
      if (typeof window !== "undefined" && window.innerWidth <= 820) {
        setTimeout(() => {
          detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 60);
      }
    } catch { /* */ }
  }

  async function handleAssign(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedTatami || !assignData.usuario_id || !rolSeleccionado) return;
    try {
      await asignarJuezAPI(selectedTatami.id, { ...assignData, rol_tatami: rolSeleccionado });
      setAssigning(false);
      setAssignData({ usuario_id: 0, rol_tatami: "" });
      setJudgeSearch("");
      await Promise.all([loadData(), loadTatamiDetail(selectedTatami.id)]);
      flash(t("camp.asignar.ok"), "ok");
    } catch (err) {
      const errorMsg = (err as { response?: { data?: { error?: string } } })
        .response?.data?.error;
      flash(errorMsg || t("camp.asignar.error"), "error");
    }
  }

  async function handleUnassign(tatamiId: number, userId: number) {
    try {
      await desasignarJuezAPI(tatamiId, userId);
      await Promise.all([loadData(), loadTatamiDetail(tatamiId)]);
      flash(t("camp.desasignar.ok"), "ok");
    } catch { flash(t("camp.desasignar.error"), "error"); }
  }

  /** Avisa del resultado de una acción con la nube flotante (ver lib/toast). */
  function flash(texto: string, tipo: "ok" | "error" = "ok") {
    aviso(texto, tipo);
  }

  async function handleToggleActivo() {
    if (!camp) return;
    try {
      await updateCampeonatoAPI(camp.id, { activo: !camp.activo });
      await loadData();
      flash(camp.activo
        ? t("camp.desactivadoMsg")
        : t("camp.activadoMsg"), "ok");
    } catch { flash(t("admin.camp.errorEstado"), "error"); }
  }

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!camp || !editData.nombre.trim()) return;
    try {
      await updateCampeonatoAPI(camp.id, {
        nombre: editData.nombre.trim(),
        descripcion: editData.descripcion.trim(),
        fecha_inicio: editData.fecha_inicio || undefined,
        fecha_fin: editData.fecha_fin || undefined,
        lugar: editData.lugar.trim(),
        ciudad: editData.ciudad.trim(),
        pais: editData.pais.trim(),
      });
      setEditing(false);
      await loadData();
      flash(t("camp.actualizado"), "ok");
    } catch { flash(t("camp.errorActualizar"), "error"); }
  }

  async function handleChangeEstado(estado: EstadoCampeonato) {
    if (!camp || camp.estado === estado) return;
    try {
      await updateCampeonatoAPI(camp.id, { estado });
      await loadData();
      flash(t("camp.actualizado"), "ok");
    } catch { flash(t("camp.errorActualizar"), "error"); }
  }

  async function handleExportar() {
    if (!camp) return;
    setExportando(true);
    try {
      await exportarCampeonatoAPI(camp.id, incluir);
      setPanelExportar(false);
      flash(t("sync.exportado"), "ok");
    } catch { flash(t("sync.errorExportar"), "error"); }
    finally { setExportando(false); }
  }

  /** Aplica el nº de tatamis escrito. Al bajar pide confirmación primero. */
  async function handleAjustarTatamis() {
    if (!camp) return;
    const objetivo = Number(numTatamis);
    const actual = camp.tatamis?.length || 0;
    if (!Number.isInteger(objetivo) || objetivo < MIN_TATAMIS || objetivo > MAX_TATAMIS) {
      setNumTatamis(String(actual));
      return;
    }
    if (objetivo === actual) return;

    const aplicar = async () => {
      setAjustandoTatamis(true);
      try {
        const res = await ajustarTatamisAPI(camp.id, objetivo);
        // El tatami abierto en el detalle puede haber desaparecido.
        if (selectedTatami && res.eliminados.includes(selectedTatami.numero)) {
          setSelectedTatami(null);
        }
        await loadData();
        flash(res.message, "ok");
      } catch (err) {
        const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
        flash(m || t("camp.tatamis.error"), "error");
        setNumTatamis(String(actual));
      } finally {
        setAjustandoTatamis(false);
      }
    };

    if (objetivo < actual) {
      pedirConfirmacion({
        titulo: t("camp.tatamis.confirmar.titulo"),
        mensaje: t("camp.tatamis.confirmar.mensaje", {
          desde: objetivo + 1, hasta: actual,
        }),
        tipo: "advertencia",
        confirmLabel: t("camp.tatamis.aplicar"),
        onConfirm: aplicar,
      });
      return;
    }
    await aplicar();
  }

  function handleDeleteCampeonato() {
    if (!camp) return;
    pedirConfirmacion({
      titulo: t("camp.eliminar.titulo"),
      mensaje: t("camp.eliminar.mensaje", { nombre: camp.nombre }),
      tipo: "peligro",
      confirmLabel: t("comun.eliminar"),
      onConfirm: async () => {
        try {
          await deleteCampeonatoAPI(camp.id);
          router.replace("/admin");
        } catch { flash(t("camp.errorEliminar"), "error"); }
      },
    });
  }

  const searchTerm = judgeSearch.trim().toLowerCase();
  const availableJudges = users.filter((u) => {
    if (!u.activo || !(u.rol === "juez" || (u.rol === "maestro" && u.puede_juzgar))) return false;
    if ((u.asignaciones?.length || 0) > 0) return false;
    if (!searchTerm) return true;
    return `${u.nombre} ${u.email}`.toLowerCase().includes(searchTerm);
  });
  const selectedJudge = users.find((u) => u.id === assignData.usuario_id);

  // Roles ya ocupados en el tatami seleccionado: no se ofrecen de nuevo en el
  // desplegable (el backend igual los rechaza con 409, esto evita el intento).
  const rolesOcupados = new Set(
    (selectedTatami?.asignaciones ?? []).map((a) => a.rol_tatami)
  );
  const rolesDisponibles = ROLES_TATAMI.filter((r) => !rolesOcupados.has(r.value));
  // Si el rol elegido se ocupó entre medias (p. ej. se recargó el detalle),
  // caer al primer rol libre para que el select nunca muestre uno ocupado.
  const rolSeleccionado =
    !assignData.rol_tatami || rolesOcupados.has(assignData.rol_tatami)
      ? (rolesDisponibles[0]?.value ?? "")
      : assignData.rol_tatami;

  if (!camp) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
      <Cargando />
    </div>
  );

  return (
    <div className="campeonato-admin-page" style={{ maxWidth: 1200, margin: "0 auto", padding: "24px clamp(20px, 4vw, 40px)" }}>
      {/* Header */}
      <div className="campeonato-admin-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12, marginBottom: 24 }}>
        <div style={{ minWidth: 0 }}>
          <button className="btn btn-outline btn-sm" onClick={() => router.push("/admin")}
            style={{ marginBottom: 8, fontSize: "0.875rem" }}>{t("comun.volver")}</button>
          <h1 style={{ fontWeight: 700, fontSize: "clamp(1.6rem, 3vw, 2.1rem)", overflowWrap: "anywhere" }}>{camp.nombre}</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.95rem" }}>
            {camp.tatamis?.length || 0} {t("comun.tatamis")} &middot;{" "}
            <span style={{ color: camp.activo ? "var(--green)" : "var(--orange)", fontWeight: 700 }}>
              {camp.activo ? t("camp.activoPublico") : t("camp.inactivoPublico")}
            </span>
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            className="btn btn-sm"
            onClick={() => router.push(`/admin/campeonato/${camp.id}/reportes`)}
            style={{
              background: "rgba(0, 212, 114, 0.10)",
              borderColor: "rgba(0, 212, 114, 0.30)",
              color: "var(--green)",
            }}
          >
            {t("camp.reportes")}
          </button>
          <button
            className="btn btn-sm"
            onClick={() => router.push(`/admin/campeonato/${camp.id}/inscripciones`)}
            style={{
              background: "rgba(0, 150, 255, 0.10)",
              borderColor: "rgba(0, 150, 255, 0.30)",
              color: "var(--chung-light, #4da3ff)",
            }}
          >
            {t("camp.inscripciones.boton")}
            {!!camp.num_pendientes && (
              <span className="badge" style={{
                marginLeft: 6, background: "var(--gold-bg)", color: "var(--gold)",
                border: "1px solid var(--gold-border)",
              }}>{camp.num_pendientes}</span>
            )}
          </button>
          <button
            className="btn btn-sm"
            onClick={() => router.push(`/admin/campeonato/${camp.id}/llaves`)}
            style={{
              background: "var(--gold-bg)",
              borderColor: "var(--gold-border)",
              color: "var(--gold)",
            }}
          >
            {t("camp.llaves")}
          </button>
          <button
            className="btn btn-sm"
            onClick={() => router.push(`/admin/campeonato/${camp.id}/generar-llaves`)}
            style={{
              background: "var(--gold-bg)",
              borderColor: "var(--gold-border)",
              color: "var(--gold)",
            }}
          >
            {t("camp.generarLlaves")}
          </button>
          <button
            className={`btn btn-sm ${panelExportar ? "btn-primary" : ""}`}
            onClick={() => setPanelExportar(!panelExportar)}
          >
            {t("sync.exportarCampeonato")}
          </button>
          <button
            className="btn btn-sm"
            onClick={() => {
              setEditData({
                nombre: camp.nombre, descripcion: camp.descripcion || "",
                fecha_inicio: camp.fecha_inicio || "", fecha_fin: camp.fecha_fin || "",
                lugar: camp.lugar || "", ciudad: camp.ciudad || "", pais: camp.pais || "",
              });
              setEditing(!editing);
            }}
          >
            {t("comun.editar")}
          </button>
          <button
            className={`btn btn-sm ${camp.activo ? "btn-danger" : "btn-primary"}`}
            onClick={handleToggleActivo}
          >
            {camp.activo ? t("comun.desactivar") : t("comun.activar")}
          </button>
          <button className="btn btn-sm btn-danger" onClick={handleDeleteCampeonato}>
            {t("comun.eliminar")}
          </button>
        </div>
      </div>

      {editing && (
        <form onSubmit={handleSaveEdit} className="card animate-slide"
          style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
          <div className="card-title">{t("camp.editar.titulo")}</div>
          {/* Nombre y sede en mayúsculas (así se guardan); la descripción no:
              ahí cabe una frase, no un dato. */}
          <input className="input" placeholder={t("admin.camp.nombre")} value={editData.nombre}
            onChange={(e) => setEditData({ ...editData, nombre: enMayusculas(e.target.value) })} required />
          <input className="input" placeholder={t("admin.camp.desc")} value={editData.descripcion}
            onChange={(e) => setEditData({ ...editData, descripcion: e.target.value })} />
          {/* <div> y no <label>: el disparador de <CampoFecha> es un botón, y
              un <label> que lo envuelva le reenvía el clic hecho sobre el
              panel, reabriéndolo. */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 700 }}>
              {t("camp.campos.fechaInicio")}
              <CampoFecha valor={editData.fecha_inicio} ariaLabel={t("camp.campos.fechaInicio")}
                onChange={(v) => setEditData({ ...editData, fecha_inicio: v })} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 700 }}>
              {t("camp.campos.fechaFin")}
              <CampoFecha valor={editData.fecha_fin} ariaLabel={t("camp.campos.fechaFin")}
                min={editData.fecha_inicio || undefined}
                onChange={(v) => setEditData({ ...editData, fecha_fin: v })} />
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
            <label className="pcs-field" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--text-muted)" }}>{t("camp.campos.lugar")}</span>
              <input className="input" placeholder={t("camp.campos.lugar")} value={editData.lugar}
                maxLength={120} onChange={(e) => setEditData({ ...editData, lugar: enMayusculas(e.target.value.slice(0, 120)) })} />
            </label>
            <PaisCiudadSelect pais={editData.pais} ciudad={editData.ciudad}
              onChange={(pais, ciudad) => setEditData({ ...editData, pais, ciudad })} />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn btn-primary">{t("comun.guardar")}</button>
            <button type="button" className="btn" onClick={() => setEditing(false)}>{t("comun.cancelar")}</button>
          </div>
        </form>
      )}

      {/* Exportar el campeonato para la otra instalación (local ↔ internet) */}
      {panelExportar && (
        <div className="card animate-slide" style={{
          marginBottom: 16, display: "flex", flexDirection: "column", gap: 10,
        }}>
          <div className="card-title" style={{ marginBottom: 0 }}>
            {t("sync.exportarCampeonato")}
          </div>
          <p className="text-muted" style={{ margin: 0, fontSize: "0.88rem" }}>
            {t("sync.exportarCampeonato.desc")}
          </p>
          <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
            <legend className="microetiqueta" style={{ marginBottom: 6 }}>
              {t("sync.incluir")}
            </legend>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {([
                ["usuarios", "sync.incluir.usuarios"],
                ["competidores", "sync.incluir.competidores"],
                ["llaves", "sync.incluir.llaves"],
              ] as const).map(([clave, labelKey]) => (
                <label key={clave} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: "0.88rem" }}>
                  <input
                    type="checkbox"
                    checked={incluir[clave]}
                    onChange={(e) => setIncluir({ ...incluir, [clave]: e.target.checked })}
                  />
                  {t(labelKey)}
                </label>
              ))}
            </div>
          </fieldset>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-primary btn-sm" disabled={exportando} onClick={handleExportar}>
              {exportando ? t("sync.exportando") : t("sync.exportar")}
            </button>
            <button className="btn btn-sm" onClick={() => setPanelExportar(false)}>
              {t("comun.cancelar")}
            </button>
          </div>
        </div>
      )}

      {/* Estado del ciclo de vida del campeonato */}
      <div className="card" style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 16 }}>
        <span style={{ fontWeight: 700, color: "var(--text-muted)", fontSize: "0.9rem" }}>
          {t("camp.campos.estado")}:
        </span>
        {(["preparacion", "en_curso", "finalizado"] as EstadoCampeonato[]).map((e) => (
          <button key={e} type="button"
            className={`btn btn-sm ${camp.estado === e ? "btn-primary" : ""}`}
            onClick={() => handleChangeEstado(e)}
            style={camp.estado === e ? undefined : { opacity: 0.75 }}
          >
            {t(`camp.estado.${e}` as ClaveTexto)}
          </button>
        ))}
        <span style={{ color: "var(--text-dim)", fontSize: "0.82rem", flexBasis: "100%" }}>
          {t("camp.estado.preparacionAyuda")}
        </span>
      </div>

      {/* Solicitudes por revisar: se moderan en el panel de inscripciones */}
      {!!camp.num_pendientes && (
        <div className="card animate-fade" style={{
          marginBottom: 16, borderColor: "var(--gold-border)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          gap: 10, flexWrap: "wrap",
        }}>
          <span style={{ fontWeight: 700, color: "var(--gold)" }}>
            {t("camp.inscripciones.aviso", { n: camp.num_pendientes })}
          </span>
          <button
            className="btn btn-sm btn-primary"
            onClick={() => router.push(`/admin/campeonato/${camp.id}/inscripciones?estado=pendiente`)}
          >
            {t("camp.inscripciones.revisar")}
          </button>
        </div>
      )}

      {dialogo}

      {/* Modal: QR de acceso directo de un juez */}
      {qrInfo && (
        <div
          onClick={() => setQrInfo(null)}
          style={{
            position: "fixed", inset: 0, zIndex: 300,
            background: "rgba(10,10,18,0.85)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
          }}
        >
          <div
            className="card animate-scale"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: 400, width: "100%", textAlign: "center", padding: 24 }}
          >
            <div className="card-title" style={{ marginBottom: 4 }}>
              {t("camp.qr.titulo", { nombre: qrInfo.nombre })}
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginBottom: 12 }}>
              {t("camp.qr.rolLabel")} <strong style={{ textTransform: "uppercase" }}>{qrInfo.rol}</strong>.{" "}
              {t("camp.qr.desc")}
            </p>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={qrInfo.dataUrl}
              alt={t("camp.qr.alt", { nombre: qrInfo.nombre })}
              style={{ width: 260, height: 260, borderRadius: 8, background: "#fff", padding: 6 }}
            />
            {/* Dirección visible: el admin confirma de un vistazo que el QR
                apunta a una dirección de red alcanzable (no localhost) */}
            <p className="font-mono" style={{
              color: "var(--text-muted)", fontSize: "0.8rem", marginTop: 8,
              overflowWrap: "anywhere",
            }}>
              {qrInfo.url.split("#")[0]}
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 14, flexWrap: "wrap" }}>
              <button
                className="btn btn-sm"
                onClick={() => {
                  navigator.clipboard?.writeText(qrInfo.url).then(
                    () => flash(t("camp.qr.copiado"), "ok"),
                    () => flash(t("camp.qr.errorCopiar"), "error"),
                  );
                }}
              >
                {t("camp.qr.copiar")}
              </button>
              <button className="btn btn-primary btn-sm" onClick={() => setQrInfo(null)}>
                {t("comun.cerrar")}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="campeonato-admin-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {/* Tatamis list */}
        <div>
          <div className="card-title">{t("camp.tatamis.titulo")}</div>

          {/* Cantidad de tatamis: editable solo mientras se prepara el evento */}
          <div className="card" style={{ padding: 12, marginBottom: 12 }}>
            {camp.estado === "preparacion" ? (
              <>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <label htmlFor="num-tatamis" style={{
                    fontSize: "0.85rem", fontWeight: 700, color: "var(--text-muted)",
                  }}>
                    {t("camp.tatamis.cantidad")}
                  </label>
                  <input
                    id="num-tatamis"
                    className="input"
                    type="number"
                    min={MIN_TATAMIS}
                    max={MAX_TATAMIS}
                    value={numTatamis}
                    disabled={ajustandoTatamis}
                    onChange={(e) => setNumTatamis(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") void handleAjustarTatamis(); }}
                    style={{ width: 90 }}
                  />
                  <button
                    className="btn btn-sm btn-primary"
                    disabled={ajustandoTatamis || Number(numTatamis) === (camp.tatamis?.length || 0)}
                    onClick={() => void handleAjustarTatamis()}
                  >
                    {t("camp.tatamis.aplicar")}
                  </button>
                </div>
                <p style={{ margin: "6px 0 0", fontSize: "0.8rem", color: "var(--text-dim)" }}>
                  {t("camp.tatamis.ayuda")}
                </p>
              </>
            ) : (
              <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-dim)" }}>
                {t("camp.tatamis.bloqueado")}
              </p>
            )}
          </div>

          <div className="tatami-list">
            {/* "tat" y no "t": no hacerle sombra a la función de traducción */}
            {camp.tatamis?.map((tat) => (
              <button
                key={tat.id}
                type="button"
                className="card tatami-card"
                style={{
                  cursor: "pointer",
                  textAlign: "left",
                  font: "inherit",
                  color: "inherit",
                  width: "100%",
                  borderColor: selectedTatami?.id === tat.id ? "var(--gold)" : undefined,
                  background: selectedTatami?.id === tat.id ? "rgba(240,184,0,0.06)" : undefined,
                }}
                onClick={() => loadTatamiDetail(tat.id)}
                aria-pressed={selectedTatami?.id === tat.id}
              >
                <div className="tatami-card-row">
                  <span style={{ fontWeight: 700, fontSize: "1.2rem" }}>{t("camp.tatami")} {tat.numero}</span>
                  <span style={{ color: "var(--text-dim)", fontSize: "0.9rem", whiteSpace: "nowrap" }}>
                    {tat.num_asignaciones} {t("comun.jueces")}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Tatami detail */}
        <div ref={detailRef} style={{ scrollMarginTop: 12 }}>
          {selectedTatami ? (
            <div className="animate-fade">
              <div className="card-title">
                {t("camp.tatami")} {selectedTatami.numero} &middot; {t("camp.asignaciones")}
              </div>

              {/* Current assignments */}
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                {selectedTatami.asignaciones?.map((a) => (
                  <div key={a.id} className="card asignacion-row" style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: 12, gap: 10, flexWrap: "wrap",
                  }}>
                    <div style={{ minWidth: 0, flex: "1 1 200px" }}>
                      <div style={{ overflowWrap: "anywhere" }}>
                        <span style={{ fontWeight: 700 }}>{a.nombre_display || a.usuario?.nombre}</span>
                        {a.usuario?.email && (
                          <span style={{ color: "var(--text-muted)", marginLeft: 8, fontSize: "0.85rem" }}>
                            {a.usuario.email}
                          </span>
                        )}
                      </div>
                      <span className="badge" style={{
                        marginTop: 4,
                        background: "var(--chung-bg)", color: "var(--chung-light)",
                        borderColor: "var(--chung-border)",
                      }}>{a.rol_tatami}</span>
                      <div style={{ color: "var(--text-dim)", fontSize: "0.8rem", marginTop: 4 }}>
                        {t("camp.asignado")} {a.asignado_at ? new Date(a.asignado_at).toLocaleDateString("es-CO") : "—"}
                        {a.asignado_por ? ` ${t("comun.por")} ${a.asignado_por.nombre}` : ""}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                      <button
                        className="btn btn-sm"
                        style={{ padding: "6px 12px", fontSize: "0.82rem" }}
                        title={t("camp.qr.tooltip")}
                        onClick={() => handleQr(selectedTatami.id, a.usuario_id)}
                      >{t("camp.qr.boton")}</button>
                      <button
                        className="btn btn-danger btn-sm"
                        style={{ padding: "6px 12px", fontSize: "0.82rem" }}
                        onClick={() => handleUnassign(selectedTatami.id, a.usuario_id)}
                      >{t("comun.quitar")}</button>
                    </div>
                  </div>
                ))}
                {(!selectedTatami.asignaciones || selectedTatami.asignaciones.length === 0) && (
                  <p style={{ color: "var(--text-dim)", fontSize: "0.9rem", textAlign: "center", padding: 20 }}>
                    {t("camp.sinJueces")}
                  </p>
                )}
              </div>

              {/* Assign form */}
              {assigning ? (
                <form onSubmit={handleAssign} className="card animate-slide" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <input
                    className="input"
                    placeholder={t("camp.asignar.buscar")}
                    value={judgeSearch}
                    onChange={(e) => {
                      setJudgeSearch(e.target.value);
                      setAssignData({ ...assignData, usuario_id: 0 });
                    }}
                  />
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 180, overflowY: "auto" }}>
                    {selectedJudge && (
                      <div style={{
                        padding: "8px 10px", border: "1px solid var(--green-border)",
                        borderRadius: "var(--radius-sm)", color: "var(--green)", fontSize: "0.88rem",
                        fontWeight: 700,
                      }}>
                        {t("camp.asignar.seleccionado", { nombre: selectedJudge.nombre, email: selectedJudge.email })}
                      </div>
                    )}
                    {availableJudges.map((u) => (
                      <button
                        key={u.id}
                        type="button"
                        className="btn"
                        onClick={() => {
                          setAssignData({ ...assignData, usuario_id: u.id });
                          setJudgeSearch(`${u.nombre} ${u.email}`);
                        }}
                        style={{ justifyContent: "flex-start", textAlign: "left", padding: "8px 10px" }}
                      >
                        <span style={{ fontWeight: 700 }}>{u.nombre}</span>
                        <span style={{ color: "var(--text-muted)", marginLeft: 8, fontSize: "0.875rem" }}>{u.email}</span>
                        {u.rol === "maestro" && (
                          <span className="badge badge-green" style={{ marginLeft: 8 }}>{t("rol.maestro")}</span>
                        )}
                      </button>
                    ))}
                    {availableJudges.length === 0 && !selectedJudge && (
                      <div style={{ color: "var(--text-dim)", fontSize: "0.88rem", padding: "8px 4px" }}>
                        {t("camp.asignar.sinResultados")}
                      </div>
                    )}
                  </div>
                  <select className="input" value={rolSeleccionado}
                    onChange={(e) => setAssignData({ ...assignData, rol_tatami: e.target.value })}>
                    {rolesDisponibles.map((r) => (
                      <option key={r.value} value={r.value}>{t(r.labelKey)}</option>
                    ))}
                  </select>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button type="submit" className="btn btn-primary" disabled={!assignData.usuario_id || !rolSeleccionado}>{t("camp.asignar.boton")}</button>
                    <button type="button" className="btn" onClick={() => {
                      setAssigning(false);
                      setAssignData({ usuario_id: 0, rol_tatami: "" });
                      setJudgeSearch("");
                    }}>{t("comun.cancelar")}</button>
                  </div>
                </form>
              ) : rolesDisponibles.length > 0 ? (
                <button className="btn btn-primary" style={{ width: "100%" }}
                  onClick={() => {
                    setAssignData({ usuario_id: 0, rol_tatami: "" });
                    setJudgeSearch("");
                    setAssigning(true);
                  }}>
                  {t("camp.asignar.abrir")}
                </button>
              ) : (
                <p style={{
                  color: "var(--text-muted)", fontSize: "0.9rem", textAlign: "center",
                  padding: "10px 0", margin: 0,
                }}>
                  {t("camp.asignar.completo")}
                </p>
              )}

              {/* Open tatami link */}
              <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
                <button className="btn btn-primary" style={{ width: "100%" }}
                  onClick={() => router.push(`/tatami/${selectedTatami.id}?rol=arbitro`)}>
                  {t("camp.abrirJC")}
                </button>
              </div>
            </div>
          ) : (
            <div className="card" style={{ textAlign: "center", padding: 40, color: "var(--text-dim)" }}>
              {t("camp.seleccionaTatami")}
            </div>
          )}
        </div>
      </div>

      <style>{`
        .campeonato-admin-grid {
          align-items: start;
        }
        .tatami-list {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
          gap: 12px;
        }
        .tatami-card {
          padding: 16px 18px;
          min-height: 64px;
        }
        .tatami-card:hover {
          border-color: var(--gold-border);
          background: var(--bg-elevated);
        }
        .tatami-card-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
        }
        @media (max-width: 820px) {
          .campeonato-admin-page {
            padding: 14px !important;
          }
          .campeonato-admin-header {
            align-items: flex-start !important;
            gap: 12px;
            flex-wrap: wrap;
          }
          .campeonato-admin-grid {
            grid-template-columns: 1fr !important;
          }
          .tatami-list {
            grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
          }
        }
        @media (max-width: 520px) {
          .campeonato-admin-grid .card {
            padding: 12px !important;
          }
          .campeonato-admin-grid .btn {
            white-space: normal;
          }
          .tatami-list {
            grid-template-columns: 1fr 1fr;
          }
          .asignacion-row > div:first-child {
            flex-basis: 100%;
          }
          .asignacion-row .btn {
            margin-left: auto;
          }
        }
        @media (max-width: 360px) {
          .tatami-list {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}
