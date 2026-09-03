/**
 * ── Cuánto se puede ESCRIBIR en cada campo ──────────────────────────────────
 *
 * Los campos de esta consola no tenían tope: se podía teclear —o pegar— sin
 * fin en el nombre de un competidor, en el de un campeonato o en la contraseña
 * del login. Lo que pasa después no es un error bonito: la columna corta por su
 * cuenta, o el servidor contesta un 500 que no menciona ningún campo.
 *
 * Los números son los de las columnas, o los del uso real cuando la columna es
 * `text`. **Nunca son más estrictos que el servidor**: un campo que corta antes
 * de lo que la API acepta deja a alguien sin poder escribir su propio apellido.
 *
 * Es el gemelo de `LIM` en Membresías (`lib/campos.ts`) y en el portal
 * (`lib/validacion.ts`).
 */
export const LIM = {
  /** El nombre de una persona: competidor, juez, maestro. */
  nombrePersona: 150,
  correo: 200,
  /** bcrypt solo mira los primeros 72 bytes; más allá es decorado. */
  password: 72,
  /** Nombre de un campeonato o de un club. */
  titulo: 120,
  /** Una descripción corta, no un reglamento. */
  descripcion: 300,
  /** Una nota de figuras: `8.50`. Cinco caracteres sobran. */
  nota: 5,
  /** Cuadro de búsqueda: no viaja a ninguna columna, pero tampoco es infinito. */
  busqueda: 80,
} as const;
