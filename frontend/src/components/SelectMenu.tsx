"use client";

import {
  useEffect, useRef, useState, type CSSProperties, type KeyboardEvent,
} from "react";
import { useI18n } from "@/lib/i18n";

export interface SelectMenuOption {
  value: string;
  label: string;
}

/**
 * Desplegable propio con el panel dorado del software. Reemplaza a los
 * `<select>` con `appearance: base-select` (la función de selects
 * personalizables de Chrome/Edge): esa es muy nueva y su panel se queda abierto
 * sin poder cerrarse al volver a tocarlo o al hacer clic fuera —el menú "se
 * traba"—. Aquí el abrir/cerrar es estado de React puro, así que SIEMPRE se
 * pliega: con clic en una opción, clic fuera o tecla Escape. Pensado para los
 * menús de categoría de figuras (Defensa Personal, etc.).
 */
export default function SelectMenu({
  value, onChange, options, ariaLabel, placeholder,
  style, buttonStyle, centerLabel = false,
}: {
  value: string;
  onChange: (value: string) => void;
  options: SelectMenuOption[];
  ariaLabel?: string;
  placeholder?: string;
  /** Estilo del contenedor (p. ej. `flex` dentro de una fila). */
  style?: CSSProperties;
  /** Estilo del botón disparador (p. ej. color de borde de validación). */
  buttonStyle?: CSSProperties;
  /** Centra la etiqueta (usado en el panel del Juez Central). */
  centerLabel?: boolean;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [activo, setActivo] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const seleccionada = options.find((o) => o.value === value);

  // Cerrar al hacer clic fuera o tocar fuera (mouse y táctil)
  useEffect(() => {
    if (!open) return;
    function fuera(e: MouseEvent | TouchEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", fuera);
    document.addEventListener("touchstart", fuera);
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("touchstart", fuera);
    };
  }, [open]);

  function abrir() {
    const idx = options.findIndex((o) => o.value === value);
    setActivo(idx < 0 ? 0 : idx);
    setOpen(true);
  }

  function elegir(v: string) {
    onChange(v);
    setOpen(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      setOpen(false);
      return;
    }
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        abrir();
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActivo((i) => Math.min(i + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActivo((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const opt = options[activo];
      if (opt) elegir(opt.value);
    }
  }

  return (
    <div
      ref={rootRef}
      className="selectmenu"
      style={{ position: "relative", ...style }}
      onKeyDown={onKeyDown}
    >
      <button
        type="button"
        className="input selectmenu-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => (open ? setOpen(false) : abrir())}
        style={buttonStyle}
      >
        <span
          className="selectmenu-label"
          style={centerLabel ? { flex: 1, textAlign: "center" } : undefined}
        >
          {seleccionada ? seleccionada.label : (placeholder ?? t("comun.selecciona"))}
        </span>
        <span className="selectmenu-arrow" aria-hidden="true" data-open={open}>▼</span>
      </button>

      {open && (
        <ul className="selectmenu-panel" role="listbox" aria-label={ariaLabel}>
          {options.map((o, i) => (
            <li
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              className="selectmenu-option"
              data-activa={i === activo}
              onMouseEnter={() => setActivo(i)}
              onClick={() => elegir(o.value)}
            >
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
