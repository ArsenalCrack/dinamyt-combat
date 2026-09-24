"use client";

// ═════════════════════════════════════════════════════════════════════════════
// LOS CLUBES QUE INSCRIBEN EN ESTE CAMPEONATO (F5 de PLAN-CAMPEONATOS)
//
// Hasta F5, que un maestro inscribiera aquí era un efecto colateral de quién
// había creado su cuenta. Ahora es una decisión del administrador, campeonato a
// campeonato: invita a un CLUB, y sus maestros lo ven e inscriben.
//
// Dos cosas que la pantalla tiene que decir, porque no se ven:
//
//   · De dónde salen los clubes. Del directorio de DINAMYT si hay conexión; si
//     no —el modo local, o el puente apagado—, se dice, y se invita por
//     nombre. Un puente apagado que no se nota es la avería que más se ha
//     pagado en esta app (§1.6-bis del plan).
//   · Qué abre cada invitación. La que viene del directorio deja entrar a los
//     maestros de ese club vengan de donde vengan; la que es solo un nombre
//     queda anotada, pero no abre la puerta a nadie de fuera.
// ═════════════════════════════════════════════════════════════════════════════

import { useCallback, useEffect, useState } from "react";
import {
  buscarClubesAPI,
  invitarClubAPI,
  listInvitacionesAPI,
  retirarInvitacionAPI,
  type ClubDelDirectorio,
  type EstadoInvitacion,
  type InvitacionClub,
} from "@/lib/api";
import { useI18n, type ClaveTexto } from "@/lib/i18n";
import { aviso } from "@/lib/toast";

const COLOR: Record<EstadoInvitacion, string> = {
  invitado: "var(--gold)",
  aceptado: "var(--green)",
  retirado: "var(--text-dim)",
};

function errorDe(err: unknown): string | undefined {
  return (err as { response?: { data?: { error?: string } } }).response?.data?.error;
}

