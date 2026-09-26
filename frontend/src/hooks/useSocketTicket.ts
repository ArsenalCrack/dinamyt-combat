"use client";

import { useEffect, useState } from "react";
import { obtenerSocketTicketAPI } from "@/lib/api";
import { haySesionProbable, obtenerToken } from "@/lib/sesion";

/**
 * Credencial para abrir el Socket.IO del tatami.
 *
 * El socket manda su token en el payload `auth`, así que necesita un valor
 * legible desde JavaScript — y la sesión ahora vive en una cookie httpOnly que
 * no lo es. Se pide entonces un "ticket" al backend (token de 12 h, ver
 * `/api/auth/socket-ticket`), que se queda en memoria.
 *
 * Tres valores, y la diferencia importa desde el 25 sep 2026:
 *
 *  · `undefined` — todavía se está averiguando. Un juez NO conecta aún: el
 *    servidor ya no deja puntuar sin identidad (`_motivo_para_no_puntuar`), y
 *    conectar sin ticket para reconectar un instante después le enseñaba
 *    «rol no disponible» antes de su tatami.
 *  · `null` — no hay credencial. Es lo normal en la pantalla pública, que
 *    conecta sin identidad y solo mira. Un juez con `null` conecta igual y el
 *    servidor le dice por qué no puede (sesión caducada: volver a escanear).
 *  · el ticket.
 */
export function useSocketTicket(): string | null | undefined {
  const [ticket, setTicket] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    let cancelado = false;
    const poner = (valor: string | null) => {
      if (!cancelado) setTicket(valor);
    };

    // Recién iniciada la sesión el token ya está en memoria: no hace falta
    // pedir nada. Al recargar se ha perdido, y ahí sí se pide.
    const enMemoria = obtenerToken();
    if (enMemoria) {
      queueMicrotask(() => poner(enMemoria));
    } else if (!haySesionProbable()) {
      queueMicrotask(() => poner(null));
    } else {
      obtenerSocketTicketAPI()
        .then((t) => poner(t))
        // Sin ticket el servidor dirá por qué (ver arriba), en vez de dejar
        // la pantalla esperando para siempre.
        .catch(() => poner(null));
    }

    return () => {
      cancelado = true;
    };
  }, []);

  return ticket;
}
