'use client';

/**
 * La versión que está corriendo, en pequeño y donde no estorbe.
 *
 * ── Para qué sirve de verdad ──
 *
 * Para la conversación que se repite: alguien escribe «me sigue pasando» y no
 * hay forma de saber si está viendo el arreglo o la pantalla de antes. Con la
 * fecha a la vista la respuesta es un vistazo — y si no coincide, ya se sabe
 * que lo que falta es recargar la app instalada, no volver a depurar.
 *
 * ── El formato ──
 *
 * `2026.09.08` en pantalla y `2026.09.08+8cacddf` en el `title`, que es lo que
 * sale al dejar el cursor encima y lo que se pega en un reporte. La fecha es
 * para la persona («¿está al día mi app?») y el hash para quien depura («¿qué
 * código exactamente?»).
 *
 * ── Por qué es una COPIA y no `@dinamyt/shared` ──
 *
 * Porque esta app vive en su propio repositorio y a propósito no está en el
 * workspace del monorepo (meterla obligaría a resolver sus dependencias contra
 * las de allí). El original es `packages/shared/src/version.ts`; son diez
 * líneas y no cambian.
 *
 * En local dice `dev`, a propósito: ahí el código cambia al guardar y una
 * versión fija sería mentira.
 */
export function Version() {
  const fecha = (process.env.NEXT_PUBLIC_VERSION_FECHA ?? '').trim();
  const commit = (process.env.NEXT_PUBLIC_VERSION_COMMIT ?? '').trim();
  const visible = fecha || 'dev';
  const completa = fecha && commit ? `${fecha}+${commit}` : visible;

  return (
    <p className="pie-version" title={`Versión ${completa}`}>
      v{visible}
    </p>
  );
}
