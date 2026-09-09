"use client";

// ═════════════════════════════════════════════════════════════════════════════
// INSCRIPCIONES DE UN CAMPEONATO
//
// Panel único de inscritos, separado del de tatamis (que vive en la ficha del
// campeonato). Las inscripciones se agrupan en tres pestañas por estado:
//
//   Pendientes — solicitudes de maestros por revisar. NO cuentan como inscritos
//                ni entran a las llaves hasta que el admin las acepte.
//   Aceptadas  — el roster real del campeonato. Aquí se dan de alta atletas.
//   Rechazadas — denegadas, con su motivo; se pueden reconsiderar.
//
// Se cargan las tres de una sola vez (el endpoint sin `estado` las devuelve
// todas) y se agrupan en cliente, así los contadores siempre concuerdan.
// ═════════════════════════════════════════════════════════════════════════════

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  CINTURONES,
  deleteInscripcionAPI,
  getCampeonatoAPI,
  getConfigCategoriasAPI,
  inscribirAPI,
  listClubesAPI,
  listCompetidoresAPI,
  listInscripcionesAPI,
  setEstadoInscripcionAPI,
  updateCompetidorAPI,
  updateInscripcionAPI,
  type CompetidorData,
  type EstadoInscripcion,
  type InscripcionData,
} from "@/lib/api";
import CompetidorFormFields, {
  COMPETIDOR_FORM_VACIO,
  edadDesde,
  formToPayload,
  type CompetidorFormState,
} from "@/components/CompetidorFormFields";
import ImportarExcelPanel from "@/components/ImportarExcelPanel";
import { useConfirmDialog } from "@/components/ConfirmDialog";
import { useI18n, type ClaveTexto } from "@/lib/i18n";
import { aviso } from "@/lib/toast";

// Nombres CANÓNICOS de modalidad (viajan al servidor y a los reportes):
// se muestran tal cual, sin traducir, para no fragmentar el registro.
const MODALIDADES_FALLBACK = [
  "COMBATE", "FIGURA A MANOS LIBRES", "FIGURA CON ARMAS", "DEFENSA PERSONAL",
];

type Panel = "ninguno" | "existente" | "nuevo" | "excel";

const PESTANAS: { estado: EstadoInscripcion; labelKey: ClaveTexto }[] = [
  { estado: "pendiente", labelKey: "ins.tab.pendientes" },
  { estado: "aceptada", labelKey: "ins.tab.aceptadas" },
  { estado: "rechazada", labelKey: "ins.tab.rechazadas" },
];

// Ventana de "perdón" (días): si los datos del atleta se actualizaron hace
// menos de esto, se inscribe directo sin pedir confirmación. Cubre varios
// campeonatos en fechas cercanas (p. ej. dos fines de semana seguidos).
const DIAS_VENTANA_DATOS = 14;

function diasDesde(fechaISO?: string | null): number | null {
  if (!fechaISO) return null;
  const t = new Date(fechaISO).getTime();
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((Date.now() - t) / 86_400_000));
}

