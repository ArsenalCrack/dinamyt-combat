"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { getSocket, disconnectSocket } from "../lib/socket";
import type { Socket } from "socket.io-client";

// ── Combat State Type ──
export interface CombateState {
  nombreHong: string;
  nombreChung: string;
  jueces: Record<string, { hong: number; chung: number }>;
  nombresJueces: Record<string, string>;
  numJueces: number;
  arbHong: number;
  arbChung: number;
  historial: HistorialEntry[];
  kyongHong: number;
  kyongChung: number;
  faltasHong: number;
  faltasChung: number;
  segundos: number;
  segundosMax: number;
  activo: boolean;
  log: LogEntry[];
  alerta12Lanzada: boolean;
  /** Alerta de superioridad visible hasta que el JC la cierre (cerrar_alerta12) */
  alerta12Data?: { hong: string; chung: string; lider: string; diferencia?: string; motivo?: string } | null;
  ronda: string;
  oroResuelto: boolean;
  oroPendienteAprobacion: boolean;
  oroGanadorNombre?: string;
  oroGanadorColor?: "hong" | "chung" | "";
  /** Descripción del punto de oro en espera (técnica, puntos y juez) */
  oroPuntoDetalle?: string;
  ganadorManualColor?: "hong" | "chung" | "";
  ganadorManualMotivo?: string;
  ganadorPendienteCierre?: boolean;
  ganadorPendienteNombre?: string;
  ganadorPendienteColor?: "hong" | "chung" | "";
  ganadorPendienteMotivo?: string;
  _categoria?: string;
  _tatami_activo?: boolean;
  _nombre_categoria?: string;
  _tatami_numero?: number | null;
  _campeonato_nombre?: string | null;
  _campeonato_id?: number | null;
  _combate_llave?: {
    llave_id: number;
    nombre: string;
    /** Índice de ronda, o "bronce" para el partido por el 3er puesto */
    ronda: number | "bronce";
    partido: number;
    ronda_nombre: string;
    comp1: { id: number; nombre: string };
    comp2: { id: number; nombre: string };
  } | null;
  // Árbol de la llave para mostrar en la pantalla pública
  _mostrar_arbol?: boolean;
  _hay_arbol?: boolean;
  _llave_arbol?: {
    llave_id: number;
    nombre: string;
    estructura: import("../lib/api").LlaveEstructura;
  } | null;
  // Grupo de figuras de la cola actualmente activo en el tatami
  _grupo_figuras?: { llave_id: number; nombre: string } | null;
  /** Jueces conectados en este momento: {rol: nombre|null} */
  _roles_conectados?: Record<string, string | null>;
  /** Número de combate del día en este tatami (coordinación con la mesa) */
  _num_combate?: number | null;
  /** Próximos combates de la llave activa (pantalla pública) */
  _proximos_llave?: { ronda_nombre: string; comp1: string; comp2: string }[];
  /** Registros locales de jueces esperando resolución de la mesa */
  _propuestas_local?: Record<string, PropuestaLocal>;
}

export interface PropuestaLocal {
  nombre?: string;
  ts?: number;
  entradas: { ts?: number; etiqueta: string; color: "hong" | "chung"; pts: number }[];
}

export interface HistorialEntry {
  juez: string;
  color: string;
  pts: number;
  nombre: string;
  tiempo?: number;
  ronda?: string;
  /** Hora real ISO del evento (para mostrar y para la firma de anulación) */
  momento?: string;
  esEspecial?: boolean;
  esKyongGo?: boolean;
  esGamJeum?: boolean;
  esDecision?: boolean;
  juez_nombre?: string | null;
  juez_asignacion?: string | null;
}

export interface LogEntry {
  txt: string;
  color: string;
  /** Hora real de la acción (epoch ms) */
  ts: number;
  /** Tiempo del cronómetro del combate en ese momento (segundos restantes) */
  crono?: number | null;
  /** Si el cronómetro corría (true) o estaba en pausa (false) */
  cronoActivo?: boolean;
}

