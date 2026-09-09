"use client";

// ═════════════════════════════════════════════════════════════════════════════
// ACCESO DIRECTO POR QR — destino del código que genera el administrador.
//
// La URL llega como  /acceso#token=...&tatami=X&rol=jY  (los datos van en el
// fragmento #, que nunca sale del navegador ni queda en logs del servidor).
// Se guarda la sesión del juez y se entra directo a su rol en el tatami,
// sin escribir usuario ni contraseña.
// ═════════════════════════════════════════════════════════════════════════════

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { abrirSesionConToken } from "@/lib/api";
import { guardarToken, guardarUsuario, limpiarSesion } from "@/lib/sesion";
import Logo from "@/components/Logo";
import { Cargando } from "@/components/Cargando";
import { useI18n } from "@/lib/i18n";

export default function AccesoPage() {
  const router = useRouter();
  const { t } = useI18n();
  // Se guarda la CLAVE del error (no el texto): así el mensaje cambia de
  // idioma en vivo si el usuario lo cambia.
  const [error, setError] = useState<"incompleto" | "invalido" | "">("");

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(async () => {
      try {
        const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
        const token = params.get("token");
        const tatami = params.get("tatami");
        const rol = params.get("rol");
        if (!token || !tatami || !rol) {
          if (!cancelled) setError("incompleto");
          return;
        }
        // El token del QR se canjea por la cookie httpOnly en vez de quedarse
        // en localStorage: así valida contra el servidor y abre sesión de un
        // paso, y el token no queda al alcance de ningún script de la página.
        const { user } = await abrirSesionConToken(token);
        if (cancelled) return;
        guardarToken(token);
        guardarUsuario(user);
        router.replace(`/tatami/${tatami}?rol=${rol}`);
      } catch {
        if (!cancelled) {
          limpiarSesion();
          setError("invalido");
        }
      }
    });
    return () => { cancelled = true; };
  }, [router]);

  // ── La espera es la del ecosistema; el error sigue siendo una tarjeta ──────
  //
  // No son la misma cosa y no se dibujan igual. ESPERAR es el escudo latiendo y
  // una línea: dura dos segundos, no hay nada que decidir, y aquí llevaba la
  // marca en vertical a 2.2 rem, o sea el tamaño de una portada para un estado
  // que nadie llega a leer. FALLAR sí es una tarjeta, porque hay algo que leer
  // —qué pasó con el QR— y algo que pulsar.
  if (error) {
    return (
      <div style={{
        minHeight: "100dvh", display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", gap: 16, padding: 20,
      }}>
        <Logo stacked className="animate-fade" fontSize="2.2rem" />
        <div className="card" style={{ maxWidth: 420, textAlign: "center" }}>
          <p style={{ color: "var(--red-alert)", fontWeight: 700, marginBottom: 12 }}>
            {error === "incompleto" ? t("acceso.incompleto") : t("acceso.invalido")}
          </p>
          <button className="btn btn-primary" onClick={() => router.replace("/login")}>
            {t("acceso.irLogin")}
          </button>
        </div>
      </div>
    );
  }

  return <Cargando mensaje={t("acceso.entrando")} />;
}
