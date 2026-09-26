"use client";

// ═════════════════════════════════════════════════════════════════════════════
// QUIÉN ADMINISTRA QUÉ (F4 de PLAN-CAMPEONATOS, decisión D3)
//
// La regla del negocio es un solo administrador de Campeonatos por
// organización. Desde F4 se aplica a quien ENTRA por primera vez; a quien ya
// estaba no se le toca nada, y D3 dice por qué: primero se mira la lista, y la
// decisión se toma club por club. Esta tarjeta ES esa lista.
//
// Solo la ve el superadministrador. Y si no hay nada que decidir —ninguna
// organización con dos admins y todos con organización— no pinta nada: una
// tarjeta que dice «todo bien» cada vez que se abre el panel es ruido.
// ═════════════════════════════════════════════════════════════════════════════

import { useCallback, useEffect, useState } from "react";
import {
  informeAdministradoresAPI,
  traspasarWorkspaceAPI,
  type InformeAdministradores,
  type InformeTraspaso,
} from "@/lib/api";
import { useConfirmDialog } from "@/components/ConfirmDialog";
import { useI18n } from "@/lib/i18n";
import { aviso } from "@/lib/toast";

function errorDe(err: unknown): string | undefined {
  return (err as { response?: { data?: { error?: string } } }).response?.data?.error;
}

