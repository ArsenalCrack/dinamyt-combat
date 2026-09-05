import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono, Instrument_Sans } from "next/font/google";
import { AplicarApariencia } from "@/components/AplicarApariencia";
import AppMenu from "@/components/AppMenu";
import PorteroMantenimiento from "@/components/PorteroMantenimiento";
import Toaster from "@/components/Toaster";
import { I18nProvider } from "@/lib/i18n";
import { SCRIPT_ANTI_PARPADEO } from "@/lib/theme";
import "./globals.css";

// Fuentes auto-hospedadas: next/font las descarga en el build y las sirve
// desde nuestro dominio. Con el @import a Google Fonts, los celulares que no
// alcanzaban fonts.googleapis.com caian a la fuente del sistema y desencajaban
// todo el layout.
//
// ── Por que estas tres y no las de antes ──────────────────────────────────
//
// Campeonatos usaba Bebas Neue + Barlow Condensed + Share Tech Mono, y las
// otras tres webs del ecosistema Archivo + Instrument Sans + IBM Plex Mono.
// Era la diferencia que mas se notaba al saltar de una app a otra: los colores
// se parecian, pero la LETRA no, y la letra es lo primero que se lee.
//
// Ahora son las mismas que el portal, Academy y Membresias:
//   · Archivo         display deportivo, con eje de anchura (font-stretch)
//   · Instrument Sans  cuerpo humanista
//   · IBM Plex Mono    mono de marcador (puntos, tiempos, PIN)
const display = Archivo({
  subsets: ["latin"],
  display: "swap",
  axes: ["wdth"],
  variable: "--next-font-display",
});
const cuerpo = Instrument_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--next-font-body",
});
const mono = IBM_Plex_Mono({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  display: "swap",
  variable: "--next-font-mono",
});

const fontClasses = `${display.variable} ${cuerpo.variable} ${mono.variable}`;

export const metadata: Metadata = {
  title: "DINAMYT - Sistema de Competencias Hapkido",
  description: "Sistema profesional de gestion y puntuacion de competencias de Hapkido en tiempo real. Combate, Figuras y mas.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning: el script inline de abajo pone data-theme en
    // <html> antes de hidratar; sin esto React avisa de atributo distinto
    <html lang="es" className={fontClasses} suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover" />
        <meta name="format-detection" content="telephone=no" />
        {/* El mismo color de fondo que las otras tres webs (era #050507). */}
        <meta name="theme-color" content="#0e0e15" />
        {/* Aplicar el tema ANTES del primer pintado: en un useEffect, cada
            carga en claro daria un fogonazo oscuro. El script viene de
            `lib/theme.ts`, que es el mismo archivo en las cuatro apps, y ahora
            entiende tambien `sistema` — el de antes solo miraba si el valor
            guardado era exactamente "light". */}
        <script dangerouslySetInnerHTML={{ __html: SCRIPT_ANTI_PARPADEO }} />
        {/* PWA: instalable en escritorio y móvil */}
        <link rel="manifest" href="/manifest.webmanifest" />
        {/* Android arma la pantalla de carga con el icono MÁS GRANDE que logre
            descargar del manifiesto, y lo estira hasta el tamaño del splash
            (~512 px en un celular de densidad 4x). Declarar aquí el de 512
            además del manifiesto le deja una segunda fuente en alta
            resolución; si solo queda el de 192 —o peor, el favicon— lo que se
            ve es ese icono ampliado, o sea pixeleado.

            Ojo con `purpose: "maskable"`: nuestro escudo es transparente y con
            aire alrededor, no llena el cuadro de borde a borde. Declararlo
            maskable hace que Android lo pinte sobre un plato del color de
            fondo del manifiesto. Por eso el manifiesto solo trae los dos
            iconos `any`, igual que membresías. */}
        <link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png" />
        <link rel="icon" type="image/png" sizes="512x512" href="/icon-512.png" />
        <link rel="apple-touch-icon" href="/icon-192.png" />
        <meta name="application-name" content="DINAMYT" />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="apple-mobile-web-app-title" content="DINAMYT" />
      </head>
      <body>
        <I18nProvider>
          {/* El tema y el idioma, al dia: escucha el modo claro del sistema y
              pregunta a la cuenta lo que se eligio en las otras apps. Solo
              pregunta con sesion — ver el componente. */}
          <AplicarApariencia />
          {/* El menú va DENTRO del portero: con el mantenimiento puesto no
              tiene sentido ofrecer navegación a pantallas que no responden. */}
          <PorteroMantenimiento>
            <AppMenu />
            {children}
          </PorteroMantenimiento>
          {/* Avisos flotantes de "guardado" / "no se pudo". Fuera del portero
              y al final: se pinta en un portal sobre el <body>, así ningún
              contenedor de la página puede recortarlo. */}
          <Toaster />
        </I18nProvider>
      </body>
    </html>
  );
}