export default function ClubesInvitados({ campId }: { campId: number }) {
  const { t } = useI18n();
  const [invitaciones, setInvitaciones] = useState<InvitacionClub[]>([]);
  const [texto, setTexto] = useState("");
  const [resultados, setResultados] = useState<ClubDelDirectorio[]>([]);
  const [disponible, setDisponible] = useState<boolean | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setInvitaciones(await listInvitacionesAPI(campId));
    } catch {
      // La lista es de apoyo: si falla, el resto de la ficha sigue.
    }
  }, [campId]);

  const buscar = useCallback(async (q: string) => {
    try {
      const r = await buscarClubesAPI(campId, q);
      setDisponible(r.disponible);
      setResultados(r.clubes);
    } catch {
      setResultados([]);
    }
  }, [campId]);

  useEffect(() => {
    let cancelado = false;
    queueMicrotask(() => { if (!cancelado) void cargar(); });
    return () => { cancelado = true; };
  }, [cargar]);

  // Se busca mientras se escribe, con una pausa: el directorio está al otro
  // lado de la red y cada tecla sería una petición.
  useEffect(() => {
    const espera = setTimeout(() => { void buscar(texto.trim()); }, 300);
    return () => clearTimeout(espera);
  }, [texto, buscar]);

  async function invitar(club: { org_id?: string | null; nombre: string; ciudad?: string | null }) {
    setOcupado(true);
    try {
      const r = await invitarClubAPI(campId, club);
      aviso(r.message, "ok");
      await Promise.all([cargar(), buscar(texto.trim())]);
    } catch (err) {
      aviso(errorDe(err) || t("inv.errorInvitar"), "error");
    } finally {
      setOcupado(false);
    }
  }

  async function retirar(inv: InvitacionClub) {
    setOcupado(true);
    try {
      const r = await retirarInvitacionAPI(campId, inv.id);
      aviso(r.message, "ok");
      await Promise.all([cargar(), buscar(texto.trim())]);
    } catch (err) {
      aviso(errorDe(err) || t("inv.errorRetirar"), "error");
    } finally {
      setOcupado(false);
    }
  }

  const escritoAMano = texto.trim();
  const yaEnResultados = resultados.some(
    (c) => c.nombre.toLowerCase() === escritoAMano.toLowerCase(),
  );

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-title">{t("inv.titulo")}</div>
      <p className="text-muted" style={{ fontSize: "0.86rem", margin: "0 0 12px" }}>
        {t("inv.ayuda")}
      </p>

      {/* ── Los invitados ── */}
      {invitaciones.length === 0 ? (
        <p className="text-muted" style={{ fontSize: "0.86rem", margin: "0 0 12px" }}>
          {t("inv.ninguno")}
        </p>
      ) : (
        <ul style={{ listStyle: "none", margin: "0 0 14px", padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
          {invitaciones.map((inv) => (
            <li
              key={inv.id}
              style={{
                display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
                padding: "8px 10px", border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                opacity: inv.estado === "retirado" ? 0.65 : 1,
              }}
            >
              <span style={{ fontWeight: 700, overflowWrap: "anywhere", flex: "1 1 10rem" }}>
                {inv.club_nombre}
                {inv.club_ciudad && (
                  <span className="text-muted" style={{ fontWeight: 400 }}> · {inv.club_ciudad}</span>
                )}
              </span>
              <span className="badge" style={{ color: COLOR[inv.estado], borderColor: COLOR[inv.estado] }}>
                {t(`inv.estado.${inv.estado}` as ClaveTexto)}
              </span>
              {!inv.por_organizacion && (
                <span className="text-muted" style={{ fontSize: "0.78rem" }} title={t("inv.soloNombreAyuda")}>
                  {t("inv.soloNombre")}
                </span>
              )}
              {inv.estado !== "retirado" && (
                <button type="button" className="btn btn-sm" disabled={ocupado} onClick={() => retirar(inv)}>
                  {t("inv.retirar")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* ── Invitar ── */}
      <label className="microetiqueta" htmlFor={`buscar-club-${campId}`} style={{ display: "block", marginBottom: 6 }}>
        {t("inv.invitar")}
      </label>
      <input
        id={`buscar-club-${campId}`}
        className="input"
        value={texto}
        maxLength={80}
        placeholder={t("inv.buscar")}
        onChange={(e) => setTexto(e.target.value)}
        style={{ marginBottom: 8 }}
      />
      {disponible === false && (
        <p style={{ color: "var(--gold)", fontSize: "0.82rem", margin: "0 0 8px" }}>
          {t("inv.sinDirectorio")}
        </p>
      )}

      {resultados.length > 0 && (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          {resultados.map((c) => (
            <li
              key={c.org_id || c.nombre}
              style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: "0.88rem" }}
            >
              <span style={{ flex: "1 1 10rem", overflowWrap: "anywhere" }}>
                {c.nombre}
                {c.ciudad && <span className="text-muted"> · {c.ciudad}</span>}
                {c.afiliado && (
                  <span className="badge" style={{ marginLeft: 6 }}>{t("inv.afiliado")}</span>
                )}
              </span>
              {c.ya_invitado ? (
                <span className="text-muted" style={{ fontSize: "0.8rem" }}>{t("inv.yaInvitado")}</span>
              ) : (
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  disabled={ocupado}
                  onClick={() => invitar({ org_id: c.org_id, nombre: c.nombre, ciudad: c.ciudad })}
                >
                  {t("inv.invitarBoton")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Sin directorio, el nombre escrito se puede invitar tal cual. */}
      {disponible === false && escritoAMano.length >= 3 && !yaEnResultados && (
        <button
          type="button"
          className="btn btn-sm"
          disabled={ocupado}
          style={{ marginTop: 8 }}
          onClick={() => invitar({ nombre: escritoAMano })}
        >
          {t("inv.invitarPorNombre", { nombre: escritoAMano })}
        </button>
      )}
    </div>
  );
}