export default function InformeAdministradoresCard() {
  const { t } = useI18n();
  const [informe, setInforme] = useState<InformeAdministradores | null>(null);
  // El traspaso (F4, punto 3): de quién a quién, y lo que diría en seco.
  const [de, setDe] = useState<Record<string, number>>({});
  const [a, setA] = useState<Record<string, number>>({});
  const [vista, setVista] = useState<Record<string, InformeTraspaso | undefined>>({});
  const [ocupado, setOcupado] = useState(false);
  const { pedirConfirmacion, dialogo } = useConfirmDialog();

  const cargar = useCallback(() => {
    informeAdministradoresAPI()
      .then(setInforme)
      // Es un dato de apoyo: si falla, el panel sigue funcionando entero.
      .catch(() => {});
  }, []);

  useEffect(() => {
    queueMicrotask(cargar);
  }, [cargar]);

  async function verTraspaso(orgId: string) {
    if (!de[orgId] || !a[orgId]) return;
    setOcupado(true);
    try {
      const r = await traspasarWorkspaceAPI(de[orgId], a[orgId]);
      setVista((v) => ({ ...v, [orgId]: r }));
    } catch (err) {
      aviso(errorDe(err) || t("org.traspaso.error"), "error");
    } finally {
      setOcupado(false);
    }
  }

  function aplicarTraspaso(orgId: string) {
    const previa = vista[orgId];
    if (!previa || previa.choques.length) return;
    pedirConfirmacion({
      titulo: t("org.traspaso.confirmarTitulo"),
      mensaje: t("org.traspaso.confirmar", { de: previa.de.nombre, a: previa.a.nombre }),
      tipo: "peligro",
      confirmLabel: t("org.traspaso.aplicar"),
      onConfirm: async () => {
        setOcupado(true);
        try {
          await traspasarWorkspaceAPI(previa.de.id, previa.a.id, true);
          aviso(t("org.traspaso.hecho", { a: previa.a.nombre }), "ok");
          setVista((v) => ({ ...v, [orgId]: undefined }));
          cargar();
        } catch (err) {
          aviso(errorDe(err) || t("org.traspaso.error"), "error");
        } finally {
          setOcupado(false);
        }
      },
    });
  }

  if (!informe) return null;
  if (!informe.varios.length && !informe.sin_organizacion.length) return null;

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="card-title">🏛️ {t("org.informe.titulo")}</div>
      <p className="text-muted" style={{ fontSize: "0.86rem", margin: "0 0 12px" }}>
        {t("org.informe.ayuda")}
      </p>

      {informe.varios.map((grupo) => (
        <div
          key={grupo.org_id}
          style={{
            padding: "10px 12px", marginBottom: 8,
            border: "1px solid var(--gold-border)", background: "var(--gold-bg)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          <div style={{ fontWeight: 700, overflowWrap: "anywhere" }}>
            {grupo.org_nombre || t("org.sinNombre")}
            <span className="badge" style={{ marginLeft: 8 }}>
              {t("org.informe.admins", { n: grupo.admins.length })}
            </span>
          </div>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: "0.86rem" }}>
            {grupo.admins.map((adm) => (
              <li key={adm.id} style={{ overflowWrap: "anywhere" }}>
                {adm.nombre} <span className="text-muted">· {adm.email}</span>
              </li>
            ))}
          </ul>
          {/* El traspaso: todo lo de uno pasa al otro, primero en seco. */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 10, fontSize: "0.85rem" }}>
            <span>{t("org.traspaso.pasar")}</span>
            <select className="input" style={{ width: "auto", minHeight: 34 }}
              value={de[grupo.org_id] ?? ""}
              onChange={(e) => {
                setDe({ ...de, [grupo.org_id]: Number(e.target.value) });
                setVista({ ...vista, [grupo.org_id]: undefined });
              }}>
              <option value="">—</option>
              {grupo.admins.map((adm) => <option key={adm.id} value={adm.id}>{adm.nombre}</option>)}
            </select>
            <span>{t("org.traspaso.a")}</span>
            <select className="input" style={{ width: "auto", minHeight: 34 }}
              value={a[grupo.org_id] ?? ""}
              onChange={(e) => {
                setA({ ...a, [grupo.org_id]: Number(e.target.value) });
                setVista({ ...vista, [grupo.org_id]: undefined });
              }}>
              <option value="">—</option>
              {grupo.admins
                .filter((adm) => adm.id !== de[grupo.org_id])
                .map((adm) => <option key={adm.id} value={adm.id}>{adm.nombre}</option>)}
            </select>
            <button type="button" className="btn btn-sm"
              disabled={ocupado || !de[grupo.org_id] || !a[grupo.org_id]}
              onClick={() => void verTraspaso(grupo.org_id)}>
              {t("org.traspaso.ver")}
            </button>
          </div>
          {vista[grupo.org_id] && (
            <div style={{ marginTop: 8, fontSize: "0.84rem" }}>
              <div>
                {t("org.traspaso.seMueven")}{" "}
                {Object.entries(vista[grupo.org_id]!.filas)
                  .filter(([, n]) => n > 0)
                  .map(([tabla, n]) => `${n} ${tabla}`)
                  .join(" · ") || t("org.traspaso.nada")}
              </div>
              {vista[grupo.org_id]!.choques.length > 0 ? (
                <div style={{ color: "var(--red-alert)", marginTop: 4 }}>
                  {t("org.traspaso.choques", { n: vista[grupo.org_id]!.choques.length })}{" "}
                  {vista[grupo.org_id]!.choques.map((c) => c.documento).join(", ")}
                </div>
              ) : (
                <button type="button" className="btn btn-sm btn-danger" style={{ marginTop: 6 }}
                  disabled={ocupado}
                  onClick={() => aplicarTraspaso(grupo.org_id)}>
                  {t("org.traspaso.aplicar")}
                </button>
              )}
            </div>
          )}
        </div>
      ))}

      {informe.sin_organizacion.length > 0 && (
        <p className="text-muted" style={{ fontSize: "0.84rem", margin: "8px 0 0" }}>
          {t("org.informe.sinOrg", { n: informe.sin_organizacion.length })}{" "}
          {informe.sin_organizacion.map((a) => a.nombre).join(", ")}
        </p>
      )}
      <p className="text-muted" style={{ fontSize: "0.8rem", margin: "8px 0 0" }}>
        {t("org.informe.conUno", { n: informe.con_uno })}
      </p>
      {dialogo}
    </div>
  );
}