function estadoInicial(): CombateState {
  return {
    nombreHong: "Hong",
    nombreChung: "Chung",
    jueces: {
      j1: { hong: 0, chung: 0 },
      j2: { hong: 0, chung: 0 },
      j3: { hong: 0, chung: 0 },
      j4: { hong: 0, chung: 0 },
    },
    nombresJueces: { j1: "", j2: "", j3: "", j4: "" },
    numJueces: 4,
    arbHong: 0,
    arbChung: 0,
    historial: [],
    kyongHong: 0,
    kyongChung: 0,
    faltasHong: 0,
    faltasChung: 0,
    segundos: 120,
    segundosMax: 120,
    activo: false,
    log: [],
    alerta12Lanzada: false,
    ronda: "r1",
    oroResuelto: false,
    oroPendienteAprobacion: false,
    ganadorManualColor: "",
    ganadorManualMotivo: "",
    ganadorPendienteCierre: false,
    ganadorPendienteNombre: "",
    ganadorPendienteColor: "",
    ganadorPendienteMotivo: "",
  };
}

// ── Scoring Helpers ──
export function promedioEsquinas(state: CombateState, color: "hong" | "chung") {
  if (!state.jueces) return 0;
  const n = state.numJueces || 4;
  // Solo cuentan los jueces activos (igual que calcular_marcador del backend)
  const activos = ["j1", "j2", "j3", "j4"].slice(0, n);
  const sum = activos.reduce(
    (s, id) => s + (state.jueces[id]?.[color] || 0),
    0
  );
  return sum / n;
}

export function marcadorFinal(state: CombateState, color: "hong" | "chung") {
  const esq = promedioEsquinas(state, color);
  const arb = color === "hong" ? state.arbHong : state.arbChung;
  return esq + arb;
}

export function marcadorDisplay(state: CombateState, color: "hong" | "chung") {
  const val = marcadorFinal(state, color);
  if (val === 0) return "0";
  return val.toFixed(1);
}

/**
 * Puntos propios del Juez Central (especiales y faltas). Van APARTE del
 * promedio de esquinas: cambiar la cantidad de jueces promediados jamás
 * altera este valor (una falta de −0.5 sigue siendo −0.5 con 2, 3 o 4 jueces).
 */
export function puntosJuezCentral(state: CombateState, color: "hong" | "chung") {
  return color === "hong" ? state.arbHong : state.arbChung;
}

/** Formatea con signo explícito: "+2", "−0.5", "0" */
export function fmtSigno(v: number) {
  const abs = Number.isInteger(v) ? String(Math.abs(v)) : Math.abs(v).toFixed(1);
  if (v > 0) return `+${abs}`;
  if (v < 0) return `−${abs}`;
  return "0";
}

export function formatTime(seg: number) {
  return `${Math.floor(seg / 60)}:${String(seg % 60).padStart(2, "0")}`;
}

