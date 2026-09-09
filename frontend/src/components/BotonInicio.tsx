"use client";

import { useRouter } from "next/navigation";
import { esExterno, urlDeInicioPublico } from "@/lib/portal";

/**
 * El botón «← Inicio» de las pantallas públicas.
 *
 * ── Por qué es un componente y no tres botones ──────────────────────────────
 *
 * Porque eran tres botones —resultados, la lista de campeonatos y la pantalla
 * de proyección— y los tres hacían `router.push("/login")`, o sea que los tres
 * mandaban al formulario de contraseña de Campeonatos a gente que no tiene
 * cuenta aquí. Tres copias de la misma decisión es cómo se arregla una y las
 * otras dos siguen rotas seis meses. El destino lo decide ahora
 * `urlDeInicioPublico()`, en un solo sitio.
 *
 * ── `<a>` y `<button>`, y por qué los dos ───────────────────────────────────
 *
 * Cuando hay portal, Inicio está en OTRO origen: el router de Next no llega
 * ahí, hace falta una navegación de verdad —y siendo un enlace de verdad, se
 * puede abrir en otra pestaña, copiar la dirección y leerla en la barra de
 * estado, que es lo que cualquiera espera de algo que se llama «Inicio».
 * En el modo local del día del evento no hay portal, el inicio es `/login` y
 * ahí sí manda el router, que no recarga la aplicación entera.
 */
export default function BotonInicio({
  texto,
  className = "btn btn-sm btn-ghost",
}: {
  texto: string;
  className?: string;
}) {
  const router = useRouter();
  const destino = urlDeInicioPublico();

  if (esExterno(destino)) {
    return (
      <a className={className} href={destino}>
        {texto}
      </a>
    );
  }

  return (
    <button className={className} onClick={() => router.push(destino)}>
      {texto}
    </button>
  );
}
