"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  listCampeonatosAPI,
  createCampeonatoAPI,
  updateCampeonatoAPI,
  exportarUsuariosAPI,
  fijarMantenimientoAPI,
  listClubesDetalleAPI,
  listUsersAPI,
  obtenerMantenimientoAPI,
  registerUserAPI,
  updateUserAPI,
  type ClubMaestro,
  type EstadoCampeonato,
  type EstadoMantenimiento,
  type UserData,
} from "@/lib/api";
import CampoContrasena from "@/components/CampoContrasena";
import CampoFecha from "@/components/CampoFecha";
import ClubesInput from "@/components/ClubesInput";
import { useConfirmDialog } from "@/components/ConfirmDialog";
import ImportarPaquetePanel from "@/components/ImportarPaquetePanel";
import PaisCiudadSelect from "@/components/PaisCiudadSelect";
import { useI18n, type ClaveTexto } from "@/lib/i18n";
import { enMayusculas } from "@/lib/texto";
import { aviso } from "@/lib/toast";
import { LIM } from "@/lib/limites";

/**
 * Los dojangs de un maestro, con respaldo en los campos sueltos.
 *
 * Un maestro guardado antes de que la lista existiera solo trae `club` +
 * `delegacion` + `pais_delegacion`, y el backend hace la misma reconstrucción
 * (ver `clubes` en models/usuario.py). Aquí hace falta porque `users` también
 * puede venir de una sesión vieja en localStorage.
 */
function clubesDe(u: UserData): ClubMaestro[] {
  if (u.clubes?.length) {
    return u.clubes.map((c) => ({
      nombre: enMayusculas(c.nombre),
      ciudad: c.ciudad || "",
      pais: c.pais || "",
    }));
  }
  if (!u.club) return [];
  return [{
    nombre: enMayusculas(u.club),
    ciudad: u.delegacion || "",
    pais: u.pais_delegacion || "",
  }];
}

interface Campeonato {
  id: number;
  nombre: string;
  descripcion: string;
  fecha_inicio: string;
  fecha_fin: string;
  lugar?: string | null;
  ciudad?: string | null;
  pais?: string | null;
  estado?: EstadoCampeonato;
  activo: boolean;
  num_tatamis: number;
  num_pendientes?: number;
  created_at: string;
}

