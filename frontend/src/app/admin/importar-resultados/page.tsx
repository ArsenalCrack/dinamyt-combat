"use client";

// ═════════════════════════════════════════════════════════════════════════════
// IMPORTAR RESULTADOS — para el software ONLINE (el de la red/internet).
//
// La organización trabaja el campeonato en el software LOCAL. Desde Reportes
// exporta un archivo .json ("Exportar resultados") y aquí lo sube para
// PUBLICARLO: la página pública /resultados lo muestra igual que los
// resultados calculados en vivo. Reimportar el mismo campeonato lo reemplaza.
// ═════════════════════════════════════════════════════════════════════════════

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  importarResultadosAPI,
  listCampeonatosResultadosAPI,
  eliminarResultadoPublicadoAPI,
  type CampeonatoResultadoItem,
  type ImportResultadosResumen,
} from "@/lib/api";
import { avisoError, avisoOk } from "@/lib/toast";
import { useI18n } from "@/lib/i18n";

export default function ImportarResultadosPage() {
  const { t, idioma } = useI18n();
  const router = useRouter();
  const [archivo, setArchivo] = useState<File | null>(null);
  const [importando, setImportando] = useState(false);
  const [resultado, setResultado] = useState<ImportResultadosResumen | null>(null);
  const [publicados, setPublicados] = useState<CampeonatoResultadoItem[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const user = localStorage.getItem("dinamyt_user");
    if (!user || JSON.parse(user).rol !== "admin") {
      router.replace("/login");
    }
  }, [router]);

  const cargarPublicados = useCallback(async () => {
    try {
      const lista = await listCampeonatosResultadosAPI();
      setPublicados(lista.filter((c) => c.publicado));
    } catch {
      /* silencioso: si el backend no responde, solo no se listan */
    }
  }, []);

  useEffect(() => {
    void cargarPublicados();
  }, [cargarPublicados]);

  async function handleImportar() {
    if (!archivo) return;
    setImportando(true);
    setResultado(null);
    try {
      const res = await importarResultadosAPI(archivo);
      setResultado(res);
      setArchivo(null);
      if (inputRef.current) inputRef.current.value = "";
      // El aviso sale con la lista de publicados ya refrescada: confirma un
      // hecho consumado, no una importación a medio reflejar.
      await cargarPublicados();
      avisoOk(res.message);
    } catch (err) {
      const m = (err as { response?: { data?: { error?: string } } }).response?.data?.error;
      avisoError(m || t("err.importarResultados"));
    } finally {
      setImportando(false);
    }
  }

  async function handleEliminar(pubId: string, nombre: string) {
    if (!confirm(t("imp.quitarConfirmar", { nombre }))) return;
    const uuid = pubId.startsWith("pub:") ? pubId.slice(4) : pubId;
    try {
      await eliminarResultadoPublicadoAPI(uuid);
      await cargarPublicados();
      avisoOk(t("imp.quitado", { nombre }));
    } catch {
      avisoError(t("err.quitarSnapshot"));
    }
  }

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <button className="btn btn-outline btn-sm" onClick={() => router.push("/admin")} style={{ marginBottom: 8 }}>
          {t("local.volver")}
        </button>
        <h1 className="display" style={{ fontSize: "1.5rem" }}>{t("imp.titulo")}</h1>
        <p className="text-muted" style={{ fontSize: "0.92rem" }}>
          {t("imp.sub")}
        </p>
      </div>

      {/* Subir archivo */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="card-title" style={{ marginBottom: 0 }}>{t("imp.subir")}</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input
            ref={inputRef}
            type="file"
            accept=".json,application/json"
            onChange={(e) => setArchivo(e.target.files?.[0] || null)}
            style={{ fontSize: "0.88rem", color: "var(--text-muted)", maxWidth: "100%" }}
            aria-label={t("imp.archivoAria")}
          />
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!archivo || importando}
            onClick={handleImportar}
          >
            {importando ? t("imp.importando") : t("imp.importar")}
          </button>
        </div>
        {resultado && (
          <div style={{ fontSize: "0.9rem", color: "var(--text-muted)" }}>
            <strong style={{ color: "var(--green)" }}>{resultado.message}</strong> ·{" "}
            {t("imp.nResultados", { n: resultado.num_resultados })}
          </div>
        )}
      </div>

      {/* Ya publicados */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div className="card-title" style={{ marginBottom: 0 }}>{t("imp.publicados")}</div>
          <a className="btn btn-outline btn-sm" href="/resultados" target="_blank" rel="noreferrer">
            {t("imp.verPublica")}
          </a>
        </div>
        {publicados.length === 0 ? (
          <p className="text-muted" style={{ fontSize: "0.9rem", margin: 0 }}>
            {t("imp.sinImportados")}
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {publicados.map((p) => (
              <div
                key={String(p.id)}
                style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  gap: 10, padding: "8px 12px", borderRadius: "var(--radius-sm)",
                  background: "var(--bg-elevated)", border: "1px solid var(--border)",
                }}
              >
                <div>
                  <div style={{ fontWeight: 700 }}>{p.nombre}</div>
                  <div className="text-muted" style={{ fontSize: "0.82rem" }}>
                    {t("imp.nResultados", { n: p.num_resultados })}
                    {p.importado_at ? ` · ${new Date(p.importado_at).toLocaleString(idioma === "en" ? "en-GB" : "es-CO", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}` : ""}
                  </div>
                </div>
                <button
                  className="btn btn-outline btn-sm"
                  onClick={() => handleEliminar(String(p.id), p.nombre)}
                  style={{ color: "#ff9a9a" }}
                >
                  {t("imp.quitar")}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
