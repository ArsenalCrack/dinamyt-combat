"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { getCampeonatoAPI } from "@/lib/api";
import LlavesSection from "@/components/LlavesSection";
import { useI18n } from "@/lib/i18n";

export default function LlavesCampeonatoPage() {
  const router = useRouter();
  const { t } = useI18n();
  const params = useParams();
  const campId = Number(params.id);
  const [campNombre, setCampNombre] = useState("");

  useEffect(() => {
    const user = localStorage.getItem("dinamyt_user");
    if (!user || JSON.parse(user).rol !== "admin") {
      router.replace("/login"); return;
    }
    let cancelled = false;
    queueMicrotask(async () => {
      try {
        const c = await getCampeonatoAPI(campId);
        if (!cancelled) setCampNombre(c.nombre);
      } catch {
        if (!cancelled) router.replace("/admin");
      }
    });
    return () => { cancelled = true; };
  }, [campId, router]);

  return (
    <div className="llaves-page">
      <div style={{ marginBottom: 20 }}>
        <button className="btn btn-outline btn-sm" onClick={() => router.push(`/admin/campeonato/${campId}`)}
          style={{ marginBottom: 8 }}>
          {t("ins.volver")}
        </button>
        <h1 className="display" style={{ fontSize: "1.5rem", overflowWrap: "anywhere" }}>
          {t("llv.titulo")} {campNombre || "..."}
        </h1>
        <p className="text-muted" style={{ fontSize: "0.92rem" }}>
          {t("llv.desc")}
        </p>
      </div>

      <LlavesSection campeonatoId={campId} />

      <style>{`
        .llaves-page {
          max-width: 1200px;
          margin: 0 auto;
          padding: 20px;
        }
        @media (max-width: 600px) {
          .llaves-page { padding: 14px; }
        }
      `}</style>
    </div>
  );
}
