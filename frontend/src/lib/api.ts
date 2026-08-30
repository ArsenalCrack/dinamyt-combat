"use client";

import axios from "axios";
import { limpiarSesion, obtenerToken, tokenCsrf } from "./sesion";

// Despliegue local (LAN): el navegador habla DIRECTO con el backend (puerto
// 5000, mismo host que la página) en vez de pasar por el proxy de Next. Menos
// saltos = menos puntos de falla; el CORS del backend ya acepta cualquier
// origen de la red privada y abrir-firewall.bat abre el puerto 5000.
const BACKEND_PORT = process.env.NEXT_PUBLIC_BACKEND_PORT || "5000";

/**
 * ¿Se consume la API por el MISMO origen que la web (`/api`, vía el rewrite de
 * next.config) o directo contra el backend?
 *
 * En la nube (Vercel + Render) tiene que ser por el proxy: web y backend están
 * en dominios distintos, así que sin él la cookie de sesión sería de terceros
 * — Safari la bloquea y Firefox la aísla — y la sesión se pierde en cada
 * recarga. En la LAN va directo: mismo host, la cookie ya es de primera parte,
 * y el proxy sería un punto único de falla con decenas de dispositivos.
 *
 * Se decide solo, según si el despliegue configuró el proxy (`BACKEND_URL`).
 * `NEXT_PUBLIC_API_MODE` ("proxy" | "directo") lo fuerza si hace falta.
 */
function usarProxy(): boolean {
  if (process.env.NEXT_PUBLIC_API_MODE === "proxy") return true;
  if (process.env.NEXT_PUBLIC_API_MODE === "directo") return false;
  return process.env.DINAMYT_PROXY_LISTO === "1";
}

