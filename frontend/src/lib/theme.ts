// Tema claro / oscuro / como-el-sistema.
//
// **Es el mismo archivo en las cuatro webs del ecosistema**, y eso es
// deliberado: la misma persona cruza de una a otra y no puede encontrarse tres
// comportamientos distintos. Si cambia, cambia en las cuatro.
//
// ── Lo que se anadio el 5 de septiembre de 2026 ──
//
// El tercer valor, `sistema`, que antes no estaba: solo habia `dark` y `light`,
// asi que quien tiene el telefono en modo claro tenia que pedirlo tambien aqui.
// Ahora `sistema` es el valor por defecto y consulta `prefers-color-scheme`.
//
// ── Y por que la eleccion viaja en el PASE ──
//
// `localStorage` es POR ORIGEN, y las cuatro apps viven en subdominios
// distintos: dinamyt.org, club.dinamyt.org, campeonatos.dinamyt.org,
// academy.dinamyt.org. Guardarla solo aqui obligaba a elegir el modo claro una
// vez por app, y otra vez en cada dispositivo.
//
// La verdad vive en `users.theme` y llega dentro del JWT (ver `JwtPayload` en
// `packages/shared`). Lo de aqui es una COPIA para poder pintar antes de saber
// quien eres, sin el fogonazo oscuro.

export type Tema = 'sistema' | 'claro' | 'oscuro';

/** La copia local. La verdad la manda el pase. Misma clave en las cuatro. */
const STORAGE_KEY = 'dinamyt_theme';

// Debe coincidir con <meta name="theme-color"> del layout: es el color de la
// barra del navegador y de la PWA instalada.
const META_COLOR: Record<'claro' | 'oscuro', string> = {
  oscuro: '#0e0e15',
  claro: '#eef0f4',
};

/** Lo que `sistema` significa AHORA MISMO en este dispositivo. */
export function temaDelSistema(): 'claro' | 'oscuro' {
  if (typeof window === 'undefined') return 'oscuro';
  return window.matchMedia?.('(prefers-color-scheme: light)').matches
    ? 'claro'
    : 'oscuro';
}

/** El tema elegido, tal cual: puede ser `sistema`. */
export function getTema(): Tema {
  if (typeof window === 'undefined') return 'sistema';
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === 'claro' || v === 'oscuro' || v === 'sistema') return v;
    // Los que eligieron antes de que existiera el tercer valor.
    if (v === 'light') return 'claro';
    if (v === 'dark') return 'oscuro';
  } catch {
    /* modo incognito: se queda en el de por defecto */
  }
  return 'sistema';
}

/** El tema que hay que PINTAR, con `sistema` ya resuelto. */
export function temaEfectivo(tema: Tema = getTema()): 'claro' | 'oscuro' {
  return tema === 'sistema' ? temaDelSistema() : tema;
}

/** Aplica el tema al documento y guarda la copia local. */
export function aplicarTema(tema: Tema, guardar = true) {
  if (typeof document === 'undefined') return;
  const efectivo = temaEfectivo(tema);
  const root = document.documentElement;

  if (efectivo === 'claro') root.dataset.theme = 'light';
  else delete root.dataset.theme;

  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', META_COLOR[efectivo]);

  if (!guardar) return;
  try {
    localStorage.setItem(STORAGE_KEY, tema);
  } catch {
    /* modo incognito: el tema aplica solo a esta pestana */
  }
}

/**
 * El script que corre ANTES de pintar. Va inline en el <head> con
 * dangerouslySetInnerHTML: si esperara a React, la pagina se veria oscura un
 * instante antes de aclararse, y ese fogonazo se lee como un fallo.
 *
 * Tiene que entender `sistema` el solo —consultando `prefers-color-scheme`—,
 * porque para cuando React monte ya es tarde.
 */
