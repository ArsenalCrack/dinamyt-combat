"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { misTatamisAPI, type UserData } from "@/lib/api";
import { useI18n, type ClaveTexto } from "@/lib/i18n";

interface MiTatami {
  id: number;
  numero: number;
  campeonato_id: number;
  campeonato_nombre?: string;
  mi_rol: string;
}

// Claves de traducción por rol (los textos viven en lib/i18n)
const ROLES: Record<string, ClaveTexto> = {
  arbitro: "rol.arbitro",
  j1: "rol.j1",
  j2: "rol.j2",
  j3: "rol.j3",
  j4: "rol.j4",
};

export default function JuezPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [user, setUser] = useState<UserData | null>(null);
  const [tatamis, setTatamis] = useState<MiTatami[]>([]);
  const [cargando, setCargando] = useState(true);
  const [sinConexion, setSinConexion] = useState(false);

  const CACHE_KEY = "dinamyt_mis_tatamis";

  const loadTatamis = useCallback(async () => {
    try {
      const data = await misTatamisAPI();
      setTatamis(data);
      setSinConexion(false);
      // Guardar la última lista conocida: sin conexión el juez debe poder
      // volver a su tatami (si no, queda bloqueado fuera del software).
      try { localStorage.setItem(CACHE_KEY, JSON.stringify(data)); } catch { /* */ }
    } catch {
      // Sin servidor: usar la última lista cacheada para no bloquear al juez.
      try {
        const cached = localStorage.getItem(CACHE_KEY);
        if (cached) {
          setTatamis(JSON.parse(cached));
          setSinConexion(true);
        }
      } catch { /* */ }
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    const saved = localStorage.getItem("dinamyt_user");
    if (!saved) { router.replace("/login"); return; }
    const u = JSON.parse(saved);
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setUser(u);
      void loadTatamis();
    });
    return () => { cancelled = true; };
  }, [loadTatamis, router]);

  if (!user) return null;

  return (
    <div style={{ maxWidth: 540, margin: "0 auto", padding: "20px" }}>
      {/* Header */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 24, paddingBottom: 16, borderBottom: "1px solid var(--border)"
      }}>
        {/* Antetitulo + titulo, como en Membresias. La marca la pone la barra. */}
        {/* Sin antetitulo: la barra ya dice donde estamos. */}
        <div>
          <h1 className="display" style={{ fontSize: "1.5rem" }}>
            {t("juez.bienvenido")} {user.nombre}
          </h1>
        </div>
      </div>

      {/* My tatamis */}
      {sinConexion && (
        <div style={{
          marginBottom: 12, padding: "8px 12px", borderRadius: "var(--radius-sm)",
          border: "1px solid var(--red-alert)", background: "rgba(232,0,42,0.08)",
          color: "var(--red-alert)", fontSize: "0.88rem", fontWeight: 700, textAlign: "center",
        }}>
          {t("juez.offline")}
        </div>
      )}
      <div className="card-title">{t("juez.misTatamis")}</div>
      {tatamis.length > 0 ? (
        <>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginBottom: 12 }}>
            {t("juez.instruccion")}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
            {/* "tat" y no "t": no hacerle sombra a la función de traducción */}
            {tatamis.map((tat) => (
              <div
                key={tat.id}
                className="card"
                style={{ cursor: "pointer" }}
                onClick={() => router.push(`/tatami/${tat.id}?rol=${tat.mi_rol}`)}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <div style={{ minWidth: 0 }}>
                    <span style={{ fontWeight: 700, fontSize: "1.1rem" }}>
                      {t("juez.tatami")} {tat.numero}
                    </span>
                    {tat.campeonato_nombre && (
                      <div style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>
                        {tat.campeonato_nombre}
                      </div>
                    )}
                    <span style={{
                      display: "inline-block", marginTop: 6,
                      padding: "4px 10px", borderRadius: "var(--radius-sm)", fontSize: "0.82rem",
                      fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em",
                      background: tat.mi_rol === "arbitro" ? "var(--gold-bg)" : "var(--chung-bg)",
                      color: tat.mi_rol === "arbitro" ? "var(--gold)" : "var(--chung-light)",
                      border: `1px solid ${tat.mi_rol === "arbitro" ? "var(--gold-border)" : "var(--chung-border)"}`,
                    }}>{ROLES[tat.mi_rol] ? t(ROLES[tat.mi_rol]) : tat.mi_rol}</span>
                  </div>
                  <button
                    className="btn btn-primary"
                    style={{ flexShrink: 0 }}
                    onClick={(e) => {
                      e.stopPropagation();
                      router.push(`/tatami/${tat.id}?rol=${tat.mi_rol}`);
                    }}
                  >
                    {t("juez.entrar")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="card" style={{ textAlign: "center", padding: 32, color: "var(--text-dim)", marginBottom: 24 }}>
          {cargando ? (
            t("juez.cargando")
          ) : (
            <>
              <p style={{ marginBottom: 8, fontWeight: 700, color: "var(--text-muted)" }}>
                {t("juez.sinAsignacion")}
              </p>
              <p style={{ fontSize: "0.9rem", margin: 0 }}>
                {t("juez.sinAsignacionDesc")}
              </p>
            </>
          )}
        </div>
      )}

      <div style={{ textAlign: "center", marginTop: 16 }}>
        <p style={{ color: "var(--text-dim)", fontSize: "0.875rem" }}>
          DINAMYT v4.0 &middot; Global Hapkido Association
        </p>
      </div>
    </div>
  );
}