// ── Main Hook ──
export function useCombate(
  tatamiId: number | string | null,
  rol: string,
  /** `undefined` = el ticket todavía no se sabe (ver `useSocketTicket`). */
  token: string | null | undefined
) {
  const [state, setState] = useState<CombateState>(estadoInicial());
  const [connected, setConnected] = useState(false);
  const [hasServerState, setHasServerState] = useState(false);
  const [pendingEvents, setPendingEvents] = useState(0);
  const [socketError, setSocketError] = useState("");
  const [alerts, setAlerts] = useState<{
    alerta12?: { hong: string; chung: string; lider: string; diferencia?: string; motivo?: string };
    ganador?: { nombre: string; color: string; motivo?: string };
    derrota?: { perdedor: string; razon: string };
    faltaFlash?: { ico: string; titulo: string; sub: string; tipoFalta: string };
    rechazo?: { message: string };
  }>({});
  const socketRef = useRef<Socket | null>(null);
  const pendingMap = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const offlineTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [offline, setOffline] = useState(false);
  // Otro dispositivo tomó este rol (el servidor reemplazó esta sesión)
  const [sesionReemplazada, setSesionReemplazada] = useState(false);
  // La mesa aplicó o descartó el registro local de un juez (contador para
  // que el mismo rol pueda resolverse varias veces)
  const [registroResuelto, setRegistroResuelto] = useState<
    { rol: string; aplicado: boolean; n: number } | null
  >(null);
  const registroResueltoSeq = useRef(0);
  const huboConexionRef = useRef(false);

  // Conectar al tatami
  useEffect(() => {
    if (!tatamiId) return;
    // Quien puntúa espera a saber con qué credencial entra: el servidor ya no
    // deja tomar un papel de juez sin ella (25 sep 2026). La pantalla, no.
    if (token === undefined && rol !== "pantalla") return;

    const sock = getSocket(tatamiId, rol, token ?? null);
    socketRef.current = sock;

    const clearOfflineTimer = () => {
      if (offlineTimerRef.current) {
        clearTimeout(offlineTimerRef.current);
        offlineTimerRef.current = null;
      }
    };
    const marcarConectado = () => {
      huboConexionRef.current = true;
      clearOfflineTimer();
      setConnected(true);
      setOffline(false);
      setSocketError("");
      // Tras cualquier reconexión, pedir el estado completo del tatami
      // (el servidor también lo envía en connect; esto es doble seguro).
      sock.emit("pedir");
    };
    const marcarDesconectado = () => {
      setConnected(false);
      // OJO: no reiniciar el conteo si ya hay uno corriendo. Cada reintento
      // fallido dispara connect_error (cada 1-3 s) y reiniciarlo aquí hacía
      // que el corte NUNCA se confirmara: pantallas y jueces quedaban en
      // "Cargando…" para siempre. El corte se confirma a los N segundos del
      // PRIMER fallo; el timer se limpia al reconectar (marcarConectado).
      if (offlineTimerRef.current) return;
      const espera = huboConexionRef.current ? 3000 : 6000;
      offlineTimerRef.current = setTimeout(() => {
        setOffline(true);
        offlineTimerRef.current = null;
      }, espera);
    };

    sock.on("connect", marcarConectado);
    sock.on("disconnect", marcarDesconectado);
    sock.on("connect_error", (err: Error) => {
      marcarDesconectado();
      setSocketError(err.message || "No se pudo conectar al tatami");
    });

    // El mismo rol se conectó desde otra pantalla/dispositivo: NO pelear la
    // conexión (evita el ping-pong de desconexiones entre los dos). El juez
    // decide retomar aquí con reconectar().
    sock.on("sesion_reemplazada", () => {
      setSesionReemplazada(true);
      sock.disconnect();
    });

    // La mesa resolvió el registro local de un juez (aplicado o descartado)
    sock.on("registro_local_resuelto", (data: { rol: string; aplicado: boolean }) => {
      registroResueltoSeq.current += 1;
      setRegistroResuelto({
        rol: data.rol,
        aplicado: Boolean(data.aplicado),
        n: registroResueltoSeq.current,
      });
    });

    if (sock.connected) {
      marcarConectado();
    } else {
      marcarDesconectado();
    }

    sock.on("estado", (data: { datos: CombateState }) => {
      setHasServerState(true);
      if (pendingMap.current.size === 0) {
        setState(data.datos);
      }
    });

    // Tick ligero del cronómetro del servidor: solo viaja el segundero (el
    // estado completo con log e historial pesa demasiado para ir cada
    // segundo a todos los dispositivos). Se fusiona sobre el estado actual.
    sock.on("crono", (data: { segundos: number; activo: boolean }) => {
      setState((prev) => ({ ...prev, segundos: data.segundos, activo: data.activo }));
    });

    sock.on("estado_confirmado", (data: { datos: CombateState }) => {
      setHasServerState(true);
      setState(data.datos);
      // Clear all pending
      pendingMap.current.forEach((timer) => clearTimeout(timer));
      pendingMap.current.clear();
      setPendingEvents(0);
    });

    sock.on("accion_rechazada", (data: { message?: string }) => {
      setAlerts((prev) => ({
        ...prev,
        rechazo: { message: data.message || "Acción rechazada" },
      }));
    });

    sock.on("ack", (data: { evId: string }) => {
      const timer = pendingMap.current.get(data.evId);
      if (timer) {
        clearTimeout(timer);
        pendingMap.current.delete(data.evId);
        setPendingEvents(pendingMap.current.size);
      }
    });

    // Pedir estado inicial
    sock.emit("pedir");

    const pending = pendingMap.current;
    return () => {
      clearOfflineTimer();
      pending.forEach((timer) => clearTimeout(timer));
      pending.clear();
      setPendingEvents(0);
      disconnectSocket();
      setConnected(false);
      setHasServerState(false);
      setSocketError("");
    };
  }, [tatamiId, rol, token]);

  // Event-specific listeners (separate effect to avoid re-binding on state change)
  useEffect(() => {
    const sock = socketRef.current;
    if (!sock) return;

    const onAlerta12 = (data: { hong: string; chung: string; lider: string; diferencia?: string; motivo?: string }) => {
      setAlerts((prev) => ({ ...prev, alerta12: data }));
    };
    const onGanador = (data: { nombre: string; color: string; motivo?: string }) => {
      setAlerts((prev) => ({ ...prev, ganador: data }));
    };
    const onDerrota = (data: { perdedor: string; razon: string }) => {
      setAlerts((prev) => ({ ...prev, derrota: data }));
    };
    const onFaltaFlash = (data: {
      data?: { ico: string; titulo: string; sub: string; tipo?: string; tipoFalta?: string };
      ico?: string;
      titulo?: string;
      sub?: string;
      tipo?: string;
      tipoFalta?: string;
    }) => {
      const payload = data.data || data;
      setAlerts((prev) => ({
        ...prev,
        faltaFlash: {
          ico: payload.ico || "",
          titulo: payload.titulo || "",
          sub: payload.sub || "",
          tipoFalta: payload.tipoFalta || payload.tipo || "adv",
        },
      }));
      // Auto-clear after 3s
      setTimeout(() => setAlerts((prev) => ({ ...prev, faltaFlash: undefined })), 3000);
    };

    sock.on("alerta12", onAlerta12);
    sock.on("ganador-flash", onGanador);
    sock.on("derrota", onDerrota);
    sock.on("falta-flash", onFaltaFlash);

    return () => {
      sock.off("alerta12", onAlerta12);
      sock.off("ganador-flash", onGanador);
      sock.off("derrota", onDerrota);
      sock.off("falta-flash", onFaltaFlash);
    };
  }, [tatamiId]);

  // ── Send Event ──
  const enviarEvento = useCallback(
    (accion: string, datos: Record<string, unknown> = {}) => {
      const sock = socketRef.current;
      if (!sock) return;

      const evId = `${rol}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      const evento = { accion, ...datos };

      // Reintentos limitados: si nunca llega el ACK, soltar el evento para
      // no bloquear indefinidamente las actualizaciones de estado del servidor.
      const MAX_REINTENTOS = 3;
      const scheduleRetry = (intento: number) => {
        const timer = setTimeout(() => {
          if (!pendingMap.current.has(evId)) return;
          if (intento >= MAX_REINTENTOS) {
            pendingMap.current.delete(evId);
            setPendingEvents(pendingMap.current.size);
            return;
          }
          socketRef.current?.emit("evento", { evId, evento });
          scheduleRetry(intento + 1);
        }, 2000);
        pendingMap.current.set(evId, timer);
      };

      scheduleRetry(1);
      setPendingEvents(pendingMap.current.size);

      // The server will confirm with estado_confirmado.
      sock.emit("evento", { evId, evento });
    },
    [rol]
  );

  // ── Broadcast Event (no state change) ──
  const broadcast = useCallback(
    (data: Record<string, unknown>) => {
      socketRef.current?.emit("broadcast", data);
    },
    []
  );

  // ── Clear Alerts ──
  const clearAlert = useCallback((key: string) => {
    setAlerts((prev) => ({ ...prev, [key]: undefined }));
  }, []);

  // ── Retomar la sesión aquí (tras un takeover desde otro dispositivo) ──
  const reconectar = useCallback(() => {
    setSesionReemplazada(false);
    socketRef.current?.connect();
  }, []);

  return {
    state,
    connected,
    /** Corte de conexión confirmado (tras el período de gracia) */
    offline,
    /** Otro dispositivo tomó este rol; reconectar() lo retoma aquí */
    sesionReemplazada,
    reconectar,
    /** Última resolución de un registro local por la mesa */
    registroResuelto,
    hasServerState,
    socketError,
    pendingEvents,
    enviarEvento,
    broadcast,
    alerts,
    clearAlert,
  };
}