export const SCRIPT_ANTI_PARPADEO = `(function(){try{
var t=localStorage.getItem('${STORAGE_KEY}')||'sistema';
if(t==='light')t='claro';if(t==='dark')t='oscuro';
var claro = t==='claro' || (t==='sistema' && window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches);
if(claro){document.documentElement.dataset.theme='light';
var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute('content','${META_COLOR.claro}');}
}catch(e){}})();`;

/** Nombre viejo, para no tocar cada pantalla de golpe. */
export const SCRIPT_ANTI_FLASH = SCRIPT_ANTI_PARPADEO;

/**
 * Aplica el tema y el idioma que vienen DENTRO de un pase del ecosistema.
 *
 * Se llama en el unico momento en que esta app ve el JWT: el salto desde el
 * portal (`#token=`). Despues la sesion es una cookie httpOnly y el pase ya no
 * se puede leer, asi que este es el momento o ninguno.
 *
 * Es lo que hace que elegir el modo claro UNA vez, en el perfil del portal, se
 * note tambien aqui. Sin esto, `localStorage` es por origen y la eleccion se
 * queda en dinamyt.org.
 *
 * No lanza nunca: un pase raro no puede impedir que alguien entre.
 */
export function aplicarAparienciaDelPase(token: string) {
  try {
    const parte = token.split('.')[1];
    const p = JSON.parse(
      atob(parte.replace(/-/g, '+').replace(/_/g, '/')),
    ) as Record<string, unknown>;

    const tema = p.theme;
    if (tema === 'claro' || tema === 'oscuro' || tema === 'sistema') {
      aplicarTema(tema);
    }
    // El idioma comparte clave con el i18n de esta app (`dinamyt_lang`), asi
    // que basta con dejarlo escrito: el provider lo lee al montar.
    const loc = p.locale;
    if (typeof loc === 'string' && loc) {
      localStorage.setItem(
        'dinamyt_lang',
        loc.toLowerCase().startsWith('en') ? 'en' : 'es',
      );
    }
  } catch {
    /* un pase ilegible no puede romper el inicio de sesion */
  }
}

/**
 * Vigila el tema del SISTEMA y repinta mientras la eleccion sea `sistema`.
 *
 * ── El hueco que cierra ──
 *
 * `sistema` es el valor POR DEFECTO —lo dice `users.theme` en el esquema—, asi
 * que esto no es un caso raro: es el de casi todo el mundo. Y hasta ahora
 * `prefers-color-scheme` se consultaba UNA SOLA VEZ, al pintar. Con eso, «como
 * el sistema» significaba en realidad «como estaba el sistema cuando abri la
 * pagina».
 *
 * Se nota en el caso mas comun de todos: el telefono que pasa a modo oscuro
 * solo al anochecer. La pantalla se queda clara hasta que alguien recarga, y lo
 * que se lee no es «la web no escucha al sistema» sino «la web se quedo
 * pegada».
 *
 * ── Por que no guarda ──
 *
 * Porque no ha cambiado nada que sea de la persona: sigue eligiendo `sistema`.
 * Lo que cambio es el sistema. Escribirlo convertiria una preferencia viva en
 * un `claro` o un `oscuro` fijo, que es justo lo contrario de lo que se pidio.
 *
 * Devuelve la funcion para dejar de escuchar.
 */
export function escucharTemaDelSistema(): () => void {
  if (typeof window === 'undefined' || !window.matchMedia) {
    return () => undefined;
  }
  const consulta = window.matchMedia('(prefers-color-scheme: light)');
  const alCambiar = () => {
    // Solo si la eleccion sigue siendo `sistema`. Quien pidio claro a mano
    // quiere claro tambien de noche.
    if (getTema() === 'sistema') aplicarTema('sistema', false);
  };

  // Safari no soporto `addEventListener` aqui hasta la 14, y en iOS todavia se
  // ve la 13 en telefonos que la gente usa a diario para esto.
  if (consulta.addEventListener) {
    consulta.addEventListener('change', alCambiar);
    return () => consulta.removeEventListener('change', alCambiar);
  }
  consulta.addListener(alCambiar);
  return () => consulta.removeListener(alCambiar);
}
