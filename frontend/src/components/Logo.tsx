"use client";

import { PORTAL_URL } from "@/lib/portal";

/**
 * Logo de DINAMYT: imagen + marca de texto.
 * - inline (default): imagen a la izquierda del texto, escala con `fontSize`.
 * - stacked: imagen EN GRANDE arriba y "DINAMYT" centrado debajo (pantallas
 *   públicas y portadas).
 * - soloImagen: solo la imagen (para espacios reducidos donde la marca de
 *   texto ya aparece en otro lugar de la pantalla).
 * - alPortal: lo envuelve en un enlace a DINAMYT. Ver abajo.
 * El alto de la imagen va en `em`, así que todo escala con el fontSize
 * (incluido clamp()) sin romper los layouts existentes.
 *
 * ── `alPortal`, y por qué hacía falta ────────────────────────────────────────
 *
 * En el resto del ecosistema la marca es la puerta de vuelta: en Membresías el
 * logo del login lleva al portal, y en las cuatro webs la marca de la barra
 * lleva a algún sitio. Aquí no llevaba a ninguna parte — o peor: en las
 * pantallas públicas, el único botón que se le parecía («← Inicio») llevaba al
 * formulario de entrar de ESTA app. O sea que quien llegaba a los resultados
 * desde un cartel y quería saber qué es DINAMYT acababa delante de una
 * contraseña que no tiene.
 *
 * Con `alPortal` el logo hace lo que un logo hace en cualquier sitio: llevar a
 * la casa de la marca. Solo se dibuja como enlace si hay portal configurado: en
 * el modo local del día del evento —sin internet— un enlace a dinamyt.org es
 * una pantalla de error esperando a que alguien la toque.
 */
export default function Logo({
  fontSize = "2rem",
  stacked = false,
  soloImagen = false,
  alPortal = false,
  className = "",
  style,
}: {
  fontSize?: string | number;
  stacked?: boolean;
  soloImagen?: boolean;
  alPortal?: boolean;
  className?: string;
  style?: React.CSSProperties;
}) {
  const marca = (
    <span
      className={`logo ${className}`.trim()}
      style={{
        fontSize,
        display: "inline-flex",
        flexDirection: stacked ? "column" : "row",
        alignItems: "center",
        justifyContent: "center",
        gap: stacked ? "0.18em" : "0.26em",
        lineHeight: 1,
        ...style,
      }}
    >
      {/* La imagen ya es la D con fondo transparente: sin bordes ni
          redondeos para que se acople directamente al fondo.

          `logo.png` tiene que seguir siendo de 512x512. Estuvo en 256 y se
          veía pastoso: acordarse de que aquí 1rem = 17px (globals.css fija
          `html { font-size: 106.25% }`), así que el `stacked` de la pantalla
          de carga —2.1em sobre 2.2rem— pide ~78 px de CSS, que en un celular
          de densidad 3.5x son 275 px reales. Con la imagen de 256 el
          navegador tenía que estirarla. Y en el marcador del tatami se pide
          hasta 1.08em sobre 10.5rem, o sea ~193 px de CSS.

          El archivo es el mismo dibujo y el mismo encuadre que `icon-512.png`
          (comprobado: superpuestos difieren menos que el ruido de reescalar),
          así que se puede regenerar desde ahí sin mover nada de sitio. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/logo.png"
        alt=""
        aria-hidden="true"
        style={{
          height: stacked ? "2.1em" : "1.08em",
          width: "auto",
          display: "block",
          flexShrink: 0,
        }}
      />
      {!soloImagen && <span>DINA<em>MYT</em></span>}
    </span>
  );

  if (!alPortal || !PORTAL_URL) return marca;

  // `<a>` y no `<Link>`: el portal está en otro origen y el router de Next no
  // llega ahí. `display: contents` para que el enlace no meta una caja nueva
  // entre el logo y lo que lo coloca — las cabeceras públicas son rejillas y
  // un envoltorio de más las descuadra.
  return (
    <a
      href={PORTAL_URL}
      title="DINAMYT"
      style={{ display: "contents" }}
    >
      {marca}
    </a>
  );
}
