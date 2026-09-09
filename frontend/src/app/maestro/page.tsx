"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  maestroAlumnosAPI,
  maestroCampeonatosAPI,
  maestroInscribirAPI,
  maestroMisInscripcionesAPI,
  maestroReenviarAPI,
  misTatamisAPI,
  type AlumnoMaestro,
  type ClubMaestro,
  type InscripcionData,
  type MaestroCampeonato,
  type UserData,
} from "@/lib/api";
import CompetidorFormFields, {
  COMPETIDOR_FORM_VACIO,
  competidorToForm,
  formToPayload,
  type CompetidorFormState,
} from "@/components/CompetidorFormFields";
import { Cargando } from "@/components/Cargando";
import { useI18n, type ClaveTexto } from "@/lib/i18n";
import { aviso } from "@/lib/toast";

// Modalidades canónicas (viajan al servidor tal cual, sin traducir).
const MODALIDADES = [
  "COMBATE", "FIGURA A MANOS LIBRES", "FIGURA CON ARMAS", "DEFENSA PERSONAL",
];

interface MiTatami {
  id: number;
  numero: number;
  campeonato_nombre?: string;
  mi_rol: string;
}

export default function MaestroPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [user, setUser] = useState<UserData | null>(null);
  const [camps, setCamps] = useState<MaestroCampeonato[]>([]);
  const [misInscripciones, setMisInscripciones] = useState<InscripcionData[]>([]);
  const [misTatamis, setMisTatamis] = useState<MiTatami[]>([]);
  const [cargando, setCargando] = useState(true);

  // Formulario de inscripción por campeonato (solo uno abierto a la vez)
  const [campSel, setCampSel] = useState<number | null>(null);
  const [form, setForm] = useState<CompetidorFormState>(COMPETIDOR_FORM_VACIO);
  const [modalidades, setModalidades] = useState<string[]>(["COMBATE"]);
  const [guardando, setGuardando] = useState(false);

  // Los alumnos que YA tiene fichados. A partir del segundo campeonato se
  // elige de aquí en vez de rellenar el formulario entero: el nombre, la
  // fecha, el género, el documento y el cinturón no cambian nunca.
  const [alumnos, setAlumnos] = useState<AlumnoMaestro[]>([]);
  const [alumnoUid, setAlumnoUid] = useState<string | null>(null);
  const [buscaAlumno, setBuscaAlumno] = useState("");
  const [cargandoAlumnos, setCargandoAlumnos] = useState(false);

  // Re-envío de inscripción rechazada
  const [reenvioId, setReenvioId] = useState<number | null>(null);
  const [reenvioForm, setReenvioForm] = useState<CompetidorFormState>(COMPETIDOR_FORM_VACIO);
  const [reenvioModalidades, setReenvioModalidades] = useState<string[]>(["COMBATE"]);
  const [reenviando, setReenviando] = useState(false);

  // Los dojangs del maestro, cada uno con su delegación. Con respaldo en los
  // campos sueltos: una sesión guardada antes de que existiera la lista solo
  // trae `club` + `delegacion` + `pais_delegacion`.
  const misClubes: ClubMaestro[] = user?.clubes?.length
    ? user.clubes
    : (user?.club
        ? [{ nombre: user.club, ciudad: user.delegacion, pais: user.pais_delegacion }]
        : []);
  const nombresClubes = misClubes.map((c) => c.nombre);
  const club = nombresClubes[0] || "";

  const cargar = useCallback(async (puedeJuzgar: boolean) => {
    try {
      const [cs, mis] = await Promise.all([
        maestroCampeonatosAPI(),
        maestroMisInscripcionesAPI(),
      ]);
      setCamps(cs);
      setMisInscripciones(mis);
      if (puedeJuzgar) {
        misTatamisAPI().then(setMisTatamis).catch(() => {});
      }
    } catch { /* */ } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    const saved = localStorage.getItem("dinamyt_user");
    if (!saved) { router.replace("/login"); return; }
    const u = JSON.parse(saved) as UserData;
    if (u.rol !== "maestro") { router.replace("/login"); return; }
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setUser(u);
      void cargar(!!u.puede_juzgar);
    });
    return () => { cancelled = true; };
  }, [cargar, router]);

  /** Avisa del resultado de una acción con la nube flotante (ver lib/toast). */
  function flash(texto: string, tipo: "ok" | "error" = "ok") {
    aviso(texto, tipo);
  }

  async function abrirForm(campId: number) {
    setCampSel(campId);
    // Arranca en el club principal: con un solo dojang es el único, y con
    // varios es el que el desplegable enseña ya elegido.
    setForm({ ...COMPETIDOR_FORM_VACIO, club });
    setModalidades(["COMBATE"]);
    setAlumnoUid(null);
    setBuscaAlumno("");
    setAlumnos([]);
    setCargandoAlumnos(true);
    try {
      // Con el campeonato: cada alumno dice si ya está inscrito ahí, para no
      // ofrecerlo dos veces.
      setAlumnos(await maestroAlumnosAPI(campId));
    } catch {
      // Sin lista se sigue pudiendo teclear, que es como funcionaba antes.
    } finally {
      setCargandoAlumnos(false);
    }
  }

  /** Elegir a un alumno ya fichado: su ficha rellena el formulario. */
  function elegirAlumno(a: AlumnoMaestro) {
    setAlumnoUid(a.uid);
    // El club guardado se traduce al nombre TAL Y COMO lo tiene el maestro:
    // el desplegable ofrece esos y solo esos (ver `clubesPropios`).
    const suyo = nombresClubes.find(
      (c) => c.toUpperCase() === (a.club || "").toUpperCase()
    );
    // Y el peso se deja EN BLANCO a propósito: es lo único de la ficha que
    // cambia de un campeonato a otro, y el del año pasado engañaría.
    setForm({ ...competidorToForm(a), peso: "", club: suyo || club });
  }

  /** Volver al formulario en blanco: el que compite por primera vez. */
  function nuevoAlumno() {
    setAlumnoUid(null);
    setBuscaAlumno("");
    setForm({ ...COMPETIDOR_FORM_VACIO, club });
  }

  function toggleModalidad(m: string) {
    setModalidades((prev) =>
      prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]
    );
  }

  async function enviar(e: React.FormEvent, campId: number) {
    e.preventDefault();
    if (guardando) return;
    if (!form.nombre_completo.trim()) return;
    setGuardando(true);
    try {
      await maestroInscribirAPI(campId, {
        // Con uid se reutiliza la ficha; sin él se crea, que es como se da de
        // alta a quien compite por primera vez.
        competidor_uid: alumnoUid,
        competidor: formToPayload(form),
        modalidades,
      });
      setCampSel(null);
      await cargar(!!user?.puede_juzgar);
      flash(t("maestro.solicitudEnviada"), "ok");
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("maestro.errorEnviar"), "error");
    } finally {
      setGuardando(false);
    }
  }

  function abrirReenvio(i: InscripcionData) {
    setReenvioId(i.id);
    if (i.competidor) {
      const previo = competidorToForm(i.competidor);
      // El club guardado tiene que seguir siendo uno de los suyos: si el admin
      // le quitó ese dojang entretanto, el desplegable no tendría esa opción y
      // el campo se vería vacío.
      const propio = nombresClubes.some((c) => c === previo.club);
      setReenvioForm({ ...previo, club: propio ? previo.club : club });
    } else {
      setReenvioForm({ ...COMPETIDOR_FORM_VACIO, club });
    }
    setReenvioModalidades(i.modalidades?.length ? [...i.modalidades] : ["COMBATE"]);
  }

  async function enviarReenvio(e: React.FormEvent) {
    e.preventDefault();
    if (reenviando || !reenvioId) return;
    if (!reenvioForm.nombre_completo.trim()) return;
    setReenviando(true);
    try {
      await maestroReenviarAPI(reenvioId, {
        competidor: formToPayload(reenvioForm),
        modalidades: reenvioModalidades,
      });
      setReenvioId(null);
      await cargar(!!user?.puede_juzgar);
      flash(t("maestro.reenvioOk"), "ok");
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      flash(m || t("maestro.errorEnviar"), "error");
    } finally {
      setReenviando(false);
    }
  }

  function toggleReenvioModalidad(m: string) {
    setReenvioModalidades((prev) =>
      prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]
    );
  }

  const estadoInscBadge = (estado: InscripcionData["estado"]) => {
    const color =
      estado === "aceptada" ? "var(--green)"
      : estado === "rechazada" ? "var(--red-alert)"
      : "var(--gold)";
    const bg =
      estado === "aceptada" ? "var(--green-bg)"
      : estado === "rechazada" ? "rgba(255,68,68,0.10)"
      : "var(--gold-bg)";
    return (
      <span className="badge" style={{ background: bg, color, border: `1px solid ${color}` }}>
        {t(`insc.estado.${estado}` as ClaveTexto)}
      </span>
    );
  };

  /**
   * Elegir al alumno en vez de teclearlo.
   *
   * Es la mitad visible del arreglo: hasta ahora el formulario arrancaba
   * siempre en blanco, así que el nombre, la fecha de nacimiento, el género,
   * el documento y el cinturón —que no cambian nunca— costaban exactamente lo
   * mismo de escribir que el peso, que sí cambia. Multiplicado por cuarenta
   * alumnos y por cada campeonato.
   */
  function selectorAlumnos() {
    if (cargandoAlumnos) {
      return <Cargando mensaje={t("maestro.cargandoAlumnos")} encajado />;
    }
    if (!alumnos.length) {
      return <div className="alumnos-aviso">{t("maestro.sinAlumnos")}</div>;
    }

    const elegido = alumnos.find((a) => a.uid === alumnoUid) || null;
    if (elegido) {
      return (
        <div className="alumno-elegido">
          <div style={{ minWidth: 0 }}>
            <div className="microetiqueta">{t("maestro.fichaDeSiempre")}</div>
            <div style={{ fontWeight: 700, overflowWrap: "anywhere" }}>
              {elegido.nombre_completo}
            </div>
            <div className="alumnos-datos">
              {[elegido.documento, elegido.cinturon, elegido.club]
                .filter(Boolean).join(" · ")}
            </div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={nuevoAlumno}>
            {t("maestro.elegirOtro")}
          </button>
        </div>
      );
    }

    const busca = buscaAlumno.trim().toUpperCase();
    const filtrados = busca
      ? alumnos.filter(
          (a) =>
            (a.nombre_completo || "").toUpperCase().includes(busca) ||
            (a.documento || "").includes(busca)
        )
      : alumnos;

    return (
      <div className="alumnos-lista">
        <div className="microetiqueta">{t("maestro.tusAlumnos")}</div>
        <input
          className="input"
          value={buscaAlumno}
          onChange={(e) => setBuscaAlumno(e.target.value)}
          placeholder={t("maestro.buscarAlumno")}
        />
        <div className="alumnos-scroll">
          {filtrados.length === 0 ? (
            <p className="muted" style={{ margin: 0, padding: "6px 2px", fontSize: "0.85rem" }}>
              {t("maestro.sinCoincidencias")}
            </p>
          ) : (
            filtrados.map((a) => (
              <button
                key={a.uid}
                type="button"
                className="alumnos-fila"
                /* Ya inscrito: la inscripción es única por (campeonato,
                   competidor), así que ofrecerlo sería ofrecer un error. */
                disabled={a.inscrito}
                onClick={() => elegirAlumno(a)}
              >
                <span style={{ fontWeight: 700, overflowWrap: "anywhere" }}>
                  {a.nombre_completo}
                </span>
                <span className="alumnos-datos">
                  {[a.documento, a.cinturon].filter(Boolean).join(" · ")}
                </span>
                {a.inscrito && (
                  <span className="badge badge-gray">{t("maestro.yaInscrito")}</span>
                )}
              </button>
            ))
          )}
        </div>
        <div className="alumnos-datos">{t("maestro.primeraVez")} ↓</div>
      </div>
    );
  }

  if (!user) return null;

  /** La ficha del dojang elegido en un formulario (para enseñar SU delegación). */
  const dojangDe = (nombre: string) =>
    misClubes.find((c) => c.nombre === nombre) || misClubes[0];

  /**
   * Origen del alumno: el dojang elegido y la delegación DE ESE dojang. Se
   * enseña dentro del formulario porque es el dato que cambia al elegir otro
   * club — un maestro con uno en Cali y otro en Popayán inscribe en una u otra
   * delegación según cuál marque.
   */
  const infoOrigen = (nombreClub: string) => {
    const dojang = dojangDe(nombreClub);
    if (!dojang) return null;
    return (
      <div style={{
        display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center",
        fontSize: "0.82rem", color: "var(--text-muted)",
        padding: "8px 12px", borderRadius: "var(--radius-sm)",
        background: "var(--bg-elevated)", border: "1px solid var(--border)",
      }}>
        <span>
          {t("maestro.tuClub")}:{" "}
          <strong style={{ color: "var(--text)" }}>{dojang.nombre}</strong>
        </span>
        {dojang.ciudad && (
          <span>· {t("maestro.tuDelegacion")}: <strong style={{ color: "var(--text)" }}>
            {dojang.ciudad}{dojang.pais ? ` (${dojang.pais})` : ""}
          </strong></span>
        )}
      </div>
    );
  };

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "20px" }}>
      {/* Header */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 20, paddingBottom: 16, borderBottom: "1px solid var(--border)", flexWrap: "wrap", gap: 10,
      }}>
        {/* Antetitulo + titulo, como en Membresias. La marca la pone la barra. */}
        {/* Sin antetitulo: la barra ya dice donde estamos. */}
        <div>
          <h1 className="display" style={{ fontSize: "1.5rem" }}>
            {t("maestro.panel")}
          </h1>
          <p className="muted" style={{ fontSize: "0.85rem", marginTop: 2 }}>
            {user.nombre}
          </p>
        </div>
        {club && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
            <div style={{
              padding: "6px 14px", borderRadius: "var(--radius-sm)",
              border: "1px solid var(--gold-border)", background: "var(--gold-bg)",
              color: "var(--gold)", fontWeight: 700,
            }}>
              {misClubes.length > 1 ? t("maestro.tusClubes") : t("maestro.tuClub")}
            </div>
            {/* Cada dojang con SU delegación: es el dato que distingue a uno de
                otro cuando están en ciudades distintas. */}
            {misClubes.map((c) => (
              <div key={c.nombre} style={{
                padding: "4px 12px", borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)", background: "var(--bg-elevated)",
                color: "var(--text-muted)", fontWeight: 600, fontSize: "0.85rem",
              }}>
                {c.nombre}
                {c.ciudad ? ` · ${c.ciudad}${c.pais ? ` (${c.pais})` : ""}` : ""}
              </div>
            ))}
          </div>
        )}
      </div>


      {!club && (
        <div className="card" style={{
          marginBottom: 16, borderColor: "var(--red-alert)",
          background: "rgba(232,0,42,0.06)", color: "var(--text-muted)",
        }}>
          {t("maestro.sinClub")}
        </div>
      )}

      {/* Campeonatos */}
      <div className="card-title">{t("maestro.campeonatos")}</div>
      {cargando ? (
        /* Era una tarjeta idéntica a la de «no hay campeonatos»: la misma caja,
           el mismo relleno, el mismo gris. Cambiaba solo la frase, así que la
           espera y la respuesta se confundían. */
        <Cargando mensaje={t("maestro.cargando")} encajado />
      ) : camps.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 28, color: "var(--text-dim)" }}>
          {t("maestro.sinCampeonatos")}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 24 }}>
          {camps.map((c) => {
            const suyas = misInscripciones.filter((i) => i.campeonato_id === c.id);
            return (
              <div key={c.id} className="card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <div style={{ minWidth: 0 }}>
                    <span style={{ fontWeight: 700, fontSize: "1.05rem", overflowWrap: "anywhere" }}>{c.nombre}</span>
                    <span className="badge badge-gray" style={{ marginLeft: 8 }}>
                      {t(`camp.estado.${c.estado}` as ClaveTexto)}
                    </span>
                    {(c.ciudad || c.pais || c.fecha_inicio) && (
                      <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: 2 }}>
                        {[c.fecha_inicio, [c.ciudad, c.pais].filter(Boolean).join(", ")].filter(Boolean).join(" · ")}
                      </div>
                    )}
                  </div>
                  {c.puede_inscribir ? (
                    <button className="btn btn-primary btn-sm"
                      disabled={!club}
                      onClick={() => { if (campSel === c.id) setCampSel(null); else void abrirForm(c.id); }}>
                      {t("maestro.inscribirAlumno")}
                    </button>
                  ) : (
                    <span className="badge badge-gray">{t("maestro.cerrado")}</span>
                  )}
                </div>

                {!c.puede_inscribir && (
                  <p style={{ color: "var(--text-dim)", fontSize: "0.82rem", marginTop: 8, marginBottom: 0 }}>
                    {t("maestro.noPreparacion")}
                  </p>
                )}

                {/* Formulario de inscripción */}
                {campSel === c.id && c.puede_inscribir && (
                  <form onSubmit={(e) => enviar(e, c.id)} className="card animate-slide"
                    style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 12, borderColor: "var(--gold-border)" }}>
                    {infoOrigen(form.club)}
                    {selectorAlumnos()}
                    {alumnoUid && (
                      <p className="alumnos-aviso" style={{ margin: 0 }}>
                        {t("maestro.soloElPeso")}
                      </p>
                    )}
                    <CompetidorFormFields value={form} onChange={setForm} clubesPropios={nombresClubes} />
                    <div>
                      <div className="microetiqueta" style={{ marginBottom: 6 }}>
                        {t("res.modCombate")} / {t("res.modFiguras")}
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                        {MODALIDADES.map((m) => (
                          <label key={m} style={{
                            display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
                            padding: "6px 10px", borderRadius: "var(--radius-sm)",
                            border: `1px solid ${modalidades.includes(m) ? "var(--gold-border)" : "var(--border)"}`,
                            background: modalidades.includes(m) ? "var(--gold-bg)" : "transparent",
                            fontSize: "0.82rem", fontWeight: 700,
                          }}>
                            <input type="checkbox" checked={modalidades.includes(m)}
                              onChange={() => toggleModalidad(m)}
                              style={{ accentColor: "var(--gold)" }} />
                            {m}
                          </label>
                        ))}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button type="submit" className="btn btn-primary" disabled={guardando}>
                        {guardando ? t("maestro.enviando") : t("maestro.enviarSolicitud")}
                      </button>
                      <button type="button" className="btn" onClick={() => setCampSel(null)}>
                        {t("comun.cancelar")}
                      </button>
                    </div>
                  </form>
                )}

                {/* Mis solicitudes en este campeonato */}
                <div style={{ marginTop: 12 }}>
                  <div className="microetiqueta" style={{ marginBottom: 6 }}>
                    {t("maestro.misSolicitudes")}
                  </div>
                  {suyas.length === 0 ? (
                    <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", margin: 0 }}>
                      {t("maestro.sinSolicitudes")}
                    </p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {suyas.map((i) => (
                        <div key={i.id} style={{
                          padding: "6px 10px",
                          border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                        }}>
                          <div style={{
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                            gap: 8, flexWrap: "wrap",
                          }}>
                            <span style={{ fontWeight: 700, overflowWrap: "anywhere" }}>
                              {i.competidor?.nombre_completo || "—"}
                              {(i.modalidades?.length || 0) > 0 && (
                                <span style={{ color: "var(--text-dim)", fontWeight: 500, marginLeft: 8, fontSize: "0.82rem" }}>
                                  {i.modalidades.join(", ")}
                                </span>
                              )}
                            </span>
                            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              {i.estado === "rechazada" && i.motivo_rechazo && (
                                <span style={{ color: "var(--text-dim)", fontSize: "0.8rem" }}>
                                  {t("insc.motivo")}: {i.motivo_rechazo}
                                </span>
                              )}
                              {estadoInscBadge(i.estado)}
                            </span>
                          </div>
                          {/* Botón re-enviar para rechazadas */}
                          {i.estado === "rechazada" && c.puede_inscribir && (
                            <div style={{ marginTop: 8 }}>
                              {reenvioId === i.id ? (
                                <form onSubmit={enviarReenvio} className="card animate-slide"
                                  style={{ display: "flex", flexDirection: "column", gap: 12, borderColor: "var(--red-alert)", marginTop: 4 }}>
                                  {infoOrigen(reenvioForm.club)}
                                  <CompetidorFormFields value={reenvioForm} onChange={setReenvioForm} clubesPropios={nombresClubes} />
                                  <div>
                                    <div className="microetiqueta" style={{ marginBottom: 6 }}>
                                      {t("res.modCombate")} / {t("res.modFiguras")}
                                    </div>
                                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                                      {MODALIDADES.map((m) => (
                                        <label key={m} style={{
                                          display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
                                          padding: "6px 10px", borderRadius: "var(--radius-sm)",
                                          border: `1px solid ${reenvioModalidades.includes(m) ? "var(--gold-border)" : "var(--border)"}`,
                                          background: reenvioModalidades.includes(m) ? "var(--gold-bg)" : "transparent",
                                          fontSize: "0.82rem", fontWeight: 700,
                                        }}>
                                          <input type="checkbox" checked={reenvioModalidades.includes(m)}
                                            onChange={() => toggleReenvioModalidad(m)}
                                            style={{ accentColor: "var(--gold)" }} />
                                          {m}
                                        </label>
                                      ))}
                                    </div>
                                  </div>
                                  <div style={{ display: "flex", gap: 8 }}>
                                    <button type="submit" className="btn btn-primary" disabled={reenviando}>
                                      {reenviando ? t("maestro.reenviando") : t("maestro.enviarSolicitud")}
                                    </button>
                                    <button type="button" className="btn" onClick={() => setReenvioId(null)}>
                                      {t("comun.cancelar")}
                                    </button>
                                  </div>
                                </form>
                              ) : (
                                <button className="btn btn-sm" style={{
                                  color: "var(--red-alert)", borderColor: "var(--red-alert)",
                                  fontSize: "0.82rem",
                                }} onClick={() => abrirReenvio(i)}>
                                  {t("maestro.reenviar")}
                                </button>
                              )}
                            </div>
                          )}
                          {/* Mensaje para pendientes */}
                          {i.estado === "pendiente" && (
                            <div style={{ marginTop: 6, fontSize: "0.8rem", color: "var(--text-dim)", fontStyle: "italic" }}>
                              {t("maestro.noEditar")}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Mis tatamis (si el maestro también juzga) */}
      {user.puede_juzgar && misTatamis.length > 0 && (
        <>
          <div className="card-title">{t("maestro.misTatamis")}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
            {misTatamis.map((tat) => (
              <div key={tat.id} className="card" style={{ cursor: "pointer" }}
                onClick={() => router.push(`/tatami/${tat.id}?rol=${tat.mi_rol}`)}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <div>
                    <span style={{ fontWeight: 700, fontSize: "1.05rem" }}>{t("juez.tatami")} {tat.numero}</span>
                    {tat.campeonato_nombre && (
                      <div style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>{tat.campeonato_nombre}</div>
                    )}
                  </div>
                  <button className="btn btn-primary" style={{ flexShrink: 0 }}
                    onClick={(e) => { e.stopPropagation(); router.push(`/tatami/${tat.id}?rol=${tat.mi_rol}`); }}>
                    {t("juez.entrar")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <style>{`
        /* ── Elegir alumno (F5-bis) ─────────────────────────────────────
           Clases propias, sin tocar nada compartido: lo que no está capado
           gana a «@layer components» y un retoque aquí se llevaría por
           delante botones de otras pantallas. */
        .alumnos-lista { display: flex; flex-direction: column; gap: 8px; }
        .alumnos-scroll {
          display: flex; flex-direction: column; gap: 6px;
          max-height: 220px; overflow-y: auto;
          padding: 4px; border: 1px solid var(--border);
          border-radius: var(--radius-sm); background: var(--bg-elevated);
        }
        .alumnos-fila {
          display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
          width: 100%; text-align: left; cursor: pointer;
          padding: 8px 10px; border-radius: var(--radius-sm);
          border: 1px solid var(--border); background: var(--bg);
          color: var(--text); font: inherit;
        }
        .alumnos-fila:hover:not(:disabled) {
          border-color: var(--gold-border); background: var(--gold-bg);
        }
        .alumnos-fila:disabled { opacity: 0.55; cursor: not-allowed; }
        .alumnos-datos {
          font-size: 0.82rem; color: var(--text-muted); overflow-wrap: anywhere;
        }
        .alumno-elegido {
          display: flex; align-items: center; justify-content: space-between;
          gap: 10px; flex-wrap: wrap;
          padding: 10px 12px; border-radius: var(--radius-sm);
          border: 1px solid var(--gold-border); background: var(--gold-bg);
        }
        .alumnos-aviso {
          font-size: 0.85rem; color: var(--text-muted);
          padding: 8px 12px; border-radius: var(--radius-sm);
          background: var(--bg-elevated); border: 1px solid var(--border);
        }
      `}</style>
    </div>
  );
}
