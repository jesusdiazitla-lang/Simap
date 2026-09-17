# Manual de usuario de SIMAP

**Versión del manual:** 0.1 · **Versión de la aplicación:** 0.1.0

> Documento vivo: se actualiza con cada publicación a la rama principal.
> Guía rápida: [README_USER.md](README_USER.md). Documentación técnica: [README.md](README.md).

## Índice

1. [Introducción](#1-introducción)
2. [Requisitos](#2-requisitos)
3. [Acceso a la aplicación](#3-acceso-a-la-aplicación)
4. [Descripción de la interfaz](#4-descripción-de-la-interfaz)
5. [Funcionalidades](#5-funcionalidades)
6. [Preguntas frecuentes](#6-preguntas-frecuentes)
7. [Solución de problemas](#7-solución-de-problemas)
8. [Glosario](#8-glosario)
9. [Historial de cambios](#9-historial-de-cambios)

---

## 1. Introducción

### 1.1 Propósito de SIMAP
_(Pendiente: se completará con los documentos de contexto del proyecto.)_

### 1.2 A quién va dirigido
_(Pendiente: perfiles de usuario / roles.)_

## 2. Requisitos

- Navegador moderno actualizado (Chrome, Edge, Firefox o Safari).
- Conexión a la red donde esté publicada la aplicación.

## 3. Acceso a la aplicación

1. Abre el navegador y entra en la dirección facilitada por el administrador
   (en desarrollo: `http://localhost:3000`).
2. _(Pendiente: pantalla de inicio de sesión.)_

## 4. Descripción de la interfaz

_(Pendiente: capturas y descripción de menús, cabecera y áreas de trabajo.)_

## 5. Funcionalidades

Cada funcionalidad se documenta con el mismo esquema:
**Objetivo · Cómo llegar · Pasos · Resultado esperado · Errores habituales.**

### 5.1 _(Pendiente: primera funcionalidad de SIMAP)_

## 6. Preguntas frecuentes

**¿Dónde veo la versión de la aplicación?**
En `http://<servidor>:8000/api/v1/health` aparece `"version"`.

## 7. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| La página no carga | El servidor no está en marcha | Avisar al administrador; en desarrollo, arrancar backend y frontend (ver README técnico) |
| Aparece un error de red al usar la aplicación | La API no responde | Comprobar `/api/v1/health` |

## 8. Glosario

| Término | Significado |
|---|---|
| API | Servicio que la interfaz usa para leer y guardar datos |
| _(pendiente)_ | |

## 9. Historial de cambios

| Fecha | Versión | Cambios |
|---|---|---|
| 2026-09-17 | 0.1.0 | Creación del proyecto: estructura base, página inicial y API de salud. |
