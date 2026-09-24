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

import { useEffect, useState } from "react";
import { informeAdministradoresAPI, type InformeAdministradores } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function InformeAdministradoresCard() {
  const { t } = useI18n();
  const [informe, setInforme] = useState<InformeAdministradores | null>(null);

  useEffect(() => {
    let cancelado = false;
    informeAdministradoresAPI()
      .then((d) => { if (!cancelado) setInforme(d); })
      // Es un dato de apoyo: si falla, el panel sigue funcionando entero.
      .catch(() => {});
    return () => { cancelado = true; };
  }, []);

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
            {grupo.admins.map((a) => (
              <li key={a.id} style={{ overflowWrap: "anywhere" }}>
                {a.nombre} <span className="text-muted">· {a.email}</span>
              </li>
            ))}
          </ul>
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
    </div>
  );
}
