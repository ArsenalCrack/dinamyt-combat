"use client";

import { useEffect } from "react";
import {
  aplicarTema,
  escucharTemaDelSistema,
  hayModoElegido,
  refrescarDesdeLaCookie,
  type Tema,
} from "@/lib/theme";
import { leerAparienciaDeLaCuenta } from "@/lib/api";
import { haySesionProbable } from "@/lib/sesion";
import { hayIdiomaElegido, idiomaDeLaCookie, useI18n } from "@/lib/i18n";

/**
 * El tema y el idioma, al dia en TODAS las pantallas.
 *
 * ── Los dos huecos que cierra ──────────────────────────────────────────────
 *
 * **1. La vuelta.** Lo que se elige aqui ya viaja a las otras apps
 * (`guardarAparienciaEnLaCuenta`), pero al reves no: la preferencia llegaba
 * DENTRO DEL PASE, y esta app solo ve el pase en un momento —el salto desde el
 * portal—. Quien tenia la sesion de aqui abierta desde ayer y cambiaba el modo
 * claro en DINAMYT no veia nada al volver. Esa es la mitad que faltaba de
 * «unas veces se recuerda y otras no».
 *
 * Ahora se PREGUNTA al cargar. Se pinta primero con lo que ya hay —la copia
 * local, que es lo que evita el fogonazo— y se corrige despues.
 *
 * **2. El tema del sistema, en vivo.** `sistema` es el valor por defecto, y
 * `prefers-color-scheme` se consultaba una sola vez al pintar: el telefono que
 * pasa a modo oscuro solo al anochecer se quedaba claro hasta que alguien
 * recargara. Ver `escucharTemaDelSistema`.
 *
 * ── Por que NO se pregunta sin sesion ──────────────────────────────────────
 *
 * Porque un 401 en esta app no es inocuo: el interceptor de `api` lo entiende
 * como «te caduco la sesion» y **recarga hacia el login**. Las pantallas
 * publicas —el marcador del tatami, los resultados— se ven sin entrar y a
 * menudo proyectadas en una pared: preguntar el color de la pantalla no puede
 * mandar el marcador al login en mitad de un combate.
 *
 * `haySesionProbable` mira la cookie CSRF, que viaja al lado de la de sesion.
 * Es una pista y basta: si se equivoca por exceso, lo unico que pasa es que se
 * pregunta de mas y se ignora la respuesta.
 */
export function AplicarApariencia() {
  const { setIdioma } = useI18n();

  // ── El tema del sistema, mientras la eleccion sea `sistema` ──────────────
  useEffect(() => escucharTemaDelSistema(), []);

  // ── La cookie compartida, cada vez que se vuelve a esta pestaña ──────────
  //
  // Es la pieza que faltaba, y la que de verdad arregla «lo cambio en una app y
  // en la otra sigue igual». La cookie `.dinamyt.org` reparte la elección a las
  // cuatro webs en el acto, pero solo se LEE al arrancar la página: una pestaña
  // abierta desde hace media hora no vuelve a mirarla nunca.
  //
  // La consulta al servidor de abajo parecía cubrirlo, pero su guarda
  // `hayModoElegido()` es cierta en cuanto exista la cookie, o sea siempre que
  // alguien haya elegido modo alguna vez en este navegador. La sincronización
  // estaba tapiada por su propia guarda.
  //
  // Aquí no hace falta guarda: la cookie ES la última elección de esta persona
  // en este navegador, en cualquiera de las cuatro apps. Aplicarla no puede
  // pisar nada más reciente, porque no hay nada más reciente. Y va sin sesión
  // también: las pantallas públicas se ven sin entrar y también tienen que
  // respetar el modo claro.
  useEffect(() => {
    const releer = () => {
      refrescarDesdeLaCookie();
      const idi = idiomaDeLaCookie();
      if (idi) setIdioma(idi);
    };
    // Al VOLVER a la pestania, no al esconderla: `visibilitychange` avisa de
    // los dos, y releer al irse no le sirve a nadie.
    const alVolver = () => {
      if (document.visibilityState === "visible") releer();
    };
    document.addEventListener("visibilitychange", alVolver);
    // Y `focus` además de `visibilitychange`: cambiar de VENTANA —dos ventanas
    // lado a lado, o la app instalada junto al navegador— no siempre dispara el
    // segundo, y ese es justo el caso de quien tiene dos apps abiertas a la vez.
    // `focus` va SIN la comprobacion de visibilidad, y a proposito: hay
    // contextos donde `visibilityState` dice `hidden` aunque la ventana este
    // delante —una vista incrustada, un panel lateral, algun navegador
    // embebido—, y ahi la comprobacion dejaba el refresco muerto. Recibir el
    // foco ya significa que alguien esta mirando; leer una cookie es gratis.
    window.addEventListener("focus", releer);
    return () => {
      document.removeEventListener("visibilitychange", alVolver);
      window.removeEventListener("focus", releer);
    };
  }, [setIdioma]);

  // ── Y lo que diga la cuenta, que es la verdad ────────────────────────────
  useEffect(() => {
    if (!haySesionProbable()) return;
    let vigente = true;

    async function confirmar() {
      const eco = await leerAparienciaDeLaCuenta();
      if (!vigente || !eco) return;

      // ⚠️ Solo si este navegador NO tiene ya una eleccion. Sin esta guarda,
      // esta funcion era la que borraba el idioma: se elegia ingles en el menu
      // —que hasta ahora ni siquiera lo guardaba en la cuenta—, y al primer
      // `visibilitychange` el servidor contestaba `es-CO` y la pantalla volvia
      // a espaniol sola. Se reporto como «el idioma no cambia».
      if (
        !hayModoElegido() &&
        (eco.theme === "claro" || eco.theme === "oscuro" || eco.theme === "sistema")
      ) {
        aplicarTema(eco.theme as Tema);
      }
      if (!hayIdiomaElegido() && eco.locale) {
        setIdioma(eco.locale.toLowerCase().startsWith("en") ? "en" : "es");
      }
    }

    void confirmar();

    // Y al volver a la pestana. Es el momento en que de verdad pasa: se cambia
    // el modo en el portal, se vuelve a la pestana de aqui que llevaba abierta
    // toda la tarde, y hasta ahora seguia como estaba.
    const alVolver = () => {
      if (document.visibilityState === "visible") void confirmar();
    };
    document.addEventListener("visibilitychange", alVolver);
    return () => {
      vigente = false;
      document.removeEventListener("visibilitychange", alVolver);
    };
  }, [setIdioma]);

  return null;
}
