/** Configuración de dependency-cruiser para el frontend SIMAP.
 *  Se usa desde tools/graph/graph.py (salida JSON) y desde `npm run graph:check`.
 */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment: "Dependencias circulares hacen imposible razonar sobre el orden de carga.",
      from: {},
      to: { circular: true },
    },
    {
      name: "no-orphans",
      severity: "warn",
      comment: "Módulo que nadie importa: o es punto de entrada o es código muerto.",
      from: {
        orphan: true,
        pathNot: [
          "(^|/)\.[^/]+\.(js|cjs|mjs|ts|json)$", // dotfiles
          "\.d\.ts$",
          "(^|/)tsconfig\.json$",
          "^src/app/.*(page|layout|loading|error|not-found|template|route)\.tsx?$", // convenciones de Next.js
        ],
      },
      to: {},
    },
    {
      name: "components-no-app-imports",
      severity: "error",
      comment: "Los componentes reutilizables no deben depender de páginas concretas.",
      from: { path: "^src/components" },
      to: { path: "^src/app" },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsPreCompilationDeps: true,
    tsConfig: { fileName: "tsconfig.json" },
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["import", "require", "node", "default", "types"],
      mainFields: ["module", "main", "types", "typings"],
    },
    reporterOptions: {
      dot: { collapsePattern: "node_modules/(?:@[^/]+/[^/]+|[^/]+)" },
      text: { highlightFocused: true },
    },
  },
};
