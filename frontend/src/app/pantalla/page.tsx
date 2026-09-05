"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listCampeonatosPublicoAPI } from "@/lib/api";
import Logo from "@/components/Logo";
import PublicControls from "@/components/PublicControls";
import { useI18n } from "@/lib/i18n";

interface TatamiPublico {
  id: number;
  numero: number;
}

interface CampeonatoPublico {
  id: number;
  nombre: string;
  tatamis: TatamiPublico[];
}

export default function PantallaAccess() {
  const router = useRouter();
  const { t } = useI18n();
  const [campeonatos, setCampeonatos] = useState<CampeonatoPublico[]>([]);
  const [campId, setCampId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  // Booleano y no texto: el mensaje se traduce al renderizar, así cambia
  // en vivo si el usuario cambia de idioma
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(async () => {
      try {
        const data = await listCampeonatosPublicoAPI();
        if (cancelled) return;
        setCampeonatos(data);
        // Si solo hay un campeonato activo, seleccionarlo de una vez
        if (data.length === 1) setCampId(data[0].id);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, []);

  const campSeleccionado = campeonatos.find((c) => c.id === campId) || null;

  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", minHeight: "100vh", padding: 20
    }}>
      <div style={{
        width: "100%", maxWidth: 460, background: "var(--bg-card)",
        border: "1px solid var(--border)", borderRadius: "var(--radius-lg)",
        padding: "36px 28px", textAlign: "center"
      }} className="animate-slide">
        {/* La pantalla de proyeccion es el unico sitio donde «DINAMYT» va en dos
            colores: aqui se lee desde la grada y el oro ayuda. En el resto de la
            app la palabra va entera del color del texto, como en las otras tres
            webs — ver `.logo em` en globals.css. */}
        <Logo
          stacked
          className="logo-acento"
          fontSize="clamp(1.8rem, 6vw, 2.2rem)"
          style={{ marginBottom: 8 }}
        />
        <p style={{ color: "var(--text-muted)", marginBottom: 24, fontSize: "0.9rem" }}>
          {t("pantalla.sub")}
        </p>

        {loading ? (
          <p className="animate-shimmer" style={{ color: "var(--text-muted)", padding: "20px 0" }}>
            {t("pantalla.cargando")}
          </p>
        ) : error ? (
          <p style={{ color: "var(--red-alert)", padding: "12px 0", fontWeight: 700 }}>{t("pantalla.errorConexion")}</p>
        ) : campeonatos.length === 0 ? (
          <p style={{ color: "var(--text-dim)", padding: "16px 0" }}>
            {t("pantalla.sinCampeonatos")}
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 16, textAlign: "left" }}>
            {/* Paso 1: Campeonato */}
            <div>
              <label style={{
                fontSize: "0.85rem", fontWeight: 800, textTransform: "uppercase",
                letterSpacing: "0.08em", color: "var(--text-muted)",
                display: "block", marginBottom: 6,
              }}>{t("pantalla.pasoCampeonato")}</label>
              {campeonatos.length === 1 ? (
                <div style={{
                  padding: "12px 14px", borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--gold-border)", background: "var(--gold-bg)",
                  color: "var(--gold)", fontWeight: 700,
                }}>
                  {campeonatos[0].nombre}
                </div>
              ) : (
                <select
                  className="input"
                  value={campId ?? ""}
                  onChange={(e) => setCampId(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">{t("pantalla.selecciona")}</option>
                  {campeonatos.map((c) => (
                    <option key={c.id} value={c.id}>{c.nombre}</option>
                  ))}
                </select>
              )}
            </div>

            {/* Paso 2: Tatami */}
            {campSeleccionado && (
              <div className="animate-fade">
                <label style={{
                  fontSize: "0.85rem", fontWeight: 800, textTransform: "uppercase",
                  letterSpacing: "0.08em", color: "var(--text-muted)",
                  display: "block", marginBottom: 6,
                }}>{t("pantalla.pasoTatami")}</label>
                {campSeleccionado.tatamis.length === 0 ? (
                  <p style={{ color: "var(--text-dim)", fontSize: "0.9rem" }}>
                    {t("pantalla.sinTatamis")}
                  </p>
                ) : (
                  <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(96px, 1fr))",
                    gap: 8,
                  }}>
                    {/* "tat" y no "t": no hacerle sombra a la función de traducción */}
                    {campSeleccionado.tatamis.map((tat) => (
                      <button
                        key={tat.id}
                        type="button"
                        className="btn"
                        onClick={() => router.push(`/tatami/${tat.id}?rol=pantalla`)}
                        style={{
                          flexDirection: "column", gap: 2, minHeight: 64,
                          borderColor: "var(--chung-border)",
                        }}
                      >
                        <span style={{
                          fontFamily: "var(--font-display)", fontSize: "1.6rem",
                          color: "var(--chung-light)", lineHeight: 1,
                        }}>{tat.numero}</span>
                        <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                          {t("pantalla.tatami")}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div style={{ marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 12 }}>
          <button onClick={() => router.push("/resultados")}
            className="btn btn-sm"
            style={{ borderColor: "var(--gold-border)", color: "var(--gold)" }}>
            {t("res.verResultados")}
          </button>
          <button onClick={() => router.push("/login")}
            style={{
              background: "none", border: "none", color: "var(--gold)",
              cursor: "pointer", fontSize: "0.9rem", fontFamily: "var(--font-body)"
            }}>
            {t("pantalla.loginJuez")}
          </button>
        </div>
      </div>

      {/* Sin sesión no hay menú global: controles propios de tema e idioma */}
      <PublicControls />
    </div>
  );
}