export function resolverApiUrl(): string {
  // Cadena vacía = rutas relativas: baseURL queda en "/api", el mismo origen.
  // Va ANTES de NEXT_PUBLIC_API_URL: si el proxy está configurado, apuntar el
  // navegador a un dominio absoluto es exactamente lo que rompe la sesión.
  if (usarProxy()) return "";
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:${BACKEND_PORT}`;
  }
  return "http://localhost:5000";
}

const API_URL = resolverApiUrl();

// Idioma elegido (persistido por i18n en localStorage). Se envía como ?lang=
// en las descargas para que el backend genere el archivo en ese idioma.
export function idiomaArchivo(): "es" | "en" {
  if (typeof window === "undefined") return "es";
  try {
    return localStorage.getItem("dinamyt_lang") === "en" ? "en" : "es";
  } catch {
    return "es";
  }
}

const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: { "Content-Type": "application/json" },
  // En LAN la respuesta es inmediata: si en 20 s no contestó, el servidor está
  // caído y conviene enterarse rápido (activa el modo local) en vez de dejar
  // pantallas de carga colgadas.
  timeout: 20000,
  // Hace que la cookie de sesión viaje (y que el navegador acepte la que
  // devuelve el login) aunque el backend esté en otro puerto.
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  // La cookie httpOnly va sola. La cabecera solo hace falta cuando quedó el
  // token en memoria (QR de acceso, o cookie bloqueada por ser de terceros).
  const token = obtenerToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // Doble envío de CSRF: el backend compara esta cabecera con la cookie
  // csrf_access_token. Solo lo exige en lo que cambia estado y entra por
  // cookie, así que en GET sobra.
  const metodo = (config.method || "get").toUpperCase();
  if (metodo !== "GET" && metodo !== "HEAD" && metodo !== "OPTIONS") {
    const csrf = tokenCsrf();
    if (csrf) config.headers["X-CSRF-TOKEN"] = csrf;
  }
  return config;
});

/**
 * Evento con el que cualquier petición avisa de que el sistema está en
 * mantenimiento. Lo escucha `<PorteroMantenimiento>` para enseñar la pantalla
 * de aviso al instante, sin esperar a su siguiente sondeo.
 */
export const EVENTO_MANTENIMIENTO = "dinamyt:mantenimiento";

// Interceptor: si recibimos 401, limpiar sesión
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      limpiarSesion();
      // Redirigir a login si no estamos ya ahí
      if (!window.location.pathname.includes("/login")) {
        window.location.href = "/login";
      }
    }
    // 503 con la marca del backend = mantenimiento, no un servidor caído. Se
    // avisa a la app entera; la sesión NO se toca, que es todo el punto de
    // este modo: al terminar, cada quien sigue donde estaba.
    if (
      error.response?.status === 503
      && error.response?.data?.mantenimiento
      && typeof window !== "undefined"
    ) {
      window.dispatchEvent(new CustomEvent(EVENTO_MANTENIMIENTO));
    }
    return Promise.reject(error);
  }
);

// ── Modo mantenimiento ──
export interface EstadoMantenimiento {
  activo: boolean;
  mensaje: string | null;
  /** ISO-8601 de cuándo se encendió, o null si está apagado. */
  desde: string | null;
  /** Si QUIEN PREGUNTA puede seguir usando la app (solo el superadmin). */
  exento: boolean;
}

/** Estado del mantenimiento. Ruta pública: responde con o sin sesión. */
export async function obtenerMantenimientoAPI() {
  const res = await api.get("/mantenimiento");
  return res.data as EstadoMantenimiento;
}

/** Enciende o apaga el mantenimiento (solo superadmin). */
export async function fijarMantenimientoAPI(activo: boolean, mensaje?: string) {
  const res = await api.put("/mantenimiento", { activo, mensaje: mensaje ?? "" });
  return res.data as EstadoMantenimiento;
}

// ── Auth API ──
export async function loginAPI(email: string, password: string) {
  const res = await api.post("/auth/login", { email, password });
  return res.data as { token: string; user: UserData };
}

/** Lo que se sabe después de intentar salir. Lo lee el botón de Salir. */
export interface Salida {
  /**
   * Si el servidor confirmó el cierre. En `false` la cookie httpOnly PUEDE
   * seguir viva —solo el servidor puede borrarla—, así que quien llame tiene
   * que contar con que la sesión no está cerrada del todo.
   */
  confirmada: boolean;
  /**
   * Si esta instalación habla con el ecosistema y por tanto hay una segunda
   * sesión que cerrar (la del portal). `null` cuando el servidor no contestó.
   */
  portal: boolean | null;
}

/**
 * Cierra la sesión en el servidor: la cookie httpOnly solo la borra él.
 *
 * **El fallo ya no se traga en silencio.** Antes, si la llamada no salía —el
 * backend reiniciándose, un 503 de mantenimiento, un corte de red— esto
 * limpiaba lo local y devolvía como si todo hubiera ido bien. La cookie seguía
 * valiendo, así que la persona salía a una pantalla que ya no era la suya con
 * la sesión intacta detrás. Ahora se devuelve lo que de verdad pasó, y
 * `/login?salida=…` remata el cierre si hizo falta.
 */
export async function logoutAPI(): Promise<Salida> {
  let salida: Salida = { confirmada: false, portal: null };
  try {
    const res = await api.post("/auth/logout");
    const data = res.data as { ok?: boolean; portal?: boolean };
    salida = { confirmada: true, portal: data?.portal ?? null };
  } catch {
    // La sesión local se limpia igual: dejar a alguien "dentro" porque falló
    // la red sería peor. Lo que NO se hace es dar el cierre por bueno.
  }
  limpiarSesion();
  return salida;
}

/** Token corto para abrir el Socket.IO (ver hooks/useSocketTicket). */
export async function obtenerSocketTicketAPI(): Promise<string> {
  const res = await api.post("/auth/socket-ticket");
  return (res.data as { ticket: string }).ticket;
}

/**
 * Convierte un token de cabecera en cookie de sesión.
 *
 * Lo usa el acceso por QR: el enlace trae el token en el fragmento de la URL,
 * y en vez de guardarlo en localStorage se canjea aquí por la cookie httpOnly.
 */
export async function abrirSesionConToken(token: string) {
  const res = await api.post("/auth/sesion", null, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.data as { user: UserData };
}

export async function registerUserAPI(data: {
  email: string;
  password: string;
  nombre: string;
  rol: string;
  /** Dojangs del maestro, cada uno con su delegación. El primero es el principal. */
  clubes?: ClubMaestro[];
  puede_juzgar?: boolean;
}) {
  const res = await api.post("/auth/register", data);
  return res.data;
}

export async function getMeAPI() {
  const res = await api.get("/auth/me");
  return res.data as UserData;
}

export async function listUsersAPI(includeInactive = false) {
  const res = await api.get("/auth/users", {
    params: includeInactive ? { include_inactive: "1" } : {},
  });
  return res.data as UserData[];
}

export async function deleteUserAPI(id: number) {
  const res = await api.delete(`/auth/users/${id}`);
  return res.data;
}

export async function updateUserAPI(
  id: number,
  data: {
    nombre?: string; email?: string; password?: string; activo?: boolean;
    rol?: string; clubes?: ClubMaestro[]; puede_juzgar?: boolean;
  }
) {
  const res = await api.put(`/auth/users/${id}`, data);
  return res.data;
}

// Clubes de los maestros del workspace (para el desplegable de club al inscribir)
export async function listClubesAPI() {
  const res = await api.get("/auth/clubes");
  return res.data as string[];
}

/**
 * Lo mismo, pero con la delegación de cada club. Al asignarle a un maestro un
 * dojang que ya existe, se rellena la ciudad que ese dojang ya tiene en vez de
 * volver a elegirla — que es como el mismo club acaba en dos ciudades.
 */
export async function listClubesDetalleAPI() {
  const res = await api.get("/auth/clubes", { params: { detalle: "1" } });
  return res.data as ClubMaestro[];
}

// ── Campeonatos API ──
export async function listCampeonatosAPI() {
  const res = await api.get("/campeonatos");
  return res.data;
}

// ── Resultados públicos (sin login) ──
export interface ResultadoPodioItem {
  puesto: number;
  nombre: string;
  club?: string;
}

export interface ResultadoRankingItem {
  puesto?: number;
  nombre: string;
  club?: string;
  total?: number;
  especial?: boolean;
  empate?: boolean;
}

export interface ResultadoPublico {
  tipo: "combate" | "figuras" | "combate_suelto";
  id: string;
  nombre: string;
  descripcion?: string;
  tatami_numero?: number | null;
  participantes: string[];
  num_competidores?: number;
  fecha?: string;
  // combate (llave)
  podio?: ResultadoPodioItem[];
  // figuras
  ranking?: ResultadoRankingItem[];
  // combate suelto
  hong?: { nombre: string; marcador: number };
  chung?: { nombre: string; marcador: number };
  ganador?: { nombre: string | null; color: "hong" | "chung" | "empate" | null };
}

export interface ResultadosCampeonato {
  // id numérico (campeonato en vivo) o "pub:<uuid>" (snapshot importado)
  campeonato: { id: number | string; nombre: string };
  resultados: ResultadoPublico[];
  categorias: string[];
  tatamis: number[];
  publicado?: boolean;
  importado_at?: string;
}

export interface CampeonatoResultadoItem {
  id: number | string; // "pub:<uuid>" si es un snapshot importado
  nombre: string;
  num_resultados: number;
  publicado?: boolean;
  importado_at?: string;
}

export async function listCampeonatosResultadosAPI() {
  const res = await api.get("/resultados/campeonatos");
  return res.data as CampeonatoResultadoItem[];
}

export async function getResultadosCampeonatoAPI(campId: number | string) {
  const res = await api.get(`/resultados/campeonato/${campId}`);
  return res.data as ResultadosCampeonato;
}

// ── Publicar resultados: exportar (en LOCAL) e importar (en ONLINE) ──

export async function exportarResultadosAPI(campId: number) {
  // Descarga el .json de resultados de un campeonato (solo admin dueño).
  const res = await api.get(`/resultados/campeonato/${campId}/exportar`, {
    responseType: "blob",
  });
  return res.data as Blob;
}

export interface ImportResultadosResumen {
  message: string;
  nombre: string;
  num_resultados: number;
  nuevo: boolean;
}

export async function importarResultadosAPI(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post("/resultados/importar", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data as ImportResultadosResumen;
}

export async function eliminarResultadoPublicadoAPI(exportUuid: string) {
  const res = await api.delete(`/resultados/publicado/${exportUuid}`);
  return res.data as { message: string };
}

export interface CampeonatoPublico {
  id: number;
  nombre: string;
  descripcion: string | null;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  lugar: string | null;
  ciudad: string | null;
  pais: string | null;
  estado: EstadoCampeonato;
  tatamis: { id: number; numero: number }[];
}

export async function listCampeonatosPublicoAPI() {
  // Sin login: campeonatos activos con sus tatamis y detalles para lo público
  const res = await api.get("/campeonatos/publico");
  return res.data as CampeonatoPublico[];
}

export async function getCampeonatoAPI(id: number) {
  const res = await api.get(`/campeonatos/${id}`);
  return res.data;
}

// Estados del ciclo de vida de un campeonato (espejo del backend).
export const ESTADOS_CAMPEONATO = ["preparacion", "en_curso", "finalizado"] as const;
export type EstadoCampeonato = (typeof ESTADOS_CAMPEONATO)[number];

// Tope de caracteres de sede/ciudad/país (espejo del backend).
export const CAMPO_LUGAR_MAX = 120;

export async function createCampeonatoAPI(data: {
  nombre: string;
  descripcion?: string;
  fecha_inicio?: string;
  fecha_fin?: string;
  lugar?: string;
  ciudad?: string;
  pais?: string;
  estado?: EstadoCampeonato;
  num_tatamis?: number;
}) {
  const res = await api.post("/campeonatos", data);
  return res.data;
}

export async function updateCampeonatoAPI(id: number, data: Record<string, unknown>) {
  const res = await api.put(`/campeonatos/${id}`, data);
  return res.data;
}

export async function deleteCampeonatoAPI(id: number) {
  const res = await api.delete(`/campeonatos/${id}`);
  return res.data;
}

// Tatamis por campeonato: mínimo y tope (espejo del backend).
export const MIN_TATAMIS = 1;
export const MAX_TATAMIS = 10;

export interface AjusteTatamis {
  message: string;
  num_tatamis: number;
  creados: number[];
  eliminados: number[];
  jueces_liberados: number;
}

/**
 * Cambia cuántos tatamis tiene el campeonato. Solo funciona en PREPARACIÓN, y
 * el backend responde 409 si al bajar habría que borrar un tatami con llaves
 * asignadas o combates guardados.
 */
export async function ajustarTatamisAPI(campeonatoId: number, numTatamis: number) {
  const res = await api.put(`/campeonatos/${campeonatoId}/tatamis`, {
    num_tatamis: numTatamis,
  });
  return res.data as AjusteTatamis;
}

// ── Sincronización entre instancias (local ↔ online) ──
//
// Un paquete .json auto-contenido viaja de una instancia a la otra. El
// importador empareja por identidad estable (uid) y resuelve él mismo el orden
// de las dependencias, así que no hay forma de importar "en el orden malo".
// Ver backend/app/api/sincronizacion.py.

export type ModoImportacion = "fusionar" | "reemplazar";

export interface ContadoresSeccion {
  nuevos: number;
  actualizados: number;
  omitidos: number;
}

export interface InformeImportacion {
  vista_previa: boolean;
  formato: string;
  modo: ModoImportacion;
  message: string;
  exportado_at?: string | null;
  origen?: { admin?: string } | null;
  resumen: Partial<Record<
    "usuarios" | "competidores" | "tatamis" | "asignaciones" | "inscripciones" | "llaves",
    ContadoresSeccion
  >>;
  avisos: string[];
  campeonato?: { id: number; nombre: string; uid: string; nuevo: boolean };
}

export interface OpcionesExportCampeonato {
  usuarios?: boolean;
  competidores?: boolean;
  llaves?: boolean;
}

function descargar(blob: Blob, nombre: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(url);
}

// Armar el paquete de un campeonato grande lleva más que una consulta normal:
// se sale del timeout corto que usa el resto de la app.
const OPCIONES_DESCARGA = { responseType: "blob" as const, timeout: 60000 };

/** Descarga el paquete completo del campeonato (para llevarlo a la otra instancia). */
export async function exportarCampeonatoAPI(
  campId: number,
  opciones: OpcionesExportCampeonato = {}
) {
  const params: Record<string, string> = {};
  for (const clave of ["usuarios", "competidores", "llaves"] as const) {
    if (opciones[clave] === false) params[clave] = "0";
  }
  const res = await api.get(`/sincronizacion/campeonato/${campId}/exportar`, {
    params, ...OPCIONES_DESCARGA,
  });
  descargar(res.data as Blob, nombreDeDescarga(res, `campeonato-${campId}.json`));
}

export async function exportarUsuariosAPI() {
  const res = await api.get("/sincronizacion/usuarios/exportar", OPCIONES_DESCARGA);
  descargar(res.data as Blob, nombreDeDescarga(res, "usuarios-dinamyt.json"));
}

export async function exportarCompetidoresAPI() {
  const res = await api.get("/sincronizacion/competidores/exportar", OPCIONES_DESCARGA);
  descargar(res.data as Blob, nombreDeDescarga(res, "competidores-dinamyt.json"));
}

/** Nombre que puso el servidor en Content-Disposition, o uno de reserva. */
function nombreDeDescarga(
  res: { headers: Record<string, unknown> },
  defecto: string
): string {
  const cabecera = String(res.headers["content-disposition"] || "");
  return /filename="([^"]+)"/.exec(cabecera)?.[1] || defecto;
}

/**
 * Sube un paquete. Con `vista_previa` el backend ejecuta la importación entera
 * y la revierte: el informe devuelto es exactamente lo que pasaría al confirmar.
 */
export async function importarPaqueteAPI(
  file: File,
  opciones: { vistaPrevia?: boolean; modo?: ModoImportacion; forzar?: boolean } = {}
) {
  const form = new FormData();
  form.append("file", file);
  form.append("vista_previa", opciones.vistaPrevia ? "1" : "0");
  form.append("modo", opciones.modo || "fusionar");
  form.append("forzar", opciones.forzar ? "1" : "0");
  const res = await api.post("/sincronizacion/importar", form, {
    headers: { "Content-Type": "multipart/form-data" },
    // Un campeonato grande son miles de filas en una sola transacción: se sale
    // del timeout corto que usa el resto de la app (pensado para la LAN).
    timeout: 120000,
  });
  return res.data as InformeImportacion;
}

// ── Tatamis API ──
export async function listTatamisAPI(campeonatoId: number) {
  const res = await api.get(`/tatamis/campeonato/${campeonatoId}`);
  return res.data;
}

export async function getTatamiAPI(id: number) {
  const res = await api.get(`/tatamis/${id}`);
  return res.data;
}

export async function misTatamisAPI() {
  const res = await api.get("/tatamis/mis-tatamis");
  return res.data;
}

export async function asignarJuezAPI(
  tatamiId: number,
  data: { usuario_id: number; rol_tatami: string; nombre_display?: string }
) {
  const res = await api.post(`/tatamis/${tatamiId}/asignar`, data);
  return res.data;
}

export async function desasignarJuezAPI(tatamiId: number, usuarioId: number) {
  const res = await api.delete(`/tatamis/${tatamiId}/desasignar/${usuarioId}`);
  return res.data;
}

// ── Llaves de eliminación (brackets) API ──
export interface LlaveCompetidor {
  id: number;
  nombre: string;
  club?: string;
}

export interface LlavePartido {
  comp1: LlaveCompetidor | null;
  comp2: LlaveCompetidor | null;
  ganador: 1 | 2 | null;
}

export interface LlaveEstructura {
  tipo?: TipoLlave;
  competidores: LlaveCompetidor[];
  // Figuras no tiene cuadro: rondas vacías y campeón null.
  rondas: LlavePartido[][];
  campeon: LlaveCompetidor | null;
  // Partido por el 3er puesto (bronce): perdedores de semifinal.
  bronce?: LlavePartido | null;
}

export type TipoLlave = "combate" | "figuras";
export type EstadoLlave = "pendiente" | "activa" | "terminada";

export interface LlaveData {
  id: number;
  campeonato_id: number;
  tatami_id?: number | null;
  tatami_numero?: number | null;
  tipo: TipoLlave;
  nombre: string;
  descripcion: string;
  estado: EstadoLlave;
  /** Clave de la sección que la generó automáticamente (null = manual). */
  seccion_clave?: string | null;
  estructura: LlaveEstructura;
  created_at: string;
}

export interface LlaveSiguiente {
  ronda: number;
  partido: number;
  ronda_nombre: string;
  comp1: LlaveCompetidor;
  comp2: LlaveCompetidor;
}

export interface LlaveTatamiInfo {
  id: number;
  tipo: TipoLlave;
  nombre: string;
  descripcion: string;
  estado: EstadoLlave;
  tatami_id?: number | null;
  tatami_numero?: number | null;
  num_competidores: number;
  pendientes: number;
  siguiente: LlaveSiguiente | null;
  campeon: LlaveCompetidor | null;
}

export async function createLlaveAPI(data: {
  campeonato_id: number;
  tatami_id?: number | null;
  tipo?: TipoLlave;
  nombre: string;
  descripcion?: string;
  competidores: { nombre: string; club?: string }[];
}) {
  const res = await api.post("/llaves", data);
  return res.data as { message: string; llave: LlaveData };
}

export async function updateLlaveAPI(
  llaveId: number,
  data: {
    nombre?: string;
    descripcion?: string;
    tatami_id?: number | null;
    competidores?: { nombre: string; club?: string }[];
  }
) {
  const res = await api.put(`/llaves/${llaveId}`, data);
  return res.data as { message: string; llave: LlaveData };
}

export async function listLlavesAPI(campeonatoId: number) {
  const res = await api.get(`/llaves/campeonato/${campeonatoId}`);
  return res.data as LlaveData[];
}

export async function listLlavesTatamiAPI(tatamiId: number | string) {
  // Llaves asignadas a un tatami con su siguiente combate sugerido
  const res = await api.get(`/llaves/tatami/${tatamiId}`);
  return res.data as LlaveTatamiInfo[];
}

export async function marcarGanadorLlaveAPI(
  llaveId: number,
  data: { ronda: number | "bronce"; partido: number; ganador: 1 | 2 | null }
) {
  const res = await api.put(`/llaves/${llaveId}/partido`, data);
  return res.data as { message: string; llave: LlaveData };
}

export async function deleteLlaveAPI(llaveId: number) {
  const res = await api.delete(`/llaves/${llaveId}`);
  return res.data;
}

export async function combinarLlavesAPI(data: {
  llave_ids: number[];
  nombre?: string;
  tatami_id?: number | null;
}) {
  // Fusiona llaves PENDIENTES del mismo tipo en una nueva (re-sorteo);
  // las originales se eliminan.
  const res = await api.post("/llaves/combinar", data);
  return res.data as { message: string; llave: LlaveData };
}

export async function moverCompetidorLlaveAPI(data: {
  origen_id: number;
  destino_id: number;
  competidor_id: number;
}) {
  // Mueve un competidor entre llaves PENDIENTES; ambas se re-sortean.
  // Si el origen queda vacío, se elimina (origen_eliminada=true).
  const res = await api.post("/llaves/mover-competidor", data);
  return res.data as {
    message: string;
    destino: LlaveData;
    origen?: LlaveData;
    origen_eliminada: boolean;
  };
}

export async function descargarLlavePdfAPI(llaveId: number) {
  // Cuadro de la llave listo para imprimir (publicar el sorteo en cartelera)
  const res = await api.get(`/llaves/${llaveId}/export/pdf`, {
    responseType: "blob",
    params: { lang: idiomaArchivo() },
  });
  return res.data as Blob;
}

export async function accesoQrAPI(tatamiId: number, usuarioId: number) {
  // Token de acceso directo para el QR de un juez asignado (solo admin)
  const res = await api.post(`/tatamis/${tatamiId}/acceso-qr/${usuarioId}`);
  return res.data as {
    token: string;
    tatami_id: number;
    rol_tatami: string;
    nombre: string;
    ip_local: string | null;
  };
}

/**
 * Origen (protocolo + host + puerto) con el que se arman las URLs de los QR.
 * Un QR con "localhost" solo funciona en el mismo PC: el teléfono que lo
 * escanee necesita una dirección alcanzable en la red. Prioridad:
 * 1. NEXT_PUBLIC_QR_ORIGIN (frontend/.env.local) — fija la URL a mano,
 *    p. ej. cuando haya dominio propio: NEXT_PUBLIC_QR_ORIGIN=https://midominio.com
 * 2. El origen actual del navegador, si NO es localhost (el admin entró por
 *    la IP de red o un dominio: esa misma dirección sirve para el teléfono).
 * 3. La IP LAN que reporta el backend + el puerto actual (el admin navega en
 *    localhost, pero el QR sale con la IP real de la máquina).
 */
export function origenParaQr(ipLocalBackend?: string | null): string {
  const fijo = process.env.NEXT_PUBLIC_QR_ORIGIN;
  if (fijo) return fijo.replace(/\/+$/, "");
  const { hostname, origin, protocol, port } = window.location;
  const esLocalhost =
    hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
  if (!esLocalhost) return origin;
  if (ipLocalBackend) return `${protocol}//${ipLocalBackend}${port ? `:${port}` : ""}`;
  return origin;
}

