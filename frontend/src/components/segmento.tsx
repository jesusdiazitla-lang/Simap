"use client";

/**
 * Control segmentado: elegir una vista entre pocas (Abiertas / Cerradas, Riesgo / Reorden).
 *
 * Radios nativos ocultos con la etiqueta como caja: se navega con flechas y se anuncia como grupo,
 * sin reimplementar nada de eso. La opción elegida va en azul (es una elección del usuario, The Two
 * Vocabularies Rule), y cada caja mide 48 px de alto.
 */

export function Segmento<T extends string>({
  nombre,
  leyenda,
  opciones,
  valor,
  alCambiar,
}: {
  readonly nombre: string;
  readonly leyenda: string;
  readonly opciones: readonly (readonly [T, string])[];
  readonly valor: T;
  readonly alCambiar: (v: T) => void;
}) {
  return (
    <fieldset>
      <legend className="sr-only">{leyenda}</legend>
      <div className="inline-flex max-w-full overflow-x-auto rounded-[var(--radius-control)] border border-borde-fuerte">
        {opciones.map(([v, etiqueta]) => (
          <label
            key={v}
            className={[
              "flex h-12 shrink-0 cursor-pointer items-center px-4 text-[0.875rem] font-medium transition-colors first:rounded-l-[var(--radius-control)] last:rounded-r-[var(--radius-control)] [&:not(:first-child)]:border-l [&:not(:first-child)]:border-borde-fuerte",
              "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accion",
              valor === v ? "bg-[var(--accion-halo)] text-accion" : "bg-superficie text-texto-suave hover:text-texto",
            ].join(" ")}
          >
            <input type="radio" name={nombre} className="sr-only" checked={valor === v} onChange={() => alCambiar(v)} />
            {etiqueta}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
