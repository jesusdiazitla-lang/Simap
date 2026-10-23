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
| `05-fase2-activos-y-campo.md` | El **alcance de F2**: activos, QR, horómetro, alertas, sin conexión; anexo con la implementación |
| `06-fase3-ordenes-de-trabajo.md` | El **alcance de F3**: órdenes de trabajo, máquina de estados, historial, reinicio del horómetro; las ocho decisiones confirmadas y anexo con la implementación |
| `07-fase4-prediccion-e-inventario.md` | El **alcance de F4**: modelo Weibull con censura, riesgo, alertas del sistema, orden predictiva, inventario con libro; las trece decisiones confirmadas y anexo con la implementación y sus desviaciones |
| `anexos/experimentos-fase4.md` | Resultados reproducidos de la validación con simulaciones (F4, sección 14), generados por `tools/experimentos_fase4.py` |

El DDL y las políticas RLS están copiados tal cual en `backend/db/schema.sql` y
`backend/db/rls_policies.sql`. Las fases de ejecución viven en `docs/PLAN.yaml` (F0..F5).

Si un documento posterior contradice a uno anterior, manda el posterior: es más específico. Anotar la
desviación en el documento nuevo en lugar de editar el viejo.

La excepción es lo que un documento posterior **pide** cambiar en los anteriores, como la sección 16
de `06-fase3-ordenes-de-trabajo.md`: se edita el texto viejo y cada cambio lleva la marca
*[Actualizado en F…]* con la decisión que lo origina, para que se distinga de la transcripción.