// ── Competidores API ──
export interface CompetidorData {
  id: number;
  nombre_completo: string;
  documento: string | null;
  fecha_nacimiento: string | null;
  genero: "MASCULINO" | "FEMENINO" | null;
  grupo_cinturon: string | null;
  cinturon: string | null;
  peso: number | null;
  club: string | null;
  categoria_especial: boolean;
  activo: boolean;
  created_at: string;
  // Última actualización de datos (peso/cinturón). El backend devuelve
  // created_at cuando nunca se ha editado.
  updated_at?: string;
  num_inscripciones?: number;
}

export type CompetidorInput = Partial<Omit<CompetidorData, "id" | "created_at">> & {
  nombre_completo: string;
};

export const GRUPOS_CINTURON = [
  "BLANCO", "PRINCIPIANTE", "INTERMEDIO", "AVANZADO", "NEGRO",
] as const;
export type GrupoCinturon = (typeof GRUPOS_CINTURON)[number];

/**
 * Cinturones REALES de Hapkido → grupo competitivo (espejo del backend).
 * El admin elige el cinturón; el grupo se detecta automáticamente.
 */
export const CINTURONES: { nombre: string; grupo: GrupoCinturon }[] = [
  { nombre: "Blanco", grupo: "BLANCO" },
  { nombre: "Amarillo", grupo: "PRINCIPIANTE" },
  { nombre: "Naranja", grupo: "PRINCIPIANTE" },
  { nombre: "Naranja/Verde", grupo: "PRINCIPIANTE" },
  { nombre: "Verde", grupo: "INTERMEDIO" },
  { nombre: "Verde/Azul", grupo: "INTERMEDIO" },
  { nombre: "Azul", grupo: "INTERMEDIO" },
  { nombre: "Rojo", grupo: "AVANZADO" },
  { nombre: "Marrón", grupo: "AVANZADO" },
  { nombre: "Marrón/Negro", grupo: "AVANZADO" },
  { nombre: "Negro", grupo: "NEGRO" },
];

