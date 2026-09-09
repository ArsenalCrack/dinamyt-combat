"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Cargando } from "@/components/Cargando";
import { useI18n } from "@/lib/i18n";
import { haySesionProbable, obtenerUsuario } from "@/lib/sesion";

export default function Home() {
  const router = useRouter();
  const { t } = useI18n();

  useEffect(() => {
    // La cookie de sesión no se ve desde aquí: se usa la de CSRF como pista de
    // que hay sesión y el perfil cacheado para saber a dónde mandar. Si no
    // cuadra, /login o el propio backend corrigen.
    const parsed = haySesionProbable() ? obtenerUsuario<{ rol?: string }>() : null;
    if (parsed?.rol) {
      router.replace(
        parsed.rol === "admin" ? "/admin"
        : parsed.rol === "maestro" ? "/maestro"
        : "/juez"
      );
      return;
    }
    router.replace("/login");
  }, [router]);

  // La portada es un desvío: se mira medio segundo y se sale. Dibujaba la
  // marca A 2.2 REM Y EN VERTICAL —el logo de una portada, no el de una
  // espera—, sin una sola palabra que dijera qué estaba pasando. Quien llega
  // desde el portal veía el escudo de otra app a pantalla completa y ninguna
  // pista de si aquello iba a algún sitio. Ahora es la misma espera que en las
  // otras veinticuatro del ecosistema, y dice a dónde va.
  return <Cargando mensaje={t("comun.cargando")} />;
}
