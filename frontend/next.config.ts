import type { NextConfig } from "next";
import { execSync } from "node:child_process";

// Solo se define en el despliegue en la nube (Vercel), donde apunta al backend
// de Render. En la LAN nadie la pone: ahí el frontend habla directo con el
// backend del mismo equipo.
const backendUrlConfigurado = process.env.BACKEND_URL;
const backendUrl = backendUrlConfigurado || "http://127.0.0.1:5000";

/**
 * La versión que se enseña en la app, calculada EN EL BUILD.
 *
 * Es CalVer —`AAAA.MM.DD`— más el commit corto: aquí se despliega cuando algo
 * está listo, no en versiones numeradas, así que lo único que responde «¿esto
 * es de antes o de después del arreglo?» es una fecha.
 *
 * La fecha sale del COMMIT y no del reloj de quien compila: dos personas
 * compilando el mismo código tienen que obtener la misma versión, y un build
 * que se repite en el servidor no puede cambiarla.
 *
 * Sin git —un tarball, un contenedor sin `.git`— se queda vacía y la app enseña
 * `dev`, que es lo honesto: no sabemos qué está corriendo.
 *
 * Es el mismo bloque que en el portal y en Academy (`next.config.ts`).
 */
function delGit(comando: string): string {
  try {
    return execSync(comando, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

const VERSION = {
  NEXT_PUBLIC_VERSION_FECHA: delGit("git log -1 --format=%cd --date=format:%Y.%m.%d"),
  NEXT_PUBLIC_VERSION_COMMIT: delGit("git rev-parse --short HEAD"),
};

const nextConfig: NextConfig = {
  skipTrailingSlashRedirect: true,
  env: {
    /**
     * Le dice al cliente si puede consumir la API por este mismo origen.
     *
     * Se deriva de BACKEND_URL en vez de pedir otra variable porque tener el
     * proxy configurado y NO usarlo es justo el error que dejaba la sesión
     * muerta al recargar en Vercel: la cookie salía de otro dominio, era de
     * terceros, y Safari la descartaba. Y al revés, si BACKEND_URL no está,
     * esto queda vacío y el cliente sigue yendo directo — así la LAN no se
     * entera y nadie se queda sin API por una variable olvidada.
     */
    DINAMYT_PROXY_LISTO: backendUrlConfigurado ? "1" : "",
    ...VERSION,
  },
  async rewrites() {
    return {
      beforeFiles: [
        { source: "/api", destination: `${backendUrl}/api` },
        { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
        { source: "/dinamyt-socket", destination: `${backendUrl}/socket.io/` },
        { source: "/dinamyt-socket/:path*", destination: `${backendUrl}/socket.io/:path*` },
      ],
    };
  },
};

export default nextConfig;