export function grupoDeCinturon(nombre: string | null | undefined): GrupoCinturon | null {
  return (
    CINTURONES.find((c) => c.nombre.toLowerCase() === (nombre || "").toLowerCase())
      ?.grupo ?? null
  );
}

// Límites de los campos del competidor (espejo del backend)
export const COMPETIDOR_LIMITES = {
  nombreMin: 8,
  nombreMax: 80,
  documentoMax: 15,
  clubMax: 80,
  edadMin: 3,
  edadMax: 100,
  pesoMin: 10,
  pesoMax: 200,
  pesoCharsMax: 6,
} as const;

export async function listCompetidoresAPI(q = "", includeInactivos = false) {
  const res = await api.get("/competidores", {
    params: {
      ...(q ? { q } : {}),
      ...(includeInactivos ? { include_inactivos: "1" } : {}),
    },
  });
  return res.data as CompetidorData[];
}

export async function createCompetidorAPI(data: CompetidorInput) {
  const res = await api.post("/competidores", data);
  return res.data as { message: string; competidor: CompetidorData };
}

export async function updateCompetidorAPI(id: number, data: Partial<CompetidorInput> & { activo?: boolean }) {
  const res = await api.put(`/competidores/${id}`, data);
  return res.data as { message: string; competidor: CompetidorData };
}

