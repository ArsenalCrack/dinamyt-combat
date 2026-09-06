"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  listCampeonatosPublicoAPI,
  type CampeonatoPublico,
} from "@/lib/api";
import Logo from "@/components/Logo";
import PublicControls from "@/components/PublicControls";
import { useI18n, type ClaveTexto } from "@/lib/i18n";

function fechaRango(inicio: string | null, fin: string | null): string {
  const fmt = (s: string) => {
    const d = new Date(`${s}T00:00:00`);
    return isNaN(d.getTime()) ? s : d.toLocaleDateString();
  };
  if (inicio && fin && inicio !== fin) return `${fmt(inicio)} – ${fmt(fin)}`;
  if (inicio) return fmt(inicio);
  if (fin) return fmt(fin);
  return "";
}

export default function CampeonatosPublicoPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [camps, setCamps] = useState<CampeonatoPublico[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(async () => {
      try {
        const lista = await listCampeonatosPublicoAPI();
        if (!cancelled) setCamps(lista);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="campub-page">
      <div className="campub-header">
        <Logo className="solo-sin-barra" fontSize="1.5rem" />
        <div>
          <h1 className="campub-titulo">{t("pub.camp.titulo")}</h1>
          <p className="campub-sub">{t("pub.camp.sub")}</p>
        </div>
        <button className="btn btn-sm btn-ghost" onClick={() => router.push("/login")}>
          {t("pub.camp.volver")}
        </button>
      </div>

      {loading ? (
        <p className="campub-msg animate-shimmer">{t("pub.camp.cargando")}</p>
      ) : error ? (
        <p className="campub-msg" style={{ color: "var(--red-alert)" }}>{t("pub.camp.errorConexion")}</p>
      ) : camps.length === 0 ? (
        <p className="campub-msg">{t("pub.camp.sinCampeonatos")}</p>
      ) : (
        <div className="campub-grid">
          {/* La tarjeta es solo el resumen: el detalle completo (inscritos,
              jueces, clubes y tatamis) vive en su propia ficha. */}
          {camps.map((c) => {
            const fecha = fechaRango(c.fecha_inicio, c.fecha_fin);
            const lugar = [c.lugar, c.ciudad, c.pais].filter(Boolean).join(", ");
            return (
              <button
                key={c.id}
                type="button"
                className="card campub-card"
                onClick={() => router.push(`/campeonatos/${c.id}`)}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontWeight: 800, fontSize: "1.1rem", overflowWrap: "anywhere" }}>{c.nombre}</span>
                  <span className="badge badge-gray">{t(`camp.estado.${c.estado}` as ClaveTexto)}</span>
                </div>
                {c.descripcion && (
                  <div style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>{c.descripcion}</div>
                )}
                <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.88rem", color: "var(--text-muted)" }}>
                  {fecha && <div>📅 {t("pub.camp.fecha")}: {fecha}</div>}
                  {lugar && <div>📍 {lugar}</div>}
                </div>
                <span className="campub-abrir">{t("pub.camp.abrir")} →</span>
              </button>
            );
          })}
        </div>
      )}

      <PublicControls />

      <style>{`
        .campub-page {
          max-width: 1100px; margin: 0 auto; padding: 20px clamp(14px, 4vw, 32px);
          display: flex; flex-direction: column; gap: 16px; min-height: 100dvh;
        }
        .campub-header {
          display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
          padding-bottom: 12px; border-bottom: 1px solid var(--border);
        }
        .campub-header > div { flex: 1; min-width: 0; }
        .campub-titulo {
          font-family: var(--font-display); font-size: 1.5rem;
          font-weight: 800; font-stretch: 118%; text-transform: uppercase;
          color: var(--text); letter-spacing: -0.015em; line-height: 0.98;
        }
        .campub-sub { color: var(--text-muted); font-size: 0.9rem; margin-top: 2px; }
        .campub-msg { text-align: center; padding: 40px 0; color: var(--text-muted); }
        .campub-grid {
          display: grid; gap: 12px;
          grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
          align-items: start;
        }
        .campub-card {
          display: flex; flex-direction: column; gap: 10px;
          width: 100%; text-align: left; font: inherit; color: inherit;
          cursor: pointer; transition: var(--transition);
        }
        .campub-card:hover, .campub-card:focus-visible {
          border-color: var(--gold-border); background: var(--bg-elevated);
          outline: none;
        }
        .campub-abrir {
          margin-top: auto; color: var(--gold); font-weight: 800;
          font-size: 0.9rem;
        }
      `}</style>
    </div>
  );
}
