/**
 * Dónde aterriza cada rol al entrar.
 *
 * Vivía copiado en tres sitios —el login, la portada y la barra—, y el propio
 * login ya avisaba de que dos copias es cómo un rol acaba entrando a la
 * pantalla de otro. Con el competidor (F3) eran tres copias que cambiar a la
 * vez, y la que se olvidara lo mandaba al panel del juez: es lo que se hace
 * con todo rol que no se conoce.
 */
export function destinoDe(rol: string | null | undefined): string {
  if (rol === "admin") return "/admin";
  if (rol === "maestro") return "/maestro";
  if (rol === "competidor") return "/mi-panel";
  return "/juez";
}
