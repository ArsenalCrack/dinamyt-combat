"use client";

import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { LIM } from "@/lib/limites";

/**
 * Campo de contraseña con el "ojo" para verla.
 *
 * ── Por qué un botón propio y no el del navegador ──
 *
 * Solo Edge dibuja un ojo por su cuenta (`::-ms-reveal`), y únicamente en
 * escritorio: en Chrome, Firefox, Safari y en cualquier navegador de celular
 * NO existe. Quien teclea su contraseña a ciegas en un móvil —que es como se
 * usa esto en el tatami— no tenía forma de comprobar lo que escribió.
 *
 * El de Edge se oculta en `globals.css`: si no, ese navegador enseñaría DOS
 * ojos, el suyo y el nuestro, uno encima del otro.
 *
 * Acepta las mismas props que un `<input>` (`value`, `onChange`, `required`,
 * `autoComplete`…) para poder sustituir uno sin tocar nada más alrededor.
 */

type Props = Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> & {
  /**
   * Arranca visible. Para las contraseñas que se FIJAN (el admin creando una
   * cuenta), donde el punto es poder leer en voz alta lo que se está poniendo;
   * en las que se COMPRUEBAN (login) arranca oculta, como debe ser.
   */
  verInicial?: boolean;
};

/** Propiedades de margen que se llevan al envoltorio en vez de al campo. */
const CLAVES_MARGEN = new Set([
  "margin", "marginTop", "marginBottom", "marginLeft", "marginRight",
  "marginBlock", "marginBlockStart", "marginBlockEnd",
  "marginInline", "marginInlineStart", "marginInlineEnd",
]);

/**
 * Reparte el estilo recibido: los márgenes al envoltorio, el resto al campo.
 *
 * Los márgenes tienen que ir fuera porque el ojo se centra respecto al
 * envoltorio, y un `marginBottom` dentro lo dejaría flotando por encima del
 * campo.
 *
 * ── Por qué se copian las claves una a una ──
 *
 * La primera versión desestructuraba (`const { margin, marginTop, … } = style`)
 * y volvía a montar el objeto con las once claves. Las que no venían quedaban
 * en `undefined`, y ahí está la trampa: al montar en el navegador, React aplica
 * las propiedades UNA A UNA sobre `node.style`, y a las que valen `undefined`
 * les hace `setProperty(nombre, "")` — o sea, las BORRA. Como `margin` es un
 * atajo que expande a las cuatro longhands, escribir el atajo y limpiar
 * `marginTop`/`marginBottom`/… justo después dejaba el margen en cero.
 *
 * En el servidor no se nota —ahí el estilo se serializa a texto y los
 * `undefined` se omiten—, así que la pantalla salía bien al abrirla directa y
 * MAL al llegar por navegación interna. Se descubrió en dinamyt-membresias, con
 * el botón de entrar pegado al campo de contraseña al volver del cierre de
 * sesión; aquí no se veía porque ningún formulario le pasa márgenes, pero el
 * fallo era el mismo.
 *
 * Copiando solo lo que de verdad viene, no hay ningún `undefined` que borre
 * nada.
 */
function repartirEstilo(style?: React.CSSProperties): {
  envoltorio: React.CSSProperties;
  campo: React.CSSProperties;
} {
  const envoltorio: Record<string, unknown> = {};
  const campo: Record<string, unknown> = {};
  for (const [clave, valor] of Object.entries(style ?? {})) {
    if (CLAVES_MARGEN.has(clave)) envoltorio[clave] = valor;
    else campo[clave] = valor;
  }
  return { envoltorio, campo };
}

export default function CampoContrasena({
  verInicial = false,
  className = "input",
  style,
  // El tope viene de fábrica: son los 72 bytes que mira bcrypt, y lo que se
  // escriba de ahí en adelante no forma parte de la contraseña. Dejarlo teclear
  // es enseñar una seguridad que no existe.
  maxLength = LIM.password,
  ...props
}: Props) {
  const { t } = useI18n();
  const [ver, setVer] = useState(verInicial);

  const { envoltorio: estiloEnvoltorio, campo: estiloCampo } = repartirEstilo(style);

  return (
    <span className="campo-pass" style={estiloEnvoltorio}>
      <input
        {...props}
        maxLength={maxLength}
        type={ver ? "text" : "password"}
        className={className}
        style={{ ...estiloCampo, margin: 0, paddingRight: 46 }}
      />
      <button
        type="button"
        className="campo-pass-ojo"
        // `tabIndex={-1}`: quien recorre el formulario con Tab espera pasar del
        // campo al botón de enviar, no a un interruptor de visibilidad.
        tabIndex={-1}
        aria-label={ver ? t("campo.ocultarContrasena") : t("campo.verContrasena")}
        aria-pressed={ver}
        title={ver ? t("campo.ocultarContrasena") : t("campo.verContrasena")}
        onClick={() => setVer((v) => !v)}
      >
        {/* SVG y no un emoji: 👁 se dibuja distinto (o no se dibuja) según el
            sistema, y en Android sale de color. Esto se ve igual en todos. */}
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path
            d="M1.5 12S5 5.5 12 5.5 22.5 12 22.5 12 19 18.5 12 18.5 1.5 12 1.5 12Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle
            cx="12"
            cy="12"
            r="3.2"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
          />
          {ver && (
            <path
              d="M4 20 20 4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
            />
          )}
        </svg>
      </button>

      <style>{`
        .campo-pass {
          position: relative;
          display: block;
          width: 100%;
        }
        /* display:block y no el inline-block por defecto del input: si no, el
           envoltorio se lleva la línea base de texto de propina (unos píxeles
           por debajo) y el ojo, centrado sobre él, queda descuadrado. */
        .campo-pass > input {
          display: block;
          width: 100%;
        }
        .campo-pass-ojo {
          position: absolute;
          top: 50%;
          right: 6px;
          transform: translateY(-50%);
          width: 36px;
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 0;
          background: transparent;
          border: none;
          border-radius: var(--radius-sm);
          color: var(--text-dim);
          cursor: pointer;
          transition: var(--transition);
        }
        .campo-pass-ojo:hover,
        .campo-pass-ojo:focus-visible {
          color: var(--gold);
          background: var(--gold-bg);
          outline: none;
        }
        .campo-pass-ojo[aria-pressed="true"] {
          color: var(--gold);
        }
      `}</style>
    </span>
  );
}
