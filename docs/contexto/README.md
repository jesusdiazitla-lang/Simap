# Documentos de contexto de SIMAP

Transcripciones de los documentos funcionales entregados (PDF del proyecto de grado). Son la **fuente
de verdad del dominio**: hay que leerlos antes de diseñar cualquier módulo, en lugar de deducir el
comportamiento del código ya escrito.

| Archivo | Qué define |
|---|---|
| `01-especificacion-funcional.md` | El **qué**: módulos, roles, entidades y el motor de predicción |
| `02-arquitectura.md` | El **cómo**: stack, capas, seguridad y despliegue |
| `03-requerimientos-casos-de-uso.md` | Los **criterios**: RF-01..28, RNF-01..08, CU-01..06 |
| `04-fase1-fundamentos.md` | El **alcance de F1**: auth, multi-tenant, RLS y su definición de "hecho" |

El DDL y las políticas RLS están copiados tal cual en `backend/db/schema.sql` y
`backend/db/rls_policies.sql`. Las fases de ejecución viven en `docs/PLAN.yaml` (F0..F5).

Si un documento posterior contradice a uno anterior, manda el posterior: es más específico. Anotar la
desviación en el documento nuevo en lugar de editar el viejo.