export async function deleteCompetidorAPI(id: number) {
  const res = await api.delete(`/competidores/${id}`);
  return res.data;
}

export async function descargarPlantillaCompetidoresAPI() {
  const res = await api.get("/competidores/plantilla", {
    responseType: "blob",
    params: { lang: idiomaArchivo() },
  });
  return res.data as Blob;
}

export interface ImportResultado {
  message: string;
  creados: number;
  actualizados: number;
  inscritos: number;
  errores: { fila: number; error: string }[];
}

export async function importCompetidoresAPI(
  file: File,
  opts?: { campeonato_id?: number; modalidades?: string[] }
) {
  const form = new FormData();
  form.append("file", file);
  if (opts?.campeonato_id) form.append("campeonato_id", String(opts.campeonato_id));
  if (opts?.modalidades?.length) form.append("modalidades", opts.modalidades.join(","));
  const res = await api.post("/competidores/import", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data as ImportResultado;
}

// ── Inscripciones API (competidor ↔ campeonato) ──
export type EstadoInscripcion = "aceptada" | "pendiente" | "rechazada";

export interface InscripcionSolicitante {
  id: number;
  nombre: string;
  rol: string;
  club: string | null;
  delegacion?: string | null;
  pais_delegacion?: string | null;
}

export interface InscripcionData {
  id: number;
  campeonato_id: number;
  competidor_id: number;
  modalidades: string[];
  peso: number | null;
  grupo_cinturon: string | null;
  peso_efectivo: number | null;
  grupo_cinturon_efectivo: string | null;
  estado: EstadoInscripcion;
  created_by: number | null;
  motivo_rechazo: string | null;
  solicitante: InscripcionSolicitante | null;
  created_at: string;
  competidor?: CompetidorData;
}

export async function listInscripcionesAPI(
  campeonatoId: number,
  estado?: EstadoInscripcion
) {
  const res = await api.get(`/inscripciones/campeonato/${campeonatoId}`, {
    params: estado ? { estado } : {},
  });
  return res.data as InscripcionData[];
}

// Admin: acepta o rechaza una solicitud de inscripción enviada por un maestro
export async function setEstadoInscripcionAPI(
  id: number,
  estado: "aceptada" | "rechazada",
  motivo?: string
) {
  const res = await api.patch(`/inscripciones/${id}/estado`, { estado, motivo });
  return res.data as { message: string; inscripcion: InscripcionData };
}

export async function inscribirAPI(
  campeonatoId: number,
  data: {
    competidor_id?: number;
    competidor?: CompetidorInput;
    modalidades?: string[];
    peso?: number | null;
  }
) {
  const res = await api.post(`/inscripciones/campeonato/${campeonatoId}`, data);
  return res.data as { message: string; inscripcion: InscripcionData };
}

export async function updateInscripcionAPI(
  id: number,
  data: { modalidades?: string[]; peso?: number | null; grupo_cinturon?: string | null }
) {
  const res = await api.put(`/inscripciones/${id}`, data);
  return res.data as { message: string; inscripcion: InscripcionData };
}

export async function deleteInscripcionAPI(id: number) {
  const res = await api.delete(`/inscripciones/${id}`);
  return res.data;
}

// ── Flujo del maestro (inscribe a sus alumnos) ──
export interface MaestroCampeonato {
  id: number;
  nombre: string;
  descripcion: string | null;
  estado: EstadoCampeonato;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  lugar: string | null;
  ciudad: string | null;
  pais: string | null;
  puede_inscribir: boolean;
}

export async function maestroCampeonatosAPI() {
  const res = await api.get("/inscripciones/maestro/campeonatos");
  return res.data as MaestroCampeonato[];
}

export async function maestroInscribirAPI(
  campeonatoId: number,
  data: { competidor: CompetidorInput; modalidades?: string[]; peso?: number | null }
) {
  const res = await api.post(`/inscripciones/maestro/campeonato/${campeonatoId}`, data);
  return res.data as { message: string; inscripcion: InscripcionData };
}

export async function maestroMisInscripcionesAPI(campeonatoId?: number) {
  const res = await api.get("/inscripciones/maestro/mias", {
    params: campeonatoId ? { campeonato_id: campeonatoId } : {},
  });
  return res.data as InscripcionData[];
}

export async function maestroReenviarAPI(
  insId: number,
  data: { competidor: CompetidorInput; modalidades?: string[] }
) {
  const res = await api.put(`/inscripciones/maestro/${insId}`, data);
  return res.data as { message: string; inscripcion: InscripcionData };
}

// ── Ficha pública del campeonato (sin login) ──
export interface CampeonatoPublicoCompetidor {
  nombre: string;
  club: string;
  modalidades: string[];
}

export interface CampeonatoPublicoJuez {
  nombre: string;
  rol_tatami: string;
  tatami_numero: number | null;
}

export interface CampeonatoPublicoDetalle {
  campeonato: {
    id: number;
    nombre: string;
    descripcion: string | null;
    estado: EstadoCampeonato;
    fecha_inicio: string | null;
    fecha_fin: string | null;
    lugar: string | null;
    ciudad: string | null;
    pais: string | null;
  };
  competidores: CampeonatoPublicoCompetidor[];
  jueces: CampeonatoPublicoJuez[];
  clubes: string[];
  tatamis: { id: number; numero: number; activo: boolean }[];
}

export async function getCampeonatoPublicoAPI(campId: number) {
  const res = await api.get(`/inscripciones/publico/campeonato/${campId}`);
  return res.data as CampeonatoPublicoDetalle;
}

// ── Generación automática de llaves ──
export interface CategoriaConfigItem {
  activa: boolean;
  tipo?: "individual" | "rango";
  valor?: string;
  desde?: string;
  hasta?: string;
  /** Solo cinturón: grupos que abarca la categoría. */
  grupos?: string[];
}

export interface ModalidadConfigData {
  nombre: string;
  tipo_llave: TipoLlave;
  activa: boolean;
  categorias: {
    genero: string; // "mixto" | "separado"
    cinturon: CategoriaConfigItem[];
    edad: CategoriaConfigItem[];
    peso: CategoriaConfigItem[];
  };
}

export interface ConfigCategorias {
  modalidades: ModalidadConfigData[];
}

export interface SeccionCompetidorPreview {
  inscripcion_id: number;
  competidor_id: number;
  nombre: string;
  club: string;
  edad: number | null;
  peso: number | null;
  grupo_cinturon: string | null;
}

export interface SeccionPreview {
  clave: string;
  modalidad: string;
  tipo_llave: TipoLlave;
  genero: string;
  cinturon: string | null;
  cinturon_grupos: string[] | null;
  edad: string | null;
  peso: string | null;
  nombre: string;
  competidores: SeccionCompetidorPreview[];
  llave_existente?: { llave_id: number; estado: EstadoLlave; nombre: string } | null;
}

export async function getConfigCategoriasAPI(campeonatoId: number) {
  const res = await api.get(`/campeonatos/${campeonatoId}/config-categorias`);
  return res.data as { config: ConfigCategorias; guardada: boolean };
}

export async function saveConfigCategoriasAPI(campeonatoId: number, config: ConfigCategorias) {
  const res = await api.put(`/campeonatos/${campeonatoId}/config-categorias`, { config });
  return res.data as { message: string; config: ConfigCategorias };
}

export async function getSeccionesPreviewAPI(campeonatoId: number) {
  const res = await api.get(`/campeonatos/${campeonatoId}/secciones-preview`);
  return res.data as {
    secciones: SeccionPreview[];
    avisos: string[];
    total_secciones: number;
    secciones_con_competidores: number;
    total_inscripciones: number;
  };
}

export async function generarLlavesAPI(
  campeonatoId: number,
  opts?: { reemplazar?: boolean; asignar_tatamis?: boolean; solo_claves?: string[] }
) {
  const res = await api.post(`/campeonatos/${campeonatoId}/generar-llaves`, opts || {});
  return res.data as {
    message: string;
    creadas: { clave: string; nombre: string; competidores: number }[];
    omitidas: { clave: string; nombre: string; motivo: string }[];
    avisos: string[];
  };
}

// ── Categorías API ──
export async function listCategoriasAPI() {
  const res = await api.get("/categorias");
  return res.data;
}

// ── Combates API ──
export async function listCombatesAPI(tatamiId: number) {
  const res = await api.get(`/combates/tatami/${tatamiId}`);
  return res.data;
}

export async function getCombateDetalleAPI(id: number) {
  const res = await api.get(`/combates/${id}`);
  return res.data;
}

export async function listCombatesRecientesAPI(limit = 20) {
  const res = await api.get(`/combates/recientes?limit=${limit}`);
  return res.data;
}

// ── Types ──
/**
 * Un dojang del maestro, con su propia delegación.
 *
 * La delegación va en el CLUB y no en el maestro porque sus dojangs suelen
 * estar en ciudades distintas: uno en Cali y otro en Popayán no son la misma
 * delegación. `ciudad` y `pais` salen del catálogo geográfico (lib/geo.ts) y
 * por eso NO van en mayúsculas, a diferencia del nombre.
 */
export interface ClubMaestro {
  nombre: string;
  ciudad?: string | null;
  pais?: string | null;
}

export interface UserData {
  id: number;
  email: string;
  nombre: string;
  rol: "admin" | "juez" | "maestro";
  // Jerarquía: el superadmin ve todos los workspaces; un admin normal solo
  // los jueces, campeonatos y competidores que él creó.
  es_superadmin?: boolean;
  // Rol maestro: sus dojangs (los fija el admin) y permiso para juzgar tatamis.
  // Un maestro puede dirigir varios y un club puede tener varios maestros.
  // `clubes` es la lista completa, cada uno con SU delegación; `club`,
  // `delegacion` y `pais_delegacion` son los del principal (el primero) y
  // siguen viajando para lo que ya los leía.
  club?: string | null;
  clubes?: ClubMaestro[];
  delegacion?: string | null;
  pais_delegacion?: string | null;
  puede_juzgar?: boolean;
  activo: boolean;
  creado_por_id?: number | null;
  creado_por?: {
    id: number;
    nombre: string;
    email: string;
  } | null;
  created_at: string;
  eliminado_at?: string | null;
  tatamis_asignados?: TatamiAsignacion[];
  asignaciones?: TatamiAsignacion[];
}

export interface TatamiAsignacion {
  id: number;
  tatami_id: number;
  usuario_id: number;
  rol_tatami: string;
  nombre_display: string;
  asignado_at?: string;
  asignado_por?: {
    id: number;
    nombre: string;
    email: string;
  } | null;
  campeonato_nombre?: string;
}

export default api;