export default function AdminPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [user, setUser] = useState<UserData | null>(null);
  const [campeonatos, setCampeonatos] = useState<Campeonato[]>([]);
  const [users, setUsers] = useState<UserData[]>([]);
  // Clubes ya existentes en el workspace, para elegirlos en vez de reescribirlos.
  const [clubes, setClubes] = useState<ClubMaestro[]>([]);
  const [tab, setTab] = useState<"campeonatos" | "jueces">("campeonatos");
  const [showNewCamp, setShowNewCamp] = useState(false);
  const [showNewUser, setShowNewUser] = useState(false);
  // Paneles de traspaso entre instalaciones (local ↔ internet)
  const [showImportCamp, setShowImportCamp] = useState(false);
  const [showImportUsers, setShowImportUsers] = useState(false);
  const [exportandoUsuarios, setExportandoUsuarios] = useState(false);
  const [newCamp, setNewCamp] = useState({
    nombre: "", descripcion: "", num_tatamis: 6,
    fecha_inicio: "", fecha_fin: "", lugar: "", ciudad: "", pais: "",
    estado: "preparacion" as EstadoCampeonato,
  });
  const [newUser, setNewUser] = useState({
    email: "", password: "", nombre: "", rol: "juez", clubes: [] as ClubMaestro[],
    puede_juzgar: false,
  });
  const [userSearch, setUserSearch] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [rolFiltro, setRolFiltro] = useState<"todos" | "admin" | "maestro" | "juez">("todos");
  const [campSearch, setCampSearch] = useState("");
  const [campFiltro, setCampFiltro] = useState<"todos" | "activos" | "inactivos">("todos");
  const [creandoCamp, setCreandoCamp] = useState(false);
  // Modo mantenimiento: solo lo ve y lo cambia el superadmin.
  const [mant, setMant] = useState<EstadoMantenimiento | null>(null);
  const [mantMensaje, setMantMensaje] = useState("");
  const [guardandoMant, setGuardandoMant] = useState(false);
  const [editingUser, setEditingUser] = useState<UserData | null>(null);
  const [editUserData, setEditUserData] = useState({
    nombre: "", email: "", password: "", rol: "juez", clubes: [] as ClubMaestro[],
    puede_juzgar: false,
  });
  const { pedirConfirmacion, dialogo } = useConfirmDialog();

  useEffect(() => {
    const saved = localStorage.getItem("dinamyt_user");
    if (!saved) { router.replace("/login"); return; }
    const u = JSON.parse(saved);
    if (u.rol !== "admin") { router.replace("/juez"); return; }
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setUser(u);
      void loadData(showInactive);
    });
    return () => { cancelled = true; };
  }, [router, showInactive]);

  async function loadData(includeInactive = false) {
    try {
      const [c, u, cl, m] = await Promise.all([
        listCampeonatosAPI(),
        listUsersAPI(includeInactive),
        // Clubes que ya existen en el workspace: al asignarle un dojang a un
        // maestro se elige de aquí en vez de volver a teclearlo. Un club es un
        // nombre, así que un dedazo al reescribirlo crea uno nuevo y parte en
        // dos las agrupaciones por club de los reportes.
        listClubesDetalleAPI().catch(() => [] as ClubMaestro[]),
        // Solo lo pinta el superadmin, pero se pide siempre: si falla, el
        // panel entero seguiría cargando igual (de ahí el catch).
        obtenerMantenimientoAPI().catch(() => null),
      ]);
      setCampeonatos(c);
      setUsers(u);
      setClubes(cl);
      if (m) {
        setMant(m);
        setMantMensaje(m.mensaje ?? "");
      }
    } catch { /* */ }
  }

  /**
   * Enciende o apaga el modo mantenimiento.
   *
   * Encenderlo pide confirmación: deja fuera a los jueces en mitad de un
   * campeonato, y no es algo que se pulse por curiosidad. Apagarlo, no: volver
   * a abrir nunca es la decisión peligrosa.
   */
  function handleMantenimiento(activar: boolean) {
    const ejecutar = async () => {
      setGuardandoMant(true);
      try {
        const nuevo = await fijarMantenimientoAPI(activar, mantMensaje);
        setMant(nuevo);
        setMantMensaje(nuevo.mensaje ?? "");
        flash(activar ? t("mant.activadoOk") : t("mant.desactivadoOk"), "ok");
      } catch {
        flash(t("mant.error"), "error");
      } finally {
        setGuardandoMant(false);
      }
    };
    if (!activar) {
      void ejecutar();
      return;
    }
    pedirConfirmacion({
      titulo: t("mant.confActivar.titulo"),
      mensaje: t("mant.confActivar.mensaje"),
      tipo: "peligro",
      confirmLabel: t("mant.activar"),
      onConfirm: ejecutar,
    });
  }

  /** Avisa del resultado de una acción con la nube flotante (ver lib/toast). */
  function flash(texto: string, tipo: "ok" | "error" = "ok") {
    aviso(texto, tipo);
  }

  async function handleToggleCampActivo(c: Campeonato) {
    try {
      await updateCampeonatoAPI(c.id, { activo: !c.activo });
      await loadData(showInactive);
      flash(c.activo
        ? t("admin.camp.desactivadoMsg", { nombre: c.nombre })
        : t("admin.camp.activadoMsg", { nombre: c.nombre }), "ok");
    } catch { flash(t("admin.camp.errorEstado"), "error"); }
  }

  async function handleSaveUserEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingUser) return;
    const payload: {
      nombre?: string; email?: string; password?: string; rol?: string;
      clubes?: ClubMaestro[]; puede_juzgar?: boolean;
    } = {};
    if (editUserData.nombre.trim()) payload.nombre = editUserData.nombre.trim();
    if (editUserData.email.trim()) payload.email = editUserData.email.trim();
    if (editUserData.password) payload.password = editUserData.password;
    if (editUserData.rol && editUserData.rol !== editingUser.rol) payload.rol = editUserData.rol;
    // Clubes y permiso de juez cuando el usuario es (o pasa a ser) maestro. La
    // delegación viaja dentro de cada club: es de cada dojang, no del maestro.
    const rolEfectivo = editUserData.rol || editingUser.rol;
    if (rolEfectivo === "maestro") {
      if (editUserData.clubes.length === 0) {
        flash(t("admin.usuarios.clubReq"), "error");
        return;
      }
      payload.clubes = editUserData.clubes;
      payload.puede_juzgar = editUserData.puede_juzgar;
    }
    try {
      await updateUserAPI(editingUser.id, payload);
      setEditingUser(null);
      await loadData(showInactive);
      flash(t("admin.usuarios.actualizado"), "ok");
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("admin.usuarios.errorActualizar"), "error");
    }
  }

  function handleToggleUserActivo(target: UserData) {
    if (target.id === user?.id) {
      flash(t("admin.usuarios.noPropio"), "error");
      return;
    }
    const ejecutar = async () => {
      try {
        await updateUserAPI(target.id, { activo: !target.activo });
        await loadData(showInactive);
        flash(target.activo ? t("admin.usuarios.desactivado") : t("admin.usuarios.reactivado"), "ok");
      } catch { flash(t("admin.usuarios.errorEstado"), "error"); }
    };
    if (target.activo) {
      pedirConfirmacion({
        titulo: t("admin.usuarios.confDesactivar.titulo"),
        mensaje: t("admin.usuarios.confDesactivar.mensaje", { nombre: target.nombre }),
        tipo: "peligro",
        confirmLabel: t("comun.desactivar"),
        onConfirm: ejecutar,
      });
    } else {
      void ejecutar();
    }
  }

  async function handleCreateCamp(e: React.FormEvent) {
    e.preventDefault();
    if (creandoCamp) return;
    setCreandoCamp(true);
    try {
      await createCampeonatoAPI(newCamp);
      setShowNewCamp(false);
      setNewCamp({
        nombre: "", descripcion: "", num_tatamis: 6,
        fecha_inicio: "", fecha_fin: "", lugar: "", ciudad: "", pais: "",
        estado: "preparacion",
      });
      // Con `await`: el aviso sale cuando la lista YA muestra el campeonato
      // nuevo. Sin él, "creado" aparecía junto a una lista que todavía era la
      // de antes, y desde la pantalla parecía que no se había hecho nada.
      await loadData(showInactive);
      flash(t("admin.camp.creado"), "ok");
    } catch {
      flash(t("admin.camp.errorCrear"), "error");
      await loadData(showInactive);
    } finally {
      setCreandoCamp(false);
    }
  }

  async function handleCreateUser(e: React.FormEvent) {
    e.preventDefault();
    if (newUser.rol === "maestro" && newUser.clubes.length === 0) {
      flash(t("admin.usuarios.clubReq"), "error");
      return;
    }
    try {
      await registerUserAPI({
        email: newUser.email,
        password: newUser.password,
        nombre: newUser.nombre,
        rol: newUser.rol,
        ...(newUser.rol === "maestro"
          ? {
              clubes: newUser.clubes,
              puede_juzgar: newUser.puede_juzgar,
            }
          : {}),
      });
      setShowNewUser(false);
      setNewUser({ email: "", password: "", nombre: "", rol: "juez", clubes: [], puede_juzgar: false });
      await loadData(showInactive);
      flash(t("admin.usuarios.creado"), "ok");
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("admin.usuarios.errorCrear"), "error");
    }
  }

  if (!user) return null;

  // Jerarquía: el dato fresco de superadmin viene de la lista de usuarios
  // (el user guardado en localStorage puede ser de un login viejo sin el campo)
  const esSuper = users.some((u) => u.id === user.id && u.es_superadmin);

  // Filtro combinado de campeonatos: búsqueda por nombre + estado activo/inactivo
  const coincideCamp = (c: Campeonato) =>
    c.nombre.toLowerCase().includes(campSearch.trim().toLowerCase())
    && (campFiltro === "todos" || (campFiltro === "activos" ? c.activo : !c.activo));

  return (
    <div className="admin-page" style={{ maxWidth: 960, margin: "0 auto", padding: "20px" }}>
      {/* Header */}
      <div className="admin-header" style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 24, paddingBottom: 16, borderBottom: "1px solid var(--border)"
      }}>
        {/* La marca ya esta en la barra de arriba (`AppMenu`), asi que aqui va
            lo que va en Membresias: antetitulo + titulo de la pantalla. Antes
            se repetia «DINAMYT» dos veces en la misma vista. */}
        <div>
          <p className="eyebrow">{t("app.antetitulo")}</p>
          <h1 className="display" style={{ fontSize: "1.5rem", marginTop: 4 }}>
            {t("admin.panel")}
          </h1>
          <p className="muted" style={{ fontSize: "0.85rem", marginTop: 2 }}>
            {user.nombre}
          </p>
        </div>
      </div>

      {dialogo}

      {/* ══════════════ MODO MANTENIMIENTO (solo superadmin) ══════════════
          Va arriba del todo y no dentro de una pestaña: se busca justo antes
          de subir una actualización, con prisa, y esconderlo en un submenú es
          garantizar que se olvide. */}
      {esSuper && mant && (
        <div
          className="card"
          style={{
            marginBottom: 20,
            borderColor: mant.activo ? "var(--gold-border)" : "var(--border)",
            background: mant.activo ? "var(--gold-bg)" : undefined,
          }}
        >
          <div className="card-title">🛠️ {t("mant.panel")}</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", margin: "0 0 10px" }}>
            {t("mant.panelDesc")}
          </p>
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            flexWrap: "wrap", marginBottom: 10,
          }}>
            <span style={{
              padding: "4px 10px", borderRadius: "var(--radius-sm)",
              fontSize: "0.82rem", fontWeight: 700,
              textTransform: "uppercase", letterSpacing: "0.08em",
              background: mant.activo ? "rgba(255,68,68,0.10)" : "var(--green-bg)",
              color: mant.activo ? "var(--red-alert)" : "var(--green)",
              border: `1px solid ${mant.activo ? "rgba(255,68,68,0.35)" : "rgba(0,196,106,.25)"}`,
            }}>
              {mant.activo ? t("mant.estadoActivo") : t("mant.estadoInactivo")}
            </span>
            {mant.desde && (
              <span style={{ color: "var(--text-dim)", fontSize: "0.84rem" }}>
                {t("mant.desde")} {new Date(mant.desde).toLocaleString()}
              </span>
            )}
          </div>
          <label style={{
            display: "block", color: "var(--text-muted)",
            fontSize: "0.84rem", fontWeight: 700, marginBottom: 6,
          }}>
            {t("mant.mensajeLabel")}
          </label>
          <input
            className="input"
            value={mantMensaje}
            maxLength={300}
            onChange={(e) => setMantMensaje(e.target.value)}
            style={{ marginBottom: 10 }}
          />
          <button
            type="button"
            className={`btn ${mant.activo ? "btn-primary" : "btn-danger"}`}
            disabled={guardandoMant}
            onClick={() => handleMantenimiento(!mant.activo)}
          >
            {mant.activo ? t("mant.desactivar") : t("mant.activar")}
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="admin-tabs" style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {/* "pestana" y no "t": no hacerle sombra a la función de traducción */}
        {(["campeonatos", "jueces"] as const).map((pestana) => (
          <button
            key={pestana}
            className="btn"
            onClick={() => setTab(pestana)}
            style={{
              background: tab === pestana ? "var(--gold-bg)" : undefined,
              borderColor: tab === pestana ? "var(--gold-border)" : undefined,
              color: tab === pestana ? "var(--gold)" : undefined,
              textTransform: "capitalize",
            }}
          >
            {pestana === "campeonatos" ? t("admin.tab.campeonatos") : t("admin.tab.jueces")}
          </button>
        ))}
        <button className="btn" onClick={() => router.push("/admin/competidores")}>
          {t("admin.tab.competidores")}
        </button>
        <button className="btn" onClick={() => router.push("/admin/importar-resultados")}>
          Importar resultados
        </button>
      </div>

      {/* ══════════════ CAMPEONATOS TAB ══════════════ */}
      {tab === "campeonatos" && (
        <div className="animate-fade">
          <div className="admin-section-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
            <h2 style={{ fontFamily: "var(--font-body)", fontWeight: 700, fontSize: "1.1rem" }}>
              {t("admin.tab.campeonatos")} ({campeonatos.length})
            </h2>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                className={`btn btn-sm ${showImportCamp ? "btn-primary" : ""}`}
                onClick={() => setShowImportCamp(!showImportCamp)}
              >
                {t("sync.importarCampeonato")}
              </button>
              <button className="btn btn-primary btn-sm" onClick={() => setShowNewCamp(!showNewCamp)}>
                {t("admin.camp.nuevo")}
              </button>
            </div>
          </div>

          {/* Traer un campeonato completo desde la otra instalación */}
          {showImportCamp && (
            <div style={{ marginBottom: 16 }}>
              <ImportarPaquetePanel
                conModo
                onImportado={(informe) => {
                  setShowImportCamp(false);
                  loadData(showInactive);
                  flash(informe.message, "ok");
                }}
              />
            </div>
          )}

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
            <input
              className="input"
              placeholder={t("admin.camp.buscar")}
              value={campSearch}
              onChange={(e) => setCampSearch(e.target.value)}
              style={{ flex: "1 1 200px", maxWidth: 380 }}
            />
            <select
              className="input"
              value={campFiltro}
              onChange={(e) => setCampFiltro(e.target.value as "todos" | "activos" | "inactivos")}
              aria-label={t("admin.camp.filtroAria")}
              style={{ width: "auto", minWidth: 150, padding: "8px 30px 8px 12px", minHeight: 38 }}
            >
              <option value="todos">{t("admin.filtro.todos")}</option>
              <option value="activos">{t("admin.filtro.activos")}</option>
              <option value="inactivos">{t("admin.filtro.inactivos")}</option>
            </select>
          </div>

          {showNewCamp && (
            <div className="card animate-slide" style={{ marginBottom: 16 }}>
              <div className="card-title">{t("admin.camp.crear.titulo")}</div>
              <form onSubmit={handleCreateCamp} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {/* Nombre y sede en mayúsculas (así se guardan); la
                    descripción no: ahí cabe una frase, no un dato. */}
                <input className="input" maxLength={LIM.titulo} placeholder={t("admin.camp.nombre")} value={newCamp.nombre}
                  onChange={(e) => setNewCamp({ ...newCamp, nombre: enMayusculas(e.target.value) })} required />
                <input className="input" maxLength={LIM.descripcion} placeholder={t("admin.camp.desc")} value={newCamp.descripcion}
                  onChange={(e) => setNewCamp({ ...newCamp, descripcion: e.target.value })} />
                {/* <div> y no <label>: el disparador de <CampoFecha> es un
                    botón, y un <label> que lo envuelva le reenvía el clic
                    hecho sobre el panel, reabriéndolo. */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 700 }}>
                    {t("camp.campos.fechaInicio")}
                    <CampoFecha valor={newCamp.fecha_inicio} ariaLabel={t("camp.campos.fechaInicio")}
                      onChange={(v) => setNewCamp({ ...newCamp, fecha_inicio: v })} />
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 700 }}>
                    {t("camp.campos.fechaFin")}
                    <CampoFecha valor={newCamp.fecha_fin} ariaLabel={t("camp.campos.fechaFin")}
                      min={newCamp.fecha_inicio || undefined}
                      onChange={(v) => setNewCamp({ ...newCamp, fecha_fin: v })} />
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
                  <label className="pcs-field" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--text-muted)" }}>{t("camp.campos.lugar")}</span>
                    <input className="input" placeholder={t("camp.campos.lugar")} value={newCamp.lugar}
                      maxLength={120} onChange={(e) => setNewCamp({ ...newCamp, lugar: enMayusculas(e.target.value.slice(0, 120)) })} />
                  </label>
                  <PaisCiudadSelect pais={newCamp.pais} ciudad={newCamp.ciudad}
                    onChange={(pais, ciudad) => setNewCamp({ ...newCamp, pais, ciudad })} />
                </div>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <label style={{ color: "var(--text-muted)", fontSize: "0.9rem", whiteSpace: "nowrap" }}>{t("camp.campos.estado")}</label>
                  <select className="input" value={newCamp.estado} style={{ minWidth: 160 }}
                    onChange={(e) => setNewCamp({ ...newCamp, estado: e.target.value as EstadoCampeonato })}>
                    <option value="preparacion">{t("camp.estado.preparacion")}</option>
                    <option value="en_curso">{t("camp.estado.en_curso")}</option>
                    <option value="finalizado">{t("camp.estado.finalizado")}</option>
                  </select>
                </div>
                <p style={{ color: "var(--text-dim)", fontSize: "0.82rem", margin: 0 }}>
                  {t("camp.estado.preparacionAyuda")}
                </p>
                <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                  <label style={{ color: "var(--text-muted)", fontSize: "0.9rem", whiteSpace: "nowrap" }}>{t("admin.camp.tatamisLabel")}</label>
                  <input className="input" type="number" min={1} max={10} value={newCamp.num_tatamis}
                    onChange={(e) => {
                      const n = parseInt(e.target.value) || 1;
                      setNewCamp({ ...newCamp, num_tatamis: Math.min(10, Math.max(1, n)) });
                    }}
                    style={{ width: 80 }} />
                  <span style={{ color: "var(--text-dim)", fontSize: "0.85rem" }}>{t("admin.camp.max10")}</span>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button type="submit" className="btn btn-primary" disabled={creandoCamp}>
                    {creandoCamp ? t("admin.camp.creando") : t("comun.crear")}
                  </button>
                  <button type="button" className="btn" onClick={() => setShowNewCamp(false)} disabled={creandoCamp}>{t("comun.cancelar")}</button>
                </div>
              </form>
            </div>
          )}

          {campeonatos.filter(coincideCamp).length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: 40, color: "var(--text-dim)" }}>
              {campeonatos.length === 0
                ? t("admin.camp.vacio")
                : t("admin.camp.sinCoincidencias")}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {campeonatos
                .filter(coincideCamp)
                .map((c) => (
                <div key={c.id} className="card" style={{ cursor: "pointer" }}
                  onClick={() => router.push(`/admin/campeonato/${c.id}`)}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                    <div style={{ minWidth: 0 }}>
                      <h3 style={{ fontWeight: 700, fontSize: "1.05rem", marginBottom: 4 }}>
                        {c.nombre}
                        <span className={`badge ${c.activo ? "badge-green" : "badge-gray"}`} style={{ marginLeft: 8, verticalAlign: "middle" }}>
                          {c.activo ? t("comun.activo") : t("comun.inactivo")}
                        </span>
                        <span className="badge badge-gray" style={{ marginLeft: 6, verticalAlign: "middle" }}>
                          {t(`camp.estado.${c.estado || "preparacion"}` as ClaveTexto)}
                        </span>
                        {(c.num_pendientes || 0) > 0 && (
                          <span className="badge" style={{
                            marginLeft: 6, verticalAlign: "middle",
                            background: "var(--gold-bg)", color: "var(--gold)",
                            border: "1px solid var(--gold-border)",
                          }}>
                            {t("camp.solicitudes.pendientes", { n: c.num_pendientes! })}
                          </span>
                        )}
                      </h3>
                      <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>
                        {c.num_tatamis} {t("comun.tatamis")}
                        {c.descripcion && ` · ${c.descripcion}`}
                        {!c.activo && t("admin.camp.oculto")}
                      </p>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                      <button
                        className={`btn btn-sm ${c.activo ? "btn-danger" : "btn-primary"}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleToggleCampActivo(c);
                        }}
                      >
                        {c.activo ? t("comun.desactivar") : t("comun.activar")}
                      </button>
                      <span style={{ color: "var(--gold)", fontSize: "0.9rem" }}>{t("admin.camp.verDetalles")}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ══════════════ JUECES TAB ══════════════ */}
      {tab === "jueces" && (
        <div className="animate-fade">
          <div className="admin-section-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
            <h2 style={{ fontFamily: "var(--font-body)", fontWeight: 700, fontSize: "1.1rem" }}>
              {t("admin.usuarios.titulo")} ({users.length})
            </h2>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                className="btn btn-sm"
                disabled={exportandoUsuarios}
                onClick={async () => {
                  setExportandoUsuarios(true);
                  try {
                    await exportarUsuariosAPI();
                    flash(t("sync.exportado"), "ok");
                  } catch { flash(t("sync.errorExportar"), "error"); }
                  finally { setExportandoUsuarios(false); }
                }}
              >
                {exportandoUsuarios ? t("sync.exportando") : t("sync.exportarUsuarios")}
              </button>
              <button
                className={`btn btn-sm ${showImportUsers ? "btn-primary" : ""}`}
                onClick={() => setShowImportUsers(!showImportUsers)}
              >
                {t("sync.importarUsuarios")}
              </button>
              <button className="btn btn-primary btn-sm" onClick={() => setShowNewUser(!showNewUser)}>
                {t("admin.usuarios.nuevo")}
              </button>
            </div>
          </div>

          {/* Traer maestros y jueces desde la otra instalación */}
          {showImportUsers && (
            <div style={{ marginBottom: 16 }}>
              <ImportarPaquetePanel
                onImportado={async (informe) => {
                  setShowImportUsers(false);
                  await loadData(showInactive);
                  flash(informe.message, "ok");
                }}
              />
            </div>
          )}

          {showNewUser && (
            <div className="card animate-slide" style={{ marginBottom: 16 }}>
              <div className="card-title">{t("admin.usuarios.crear.titulo")}</div>
              <form onSubmit={handleCreateUser} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {/* Nombre y club en MAYÚSCULAS mientras se escriben: así se
                    guardan (ver lib/texto.ts y el backend). */}
                <input className="input" maxLength={LIM.nombrePersona} placeholder={t("admin.usuarios.nombre")} value={newUser.nombre}
                  onChange={(e) => setNewUser({ ...newUser, nombre: enMayusculas(e.target.value) })} required />
                <input className="input" type="email" maxLength={LIM.correo} placeholder={t("admin.usuarios.correo")} value={newUser.email}
                  onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} required />
                <CampoContrasena placeholder={t("admin.usuarios.contrasena")} value={newUser.password}
                  autoComplete="new-password"
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} required />
                {/* Jerarquía: cualquier admin agrega jueces y maestros a su
                    equipo; solo el superadmin puede crear administradores. */}
                <select className="input" value={newUser.rol}
                  onChange={(e) => setNewUser({ ...newUser, rol: e.target.value })}>
                  <option value="juez">{t("rol.juez")}</option>
                  <option value="maestro">{t("rol.maestro")}</option>
                  {esSuper && <option value="admin">{t("rol.admin")}</option>}
                </select>
                {newUser.rol === "maestro" && (
                  <>
                    <ClubesInput
                      clubes={newUser.clubes}
                      sugerencias={clubes}
                      onChange={(nuevos) => setNewUser({ ...newUser, clubes: nuevos })}
                    />
                    <label style={{
                      display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
                      fontSize: "0.9rem", color: "var(--text-muted)", fontWeight: 700, userSelect: "none",
                    }}>
                      <input type="checkbox" checked={newUser.puede_juzgar}
                        onChange={(e) => setNewUser({ ...newUser, puede_juzgar: e.target.checked })}
                        style={{ accentColor: "var(--gold)", width: 16, height: 16 }} />
                      {t("admin.usuarios.puedeJuzgar")}
                    </label>
                    <p style={{ color: "var(--text-dim)", fontSize: "0.84rem", margin: 0 }}>
                      {t("admin.usuarios.rolMaestroNota")}
                    </p>
                  </>
                )}
                <div style={{ display: "flex", gap: 8 }}>
                  <button type="submit" className="btn btn-primary">{t("comun.crear")}</button>
                  <button type="button" className="btn" onClick={() => setShowNewUser(false)}>{t("comun.cancelar")}</button>
                </div>
              </form>
            </div>
          )}

          {/* Buscador, filtro por tipo y filtro de inactivos */}
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
            <input
              className="input"
              placeholder={t("admin.usuarios.buscar")}
              value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)}
              style={{ flex: "1 1 200px", maxWidth: 380 }}
            />
            <select
              className="input"
              value={rolFiltro}
              onChange={(e) => setRolFiltro(e.target.value as "todos" | "admin" | "maestro" | "juez")}
              aria-label={t("admin.usuarios.filtroAria")}
              style={{ width: "auto", minWidth: 150, padding: "8px 30px 8px 12px", minHeight: 38 }}
            >
              <option value="todos">{t("admin.usuarios.filtro.todos")}</option>
              <option value="admin">{t("admin.usuarios.filtro.admins")}</option>
              <option value="maestro">{t("admin.usuarios.filtro.maestros")}</option>
              <option value="juez">{t("admin.usuarios.filtro.jueces")}</option>
            </select>
            <label style={{
              display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
              fontSize: "0.88rem", color: "var(--text-muted)", fontWeight: 700,
              userSelect: "none", whiteSpace: "nowrap",
            }}>
              <input
                type="checkbox"
                checked={showInactive}
                onChange={(e) => setShowInactive(e.target.checked)}
                style={{ accentColor: "var(--gold)", width: 16, height: 16 }}
              />
              {t("admin.usuarios.mostrarInactivos")}
            </label>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {users
              .filter((u) => rolFiltro === "todos" || u.rol === rolFiltro)
              .filter((u) => {
                const q = userSearch.trim().toLowerCase();
                if (!q) return true;
                return `${u.nombre} ${u.email}`.toLowerCase().includes(q);
              })
              .map((u) => (
              <div key={u.id}>
                <div className="admin-user-row card" style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  opacity: u.activo ? 1 : 0.55,
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ overflowWrap: "anywhere" }}>
                      <span style={{ fontWeight: 700 }}>{u.nombre}</span>
                      <span style={{ color: "var(--text-muted)", marginLeft: 8, fontSize: "0.9rem" }}>{u.email}</span>
                      {!u.activo && (
                        <span className="badge badge-gray" style={{ marginLeft: 8 }}>{t("comun.inactivo")}</span>
                      )}
                    </div>
                    <div style={{ color: "var(--text-dim)", fontSize: "0.84rem", marginTop: 4 }}>
                      {t("admin.usuarios.agregado")} {u.created_at ? new Date(u.created_at).toLocaleDateString("es-CO") : "—"}
                      {u.creado_por ? ` ${t("comun.por")} ${u.creado_por.nombre}` : ""}
                      {/* Cada dojang CON SU ciudad, no solo el principal: es lo
                          que evita crearle una segunda cuenta por creer que le
                          falta uno, y ver de un vistazo que uno está en otra
                          delegación. */}
                      {u.rol === "maestro" && clubesDe(u).length > 0
                        ? ` · ${t("admin.usuarios.club")}: ${clubesDe(u).map(
                            (c) => c.ciudad ? `${c.nombre} (${c.ciudad})` : c.nombre,
                          ).join(" · ")}`
                        : ""}
                      {u.rol === "maestro" && u.puede_juzgar ? ` · ${t("rol.juez")}` : ""}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                    <span style={{
                      padding: "4px 10px", borderRadius: "var(--radius-sm)", fontSize: "0.82rem",
                      fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em",
                      background: u.rol === "admin" ? "var(--gold-bg)" : u.rol === "maestro" ? "var(--green-bg)" : "var(--chung-bg)",
                      color: u.rol === "admin" ? "var(--gold)" : u.rol === "maestro" ? "var(--green)" : "var(--chung-light)",
                      border: `1px solid ${u.rol === "admin" ? "var(--gold-border)" : u.rol === "maestro" ? "rgba(0,196,106,.35)" : "var(--chung-border)"}`,
                    }}>{u.es_superadmin ? t("rol.superadmin") : u.rol === "admin" ? t("rol.admin") : u.rol === "maestro" ? t("rol.maestro") : t("rol.juez")}</span>
                    <button
                      className="btn btn-sm"
                      onClick={() => {
                        if (editingUser?.id === u.id) {
                          setEditingUser(null);
                        } else {
                          setEditingUser(u);
                          setEditUserData({
                            // Un usuario creado antes de esta regla se abre ya
                            // en mayúsculas: se ve como se va a guardar.
                            nombre: enMayusculas(u.nombre), email: u.email, password: "", rol: u.rol,
                            clubes: clubesDe(u),
                            puede_juzgar: !!u.puede_juzgar,
                          });
                        }
                      }}
                      style={{ padding: "4px 10px", fontSize: "0.82rem" }}
                    >
                      {editingUser?.id === u.id ? t("comun.cerrar") : t("comun.editar")}
                    </button>
                    <button
                      className={`btn btn-sm ${u.activo ? "btn-danger" : "btn-primary"}`}
                      onClick={() => handleToggleUserActivo(u)}
                      disabled={u.id === user.id}
                      style={{ padding: "4px 10px", fontSize: "0.82rem" }}
                    >
                      {u.activo ? t("comun.desactivar") : t("comun.reactivar")}
                    </button>
                  </div>
                </div>

                {/* Edición: correo, nombre y restablecer contraseña (solo admin) */}
                {editingUser?.id === u.id && (
                  <form onSubmit={handleSaveUserEdit} className="card animate-slide" style={{
                    display: "flex", flexDirection: "column", gap: 10,
                    marginTop: 6, borderColor: "var(--gold-border)",
                  }}>
                    <div className="card-title">{t("admin.usuarios.editarA", { nombre: u.nombre })}</div>
                    <input className="input" maxLength={LIM.nombrePersona} placeholder={t("admin.usuarios.nombre")} value={editUserData.nombre}
                      onChange={(e) => setEditUserData({ ...editUserData, nombre: enMayusculas(e.target.value) })} />
                    <input className="input" type="email" maxLength={LIM.correo} placeholder={t("admin.usuarios.correo")} value={editUserData.email}
                      onChange={(e) => setEditUserData({ ...editUserData, email: e.target.value })} />
                    <CampoContrasena autoComplete="new-password"
                      placeholder={t("admin.usuarios.nuevaContrasena")}
                      value={editUserData.password}
                      onChange={(e) => setEditUserData({ ...editUserData, password: e.target.value })} />
                    {/* Rol: alternar juez/maestro lo hace cualquier admin; el
                        rol de administrador es exclusivo del superadmin. */}
                    {(esSuper || u.rol !== "admin") && (
                      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                        <label style={{ color: "var(--text-muted)", fontSize: "0.9rem", whiteSpace: "nowrap" }}>{t("admin.usuarios.rolLabel")}</label>
                        <select className="input" value={editUserData.rol}
                          disabled={u.id === user.id}
                          onChange={(e) => setEditUserData({ ...editUserData, rol: e.target.value })}>
                          <option value="juez">{t("rol.juez")}</option>
                          <option value="maestro">{t("rol.maestro")}</option>
                          {esSuper && <option value="admin">{t("rol.admin")}</option>}
                        </select>
                      </div>
                    )}
                    {(editUserData.rol || u.rol) === "maestro" && (
                      <>
                        <ClubesInput
                          clubes={editUserData.clubes}
                          sugerencias={clubes}
                          onChange={(nuevos) => setEditUserData({ ...editUserData, clubes: nuevos })}
                        />
                        <label style={{
                          display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
                          fontSize: "0.9rem", color: "var(--text-muted)", fontWeight: 700, userSelect: "none",
                        }}>
                          <input type="checkbox" checked={editUserData.puede_juzgar}
                            onChange={(e) => setEditUserData({ ...editUserData, puede_juzgar: e.target.checked })}
                            style={{ accentColor: "var(--gold)", width: 16, height: 16 }} />
                          {t("admin.usuarios.puedeJuzgar")}
                        </label>
                      </>
                    )}
                    <p style={{ color: "var(--text-dim)", fontSize: "0.84rem", margin: 0 }}>
                      {t("admin.usuarios.notaReset")}
                      {u.id === user.id
                        ? t("admin.usuarios.notaPropio")
                        : t("admin.usuarios.notaRolCambio")}
                    </p>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button type="submit" className="btn btn-primary btn-sm">{t("comun.guardarCambios")}</button>
                      <button type="button" className="btn btn-sm" onClick={() => setEditingUser(null)}>{t("comun.cancelar")}</button>
                    </div>
                  </form>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      <style>{`
        .admin-section-header .btn {
          flex: 0 0 auto;
        }
        @media (max-width: 420px) {
          .admin-section-header {
            flex-direction: column;
            align-items: stretch !important;
          }
          .admin-section-header .btn {
            width: 100%;
          }
        }
        @media (max-width: 640px) {
          .admin-page {
            padding: 14px !important;
          }
          .admin-header {
            align-items: flex-start !important;
            gap: 12px;
            flex-wrap: wrap;
          }
          .admin-tabs {
            overflow-x: auto;
            padding-bottom: 2px;
          }
          .admin-tabs .btn {
            flex: 0 0 auto;
          }
          .admin-user-row {
            align-items: flex-start !important;
            gap: 12px;
            flex-wrap: wrap;
          }
          .admin-user-row > div:last-child {
            width: 100%;
            justify-content: space-between;
          }
        }
      `}</style>
    </div>
  );
}
