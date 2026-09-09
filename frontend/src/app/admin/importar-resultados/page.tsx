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

export default function ImportarResultadosPage() {
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
      avisoError(m || "No se pudo importar el archivo. ¿Es un export de resultados de DINAMYT?");
    } finally {
      setImportando(false);
    }
  }

  async function handleEliminar(pubId: string, nombre: string) {
    if (!confirm(`¿Quitar de la web pública los resultados de "${nombre}"?`)) return;
    const uuid = pubId.startsWith("pub:") ? pubId.slice(4) : pubId;
    try {
      await eliminarResultadoPublicadoAPI(uuid);
      await cargarPublicados();
      avisoOk(`Se quitó "${nombre}" de los resultados públicos.`);
    } catch {
      avisoError("No se pudo quitar el snapshot.");
    }
  }

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <button className="btn btn-outline btn-sm" onClick={() => router.push("/admin")} style={{ marginBottom: 8 }}>
          ← Volver
        </button>
        <h1 className="display" style={{ fontSize: "1.5rem" }}>Importar resultados</h1>
        <p className="text-muted" style={{ fontSize: "0.92rem" }}>
          Sube el archivo <code>.json</code> exportado desde el software local (Reportes → “Exportar
          resultados”) para publicarlo en la página pública de resultados.
        </p>
      </div>

      {/* Subir archivo */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="card-title" style={{ marginBottom: 0 }}>Subir archivo de resultados</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input
            ref={inputRef}
            type="file"
            accept=".json,application/json"
            onChange={(e) => setArchivo(e.target.files?.[0] || null)}
            style={{ fontSize: "0.88rem", color: "var(--text-muted)", maxWidth: "100%" }}
            aria-label="Archivo .json de resultados"
          />
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!archivo || importando}
            onClick={handleImportar}
          >
            {importando ? "Importando…" : "Importar y publicar"}
          </button>
        </div>
        {resultado && (
          <div style={{ fontSize: "0.9rem", color: "var(--text-muted)" }}>
            <strong style={{ color: "var(--green)" }}>{resultado.message}</strong> ·{" "}
            {resultado.num_resultados} resultado(s).
          </div>
        )}
      </div>

      {/* Ya publicados */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div className="card-title" style={{ marginBottom: 0 }}>Publicados actualmente</div>
          <a className="btn btn-outline btn-sm" href="/resultados" target="_blank" rel="noreferrer">
            Ver página pública ↗
          </a>
        </div>
        {publicados.length === 0 ? (
          <p className="text-muted" style={{ fontSize: "0.9rem", margin: 0 }}>
            Aún no hay resultados importados.
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
                    {p.num_resultados} resultado(s)
                    {p.importado_at ? ` · ${new Date(p.importado_at).toLocaleString("es-CO", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}` : ""}
                  </div>
                </div>
                <button
                  className="btn btn-outline btn-sm"
                  onClick={() => handleEliminar(String(p.id), p.nombre)}
                  style={{ color: "#ff9a9a" }}
                >
                  Quitar
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