export default function InscripcionesPage() {
  const router = useRouter();
  const { t } = useI18n();
  const params = useParams();
  const campId = Number(params.id);

  const [campNombre, setCampNombre] = useState("");
  const [inscripciones, setInscripciones] = useState<InscripcionData[]>([]);
  const [competidores, setCompetidores] = useState<CompetidorData[]>([]);
  const [clubes, setClubes] = useState<string[]>([]);
  const [modalidadesDisponibles, setModalidadesDisponibles] = useState<string[]>(MODALIDADES_FALLBACK);

  const [pestana, setPestana] = useState<EstadoInscripcion>("aceptada");
  const [panel, setPanel] = useState<Panel>("ninguno");
  const [busquedaExistente, setBusquedaExistente] = useState("");
  const [seleccionado, setSeleccionado] = useState<CompetidorData | null>(null);
  const [modalidadesSel, setModalidadesSel] = useState<string[]>(["COMBATE"]);
  const [pesoInscripcion, setPesoInscripcion] = useState("");
  // Confirmación de datos viejos: peso y cinturón editables antes de inscribir
  const [confPeso, setConfPeso] = useState("");
  const [confCinturon, setConfCinturon] = useState("");
  const [formNuevo, setFormNuevo] = useState<CompetidorFormState>(COMPETIDOR_FORM_VACIO);
  const [guardando, setGuardando] = useState(false);

  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [editModalidades, setEditModalidades] = useState<string[]>([]);
  const [editPeso, setEditPeso] = useState("");
  // Motivo de rechazo por solicitud (pestaña de pendientes)
  const [motivos, setMotivos] = useState<Record<number, string>>({});

  const [busquedaLista, setBusquedaLista] = useState("");
  const { pedirConfirmacion, dialogo } = useConfirmDialog();

  const cargar = useCallback(async () => {
    try {
      // Sin filtro de estado: llegan las tres listas de una vez.
      const [ins, comps, cl] = await Promise.all([
        listInscripcionesAPI(campId),
        listCompetidoresAPI(),
        listClubesAPI().catch(() => [] as string[]),
      ]);
      setInscripciones(ins);
      setCompetidores(comps);
      setClubes(cl);
    } catch { /* */ }
  }, [campId]);

  useEffect(() => {
    const saved = localStorage.getItem("dinamyt_user");
    if (!saved || JSON.parse(saved).rol !== "admin") {
      router.replace("/login");
      return;
    }
    let cancelled = false;
    queueMicrotask(async () => {
      if (cancelled) return;
      // Pestaña inicial por query (?estado=pendiente): la ficha del campeonato
      // enlaza así su aviso de solicitudes por revisar. Se lee de window y no
      // con useSearchParams porque este componente no está bajo un <Suspense>,
      // y sin él la compilación de producción falla.
      const pedida = new URLSearchParams(window.location.search).get("estado");
      if (pedida === "pendiente" || pedida === "rechazada" || pedida === "aceptada") {
        setPestana(pedida);
      }
      try {
        const c = await getCampeonatoAPI(campId);
        if (!cancelled) setCampNombre(c.nombre);
      } catch {
        if (!cancelled) router.replace("/admin");
        return;
      }
      void cargar();
      try {
        const { config } = await getConfigCategoriasAPI(campId);
        const activas = config.modalidades.filter((m) => m.activa).map((m) => m.nombre);
        if (!cancelled && activas.length) setModalidadesDisponibles(activas);
      } catch { /* la config es opcional para inscribir */ }
    });
    return () => { cancelled = true; };
  }, [campId, cargar, router]);

  /** Avisa del resultado de una acción con la nube flotante (ver lib/toast). */
  function flash(texto: string, tipo: "ok" | "error" = "ok") {
    aviso(texto, tipo);
  }

  function toggleModalidad(lista: string[], setLista: (l: string[]) => void, m: string) {
    setLista(lista.includes(m) ? lista.filter((x) => x !== m) : [...lista, m]);
  }

  function abrirPanel(p: Panel) {
    setPanel(panel === p ? "ninguno" : p);
    setSeleccionado(null);
    setBusquedaExistente("");
    setModalidadesSel(["COMBATE"]);
    setPesoInscripcion("");
    setFormNuevo(COMPETIDOR_FORM_VACIO);
  }

  function cambiarPestana(estado: EstadoInscripcion) {
    setPestana(estado);
    setPanel("ninguno");
    setEditandoId(null);
    setBusquedaLista("");
  }

  /** Selecciona un candidato y precarga sus datos para la confirmación. */
  function seleccionarCandidato(c: CompetidorData) {
    setSeleccionado(c);
    setConfPeso(c.peso != null ? String(c.peso) : "");
    setConfCinturon(c.cinturon || "");
  }

  // Días desde la última actualización de datos del seleccionado
  const diasDatos = seleccionado
    ? diasDesde(seleccionado.updated_at || seleccionado.created_at)
    : null;
  const datosViejos = diasDatos != null && diasDatos > DIAS_VENTANA_DATOS;

  /**
   * Inscribe al seleccionado. Con `actualizar`, primero guarda el peso y el
   * cinturón confirmados en la ficha del atleta (re-marca su updated_at) y la
   * inscripción toma el snapshot de esos datos frescos.
   */
  async function inscribirSeleccionado(actualizar: boolean) {
    if (!seleccionado) return;
    setGuardando(true);
    try {
      if (actualizar) {
        await updateCompetidorAPI(seleccionado.id, {
          nombre_completo: seleccionado.nombre_completo,
          peso: confPeso.trim() ? Number(confPeso.replace(",", ".")) : null,
          cinturon: confCinturon || null,
        });
      }
      await inscribirAPI(campId, {
        competidor_id: seleccionado.id,
        modalidades: modalidadesSel,
        peso: !actualizar && pesoInscripcion.trim()
          ? Number(pesoInscripcion.replace(",", "."))
          : undefined,
      });
      flash(t("ins.inscrito", { nombre: seleccionado.nombre_completo }));
      abrirPanel("ninguno");
      await cargar();
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("ins.errorInscribir"), "error");
    } finally {
      setGuardando(false);
    }
  }

  async function handleInscribirExistente(e: React.FormEvent) {
    e.preventDefault();
    // Con datos viejos el envío va por los botones explícitos del aviso
    if (datosViejos) return;
    await inscribirSeleccionado(false);
  }

  async function handleInscribirNuevo(e: React.FormEvent) {
    e.preventDefault();
    if (!formNuevo.nombre_completo.trim()) return;
    setGuardando(true);
    try {
      await inscribirAPI(campId, {
        competidor: formToPayload(formNuevo),
        modalidades: modalidadesSel,
      });
      flash(t("ins.registradoInscrito", { nombre: formNuevo.nombre_completo.trim() }));
      abrirPanel("ninguno");
      await cargar();
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("ins.errorRegistrar"), "error");
    } finally {
      setGuardando(false);
    }
  }

  /** Acepta o rechaza una solicitud (y también reconsidera una rechazada). */
  async function handleModerar(ins: InscripcionData, estado: "aceptada" | "rechazada") {
    try {
      await setEstadoInscripcionAPI(
        ins.id, estado, estado === "rechazada" ? motivos[ins.id] : undefined
      );
      setMotivos((prev) => {
        const resto = { ...prev };
        delete resto[ins.id];
        return resto;
      });
      await cargar();
      flash(
        estado === "aceptada" ? t("camp.solicitudes.aceptada") : t("camp.solicitudes.rechazada"),
        "ok"
      );
    } catch { flash(t("camp.solicitudes.error"), "error"); }
  }

  function abrirEdicion(ins: InscripcionData) {
    setEditandoId(ins.id);
    setEditModalidades(ins.modalidades || []);
    setEditPeso(ins.peso != null ? String(ins.peso) : "");
  }

  async function handleGuardarEdicion(ins: InscripcionData) {
    try {
      await updateInscripcionAPI(ins.id, {
        modalidades: editModalidades,
        peso: editPeso.trim() ? Number(editPeso.replace(",", ".")) : null,
      });
      setEditandoId(null);
      await cargar();
      flash(t("ins.actualizada"));
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("ins.errorActualizar"), "error");
    }
  }

  function handleQuitar(ins: InscripcionData) {
    const nombre = ins.competidor?.nombre_completo || t("ins.esteCompetidor");
    pedirConfirmacion({
      titulo: t("ins.quitar.titulo"),
      mensaje: t("ins.quitar.mensaje", { nombre }),
      tipo: "advertencia",
      confirmLabel: t("comun.quitar"),
      onConfirm: async () => {
        try {
          await deleteInscripcionAPI(ins.id);
          await cargar();
          flash(t("ins.eliminada"));
        } catch { flash(t("ins.errorQuitar"), "error"); }
      },
    });
  }

  // Un competidor con inscripción en CUALQUIER estado deja de ser candidato: el
  // backend solo admite una inscripción por competidor y campeonato.
  const idsInscritos = useMemo(
    () => new Set(inscripciones.map((i) => i.competidor_id)),
    [inscripciones]
  );

  const porEstado = useMemo(() => {
    const grupos: Record<EstadoInscripcion, InscripcionData[]> = {
      pendiente: [], aceptada: [], rechazada: [],
    };
    for (const i of inscripciones) grupos[i.estado]?.push(i);
    return grupos;
  }, [inscripciones]);

  const candidatos = useMemo(() => {
    const termino = busquedaExistente.trim().toLowerCase();
    return competidores
      .filter((c) => c.activo && !idsInscritos.has(c.id))
      .filter((c) =>
        !termino ||
        `${c.nombre_completo} ${c.documento || ""} ${c.club || ""}`.toLowerCase().includes(termino)
      )
      .slice(0, 30);
  }, [competidores, idsInscritos, busquedaExistente]);

  const listaActiva = porEstado[pestana];
  const visibles = useMemo(() => {
    const termino = busquedaLista.trim().toLowerCase();
    if (!termino) return listaActiva;
    return listaActiva.filter((i) =>
      `${i.competidor?.nombre_completo || ""} ${i.competidor?.club || ""} ${(i.modalidades || []).join(" ")}`
        .toLowerCase()
        .includes(termino)
    );
  }, [listaActiva, busquedaLista]);

  const selectorModalidades = (lista: string[], setLista: (l: string[]) => void) => (
    <div>
      <div className="microetiqueta" style={{ marginBottom: 6 }}>
        {t("ins.modalidades")}
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {modalidadesDisponibles.map((m) => {
          const activa = lista.includes(m);
          return (
            <button
              key={m}
              type="button"
              className="btn btn-sm"
              onClick={() => toggleModalidad(lista, setLista, m)}
              style={{
                background: activa ? "var(--gold-bg)" : undefined,
                borderColor: activa ? "var(--gold-border)" : undefined,
                color: activa ? "var(--gold)" : undefined,
                fontSize: "0.8rem",
              }}
              aria-pressed={activa}
            >
              {activa ? "✓ " : ""}{m}
            </button>
          );
        })}
      </div>
    </div>
  );

  /** Ficha del atleta: idéntica en las tres pestañas. */
  const fichaAtleta = (ins: InscripcionData) => {
    const c = ins.competidor;
    const edad = edadDesde(c?.fecha_nacimiento || null);
    return (
      <div style={{ minWidth: 0, flex: "1 1 240px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 800, overflowWrap: "anywhere" }}>
            {c?.nombre_completo || t("ins.eliminadoComp")}
          </span>
          {ins.grupo_cinturon_efectivo && (
            <span className="badge badge-chung">{ins.grupo_cinturon_efectivo}</span>
          )}
          {c?.categoria_especial && (
            <span className="badge badge-gold" title={t("comp.especialTitle")}>
              {t("comp.especialBadge")}
            </span>
          )}
          {(ins.modalidades || []).map((m) => (
            <span key={m} className="badge badge-gray">{m}</span>
          ))}
        </div>
        <div style={{
          color: "var(--text-muted)", fontSize: "0.85rem", marginTop: 4,
          display: "flex", gap: 12, flexWrap: "wrap",
        }}>
          {edad != null && <span>{edad} {t("comp.anios")}</span>}
          {c?.genero && <span>{c.genero === "MASCULINO" ? t("comp.masc") : t("comp.fem")}</span>}
          {ins.peso_efectivo != null && <span>{ins.peso_efectivo} kg</span>}
          {c?.club && <span>{c.club}</span>}
          {(ins.modalidades || []).length === 0 && (
            <span style={{ color: "var(--orange)" }}>{t("ins.sinModalidades")}</span>
          )}
        </div>
        {/* Quién la envió: el admin decide sabiendo de qué club y delegación viene */}
        {ins.solicitante && (
          <div style={{ color: "var(--text-dim)", fontSize: "0.8rem", marginTop: 4 }}>
            {t("camp.solicitudes.solicitadoPor", { nombre: ins.solicitante.nombre })}
            {ins.solicitante.delegacion
              ? ` · ${ins.solicitante.delegacion}${ins.solicitante.pais_delegacion ? ` (${ins.solicitante.pais_delegacion})` : ""}`
              : ""}
            {ins.created_at
              ? ` · ${t("ins.solicitadaEl", { fecha: new Date(ins.created_at).toLocaleDateString() })}`
              : ""}
          </div>
        )}
      </div>
    );
  };

  const vacioPorPestana: Record<EstadoInscripcion, string> = {
    pendiente: t("ins.pendientes.vacio"),
    aceptada: t("ins.vacio"),
    rechazada: t("ins.rechazadas.vacio"),
  };

  return (
    <div className="inscripciones-page">
      <div style={{ marginBottom: 18 }}>
        <button className="btn btn-outline btn-sm" onClick={() => router.push(`/admin/campeonato/${campId}`)}
          style={{ marginBottom: 8 }}>
          {t("ins.volver")}
        </button>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10, flexWrap: "wrap" }}>
          <div>
            <h1 className="display" style={{ fontSize: "1.5rem", overflowWrap: "anywhere" }}>
              {t("camp.inscripciones.boton")} — {campNombre || "..."}
            </h1>
            <p className="text-muted" style={{ fontSize: "0.92rem" }}>
              {t("ins.desc", { n: porEstado.aceptada.length })}
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              className="btn btn-sm"
              onClick={() => router.push(`/admin/campeonato/${campId}/generar-llaves`)}
              style={{ background: "var(--gold-bg)", borderColor: "var(--gold-border)", color: "var(--gold)" }}
            >
              {t("camp.generarLlaves")}
            </button>
          </div>
        </div>
      </div>

      {dialogo}

      {/* Pestañas por estado */}
      <div role="tablist" aria-label={t("ins.tab.aria")}
        style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
        {PESTANAS.map(({ estado, labelKey }) => {
          const activa = pestana === estado;
          const n = porEstado[estado].length;
          // Las pendientes se resaltan aunque no sea la pestaña activa: son las
          // únicas que exigen una decisión del admin.
          const destacar = estado === "pendiente" && n > 0;
          return (
            <button
              key={estado}
              role="tab"
              aria-selected={activa}
              className="btn btn-sm"
              onClick={() => cambiarPestana(estado)}
              style={{
                background: activa ? "var(--gold-bg)" : undefined,
                borderColor: activa || destacar ? "var(--gold-border)" : undefined,
                color: activa || destacar ? "var(--gold)" : undefined,
                fontWeight: activa ? 800 : undefined,
              }}
            >
              {t(labelKey)} ({n})
            </button>
          );
        })}
      </div>

      {pestana === "pendiente" && (
        <p className="text-muted" style={{ fontSize: "0.88rem", marginBottom: 12 }}>
          {t("ins.pendientes.desc")}
        </p>
      )}
      {pestana === "rechazada" && (
        <p className="text-muted" style={{ fontSize: "0.88rem", marginBottom: 12 }}>
          {t("ins.rechazadas.desc")}
        </p>
      )}

      {/* Alta de inscritos: solo en la pestaña del roster aceptado */}
      {pestana === "aceptada" && (
        <>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
            <button
              className={`btn btn-sm ${panel === "existente" ? "btn-primary" : ""}`}
              onClick={() => abrirPanel("existente")}
            >
              {t("ins.inscribirRegistrado")}
            </button>
            <button
              className={`btn btn-sm ${panel === "nuevo" ? "btn-primary" : ""}`}
              onClick={() => abrirPanel("nuevo")}
            >
              {t("comp.nuevo")}
            </button>
            <button
              className={`btn btn-sm ${panel === "excel" ? "btn-primary" : ""}`}
              onClick={() => abrirPanel("excel")}
            >
              {t("comp.importarExcel")}
            </button>
          </div>

          {/* Panel: inscribir existente */}
          {panel === "existente" && (
            <form onSubmit={handleInscribirExistente} className="card animate-slide"
              style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 14 }}>
              <div className="card-title" style={{ marginBottom: 0 }}>{t("ins.panelRegistrado")}</div>
              <input
                className="input"
                placeholder={t("comp.buscar")}
                value={busquedaExistente}
                onChange={(e) => { setBusquedaExistente(e.target.value); setSeleccionado(null); }}
              />
              {seleccionado ? (
                <div style={{
                  padding: "10px 12px", border: "1px solid var(--green-border, rgba(0,196,106,.25))",
                  borderRadius: "var(--radius-sm)", display: "flex", justifyContent: "space-between",
                  alignItems: "center", gap: 8, flexWrap: "wrap",
                }}>
                  <div>
                    <div style={{ fontWeight: 800, color: "var(--green)" }}>{seleccionado.nombre_completo}</div>
                    <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                      {[
                        seleccionado.club,
                        seleccionado.grupo_cinturon,
                        edadDesde(seleccionado.fecha_nacimiento) != null
                          ? `${edadDesde(seleccionado.fecha_nacimiento)} ${t("comp.anios")}` : null,
                        seleccionado.peso != null ? `${seleccionado.peso} kg` : null,
                      ].filter(Boolean).join(" · ") || t("ins.sinDatos")}
                    </div>
                  </div>
                  <button type="button" className="btn btn-sm" onClick={() => setSeleccionado(null)}>
                    {t("ins.cambiar")}
                  </button>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 220, overflowY: "auto" }}>
                  {candidatos.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className="btn"
                      onClick={() => seleccionarCandidato(c)}
                      style={{ justifyContent: "flex-start", textAlign: "left", padding: "8px 10px" }}
                    >
                      <span style={{ fontWeight: 700 }}>{c.nombre_completo}</span>
                      <span style={{ color: "var(--text-muted)", marginLeft: 8, fontSize: "0.85rem" }}>
                        {[c.club, c.grupo_cinturon].filter(Boolean).join(" · ")}
                      </span>
                    </button>
                  ))}
                  {candidatos.length === 0 && (
                    <p style={{ color: "var(--text-dim)", fontSize: "0.88rem", margin: "4px 0" }}>
                      {t("ins.sinCandidatos")}
                    </p>
                  )}
                </div>
              )}
              {selectorModalidades(modalidadesSel, setModalidadesSel)}

              {/* ── Datos viejos: pedir confirmación de peso y cinturón ── */}
              {seleccionado && datosViejos ? (
                <div className="animate-fade" style={{
                  border: "1px solid var(--gold-border)", background: "var(--gold-bg)",
                  borderRadius: "var(--radius-sm)", padding: "12px 14px",
                  display: "flex", flexDirection: "column", gap: 10,
                }}>
                  <div style={{ fontWeight: 800, color: "var(--gold)", fontSize: "0.92rem" }}>
                    {t("ins.datosViejos.titulo", { n: diasDatos ?? 0 })}
                  </div>
                  <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-muted)" }}>
                    {t("ins.datosViejos.desc", {
                      nombre: seleccionado.nombre_completo,
                      fecha: new Date(seleccionado.updated_at || seleccionado.created_at)
                        .toLocaleDateString(),
                    })}
                  </p>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.82rem", color: "var(--text-muted)", fontWeight: 700 }}>
                      {t("form.peso")}
                      <input
                        className="input" type="number" min={10} max={200} step="0.1"
                        value={confPeso}
                        onChange={(e) => setConfPeso(e.target.value)}
                        style={{ width: 130 }}
                      />
                    </label>
                    <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.82rem", color: "var(--text-muted)", fontWeight: 700 }}>
                      {t("form.cinturon")}
                      <select
                        className="input"
                        value={confCinturon}
                        onChange={(e) => setConfCinturon(e.target.value)}
                        style={{ minWidth: 160 }}
                      >
                        <option value="">{t("form.sinDefinir")}</option>
                        {CINTURONES.map((c) => (
                          <option key={c.nombre} value={c.nombre}>{c.nombre}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button type="button" className="btn btn-primary"
                      disabled={modalidadesSel.length === 0 || guardando}
                      onClick={() => inscribirSeleccionado(true)}>
                      {guardando ? t("ins.inscribiendo") : t("ins.actualizarInscribir")}
                    </button>
                    <button type="button" className="btn"
                      disabled={modalidadesSel.length === 0 || guardando}
                      onClick={() => inscribirSeleccionado(false)}>
                      {t("ins.continuarMismos")}
                    </button>
                    <button type="button" className="btn" onClick={() => abrirPanel("ninguno")}>{t("comun.cancelar")}</button>
                  </div>
                </div>
              ) : (
                <>
                  {seleccionado && diasDatos != null && (
                    <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--green)" }}>
                      {t("ins.datosAlDia", { n: diasDatos })}
                    </p>
                  )}
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.88rem", color: "var(--text-muted)", flexWrap: "wrap" }}>
                    {t("ins.pesoInscribir")}
                    <input
                      className="input"
                      type="number"
                      min={10}
                      max={200}
                      step="0.1"
                      value={pesoInscripcion}
                      onChange={(e) => setPesoInscripcion(e.target.value)}
                      placeholder={seleccionado?.peso != null ? t("ins.pesoActual", { peso: seleccionado.peso }) : "62.5"}
                      style={{ width: 140 }}
                    />
                  </label>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button type="submit" className="btn btn-primary"
                      disabled={!seleccionado || modalidadesSel.length === 0 || guardando}>
                      {guardando ? t("ins.inscribiendo") : t("ins.inscribir")}
                    </button>
                    <button type="button" className="btn" onClick={() => abrirPanel("ninguno")}>{t("comun.cancelar")}</button>
                  </div>
                </>
              )}
            </form>
          )}

          {/* Panel: nuevo competidor + inscripción */}
          {panel === "nuevo" && (
            <form onSubmit={handleInscribirNuevo} className="card animate-slide"
              style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 14 }}>
              <div className="card-title" style={{ marginBottom: 0 }}>{t("ins.panelNuevo")}</div>
              <CompetidorFormFields value={formNuevo} onChange={setFormNuevo} clubes={clubes} />
              {selectorModalidades(modalidadesSel, setModalidadesSel)}
              <div style={{ display: "flex", gap: 8 }}>
                <button type="submit" className="btn btn-primary"
                  disabled={!formNuevo.nombre_completo.trim() || modalidadesSel.length === 0 || guardando}>
                  {guardando ? t("comp.guardando") : t("ins.registrarInscribir")}
                </button>
                <button type="button" className="btn" onClick={() => abrirPanel("ninguno")}>{t("comun.cancelar")}</button>
              </div>
            </form>
          )}

          {/* Panel: importar Excel */}
          {panel === "excel" && (
            <div style={{ marginBottom: 14 }}>
              <ImportarExcelPanel
                campeonatoId={campId}
                modalidadesDefault={modalidadesSel.length ? modalidadesSel : ["COMBATE"]}
                onImportado={cargar}
                onMensaje={flash}
              />
            </div>
          )}
        </>
      )}

      {/* Buscador de la pestaña activa */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
        <input
          className="input"
          placeholder={pestana === "aceptada" ? t("ins.filtrar") : t("ins.filtrarEstado")}
          value={busquedaLista}
          onChange={(e) => setBusquedaLista(e.target.value)}
          style={{ flex: "1 1 220px", maxWidth: 340 }}
        />
        <span style={{ fontSize: "0.875rem", color: "var(--text-dim)" }}>
          {t("comp.deTotal", { n: visibles.length, total: listaActiva.length })}
        </span>
      </div>

      {listaActiva.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 28, color: "var(--text-dim)" }}>
          {vacioPorPestana[pestana]}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {visibles.map((ins) => {
            const editando = editandoId === ins.id;
            return (
              <div key={ins.id} className="card" style={{
                padding: "12px 14px",
                borderColor: pestana === "pendiente" ? "var(--gold-border)" : undefined,
              }}>
                <div className="ins-row">
                  {fichaAtleta(ins)}

                  {/* Acciones según la pestaña */}
                  {pestana === "aceptada" && (
                    <div style={{ display: "flex", gap: 6, flexShrink: 0, flexWrap: "wrap" }}>
                      <button className="btn btn-sm" onClick={() => (editando ? setEditandoId(null) : abrirEdicion(ins))}>
                        {editando ? t("comun.cerrar") : t("comun.editar")}
                      </button>
                      <button className="btn btn-danger btn-sm" onClick={() => handleQuitar(ins)}>
                        {t("comun.quitar")}
                      </button>
                    </div>
                  )}
                  {pestana === "rechazada" && (
                    <div style={{ display: "flex", gap: 6, flexShrink: 0, flexWrap: "wrap" }}>
                      <button className="btn btn-primary btn-sm" onClick={() => handleModerar(ins, "aceptada")}>
                        {t("ins.reconsiderar")}
                      </button>
                      <button className="btn btn-danger btn-sm" onClick={() => handleQuitar(ins)}>
                        {t("comun.quitar")}
                      </button>
                    </div>
                  )}
                </div>

                {/* Pendiente: motivo + aceptar / rechazar */}
                {pestana === "pendiente" && (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 10 }}>
                    <input
                      className="input"
                      placeholder={t("camp.solicitudes.motivoPh")}
                      value={motivos[ins.id] || ""}
                      maxLength={300}
                      onChange={(e) => setMotivos({ ...motivos, [ins.id]: e.target.value.slice(0, 300) })}
                      style={{ flex: "1 1 180px", minWidth: 0 }}
                    />
                    <button className="btn btn-primary btn-sm" onClick={() => handleModerar(ins, "aceptada")}>
                      {t("camp.solicitudes.aceptar")}
                    </button>
                    <button className="btn btn-danger btn-sm" onClick={() => handleModerar(ins, "rechazada")}>
                      {t("camp.solicitudes.rechazar")}
                    </button>
                  </div>
                )}

                {/* Rechazada: por qué se denegó */}
                {pestana === "rechazada" && (
                  <p style={{ margin: "8px 0 0", fontSize: "0.85rem", color: "var(--text-muted)" }}>
                    {ins.motivo_rechazo
                      ? t("ins.rechazadas.motivo", { motivo: ins.motivo_rechazo })
                      : t("ins.rechazadas.sinMotivo")}
                  </p>
                )}

                {/* Aceptada: edición de modalidades y peso */}
                {editando && (
                  <div className="animate-fade" style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 10 }}>
                    {selectorModalidades(editModalidades, setEditModalidades)}
                    <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.88rem", color: "var(--text-muted)", flexWrap: "wrap" }}>
                      {t("ins.pesoInscripcion")}
                      <input
                        className="input"
                        type="number"
                        min={10}
                        max={200}
                        step="0.1"
                        value={editPeso}
                        onChange={(e) => setEditPeso(e.target.value)}
                        placeholder={ins.competidor?.peso != null
                          ? t("ins.pesoActualAtleta", { peso: ins.competidor.peso })
                          : t("ins.sinDato")}
                        style={{ width: 150 }}
                      />
                    </label>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button className="btn btn-primary btn-sm" onClick={() => handleGuardarEdicion(ins)}>
                        {t("comun.guardar")}
                      </button>
                      <button className="btn btn-sm" onClick={() => setEditandoId(null)}>{t("comun.cancelar")}</button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {visibles.length === 0 && (
            <div className="card" style={{ textAlign: "center", padding: 20, color: "var(--text-dim)" }}>
              {t("comp.sinCoincidencias")}
            </div>
          )}
        </div>
      )}

      <style>{`
        .inscripciones-page {
          max-width: 1100px; margin: 0 auto; padding: 24px clamp(16px, 4vw, 40px);
        }
        .ins-row {
          display: flex; justify-content: space-between; align-items: center;
          gap: 10px; flex-wrap: wrap;
        }
        @media (max-width: 560px) {
          .inscripciones-page { padding: 14px; }
        }
      `}</style>
    </div>
  );
}
