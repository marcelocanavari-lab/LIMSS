# Investigación: colisiones de (NUMCOMO, año) en comprobantes IR del ERP

**Fecha:** 2026-08-19
**Alcance:** Diagnóstico únicamente — no se modificó `obtener_vencimiento_lote`, `buscar_lineas_ir`
ni ninguna otra lógica de resolución de colisiones. Toda consulta al ERP (GI_LX) fue de solo
lectura.

## Resumen ejecutivo

La hipótesis se confirma, y el problema es **más amplio que lo que documenta el docstring de
`erp_ir.py`**: las colisiones de `(NUMCOMO, YEAR(FECCOR))` **no están limitadas al lote de arrastre
del 2020-04-02**. Se encontraron **7 grupos de colisión** en `GIN01CPB` fuera de esa fecha exacta,
con comprobantes en conflicto tan recientes como **2026-08-04** y **2026-08-07** — es decir, das de
la semana anterior a esta investigación, no solo un evento histórico cerrado.

De las 4 solicitudes generadas automáticamente por el agente que se pudieron identificar, **3 (75%)
corresponden a un IR que hoy tiene más de un comprobante con el mismo `(NUMCOMO, año)`** en el ERP.
En ninguna de las 4 la fecha *actualmente* devuelta por `obtener_vencimiento_lote` difiere de la que
quedó guardada en la solicitud en su momento — pero esto es en parte casualidad de cómo cae el
desempate por `FECCOR DESC` hoy, no una garantía: en el caso de IR 212/26 los dos comprobantes en
colisión tienen el **mismo FECCOR exacto**, por lo que `TOP 1 ... ORDER BY FECCOR DESC` no tiene un
criterio de desempate determinístico — el resultado podría cambiar en una ejecución futura sin que
cambie ningún dato.

## 1) Solicitudes generadas por el agente: comparación guardado vs. actual

Se identificaron 4 solicitudes por la unión de los dos criterios pedidos (`lims_agente_control` con
`resultado = 'solicitud_generada'`, y `lims_solicitudes_muestreo` con `id_usuario_qa` = usuario de
sistema `AGENTE_IA`, id_usuario=9). Nota: la solicitud 28 tiene `origen='agente'` e
`id_usuario_qa=9` pero **no tiene una fila correspondiente en `lims_agente_control`** — no se pudo
determinar por ese log cuál fue el `N01Id` exacto que procesó el agente en su momento.

| id_solicitud | nro_solicitud | erp_nro_ir | erp_CODART | Fecha guardada en la solicitud | Fecha actual (ERP, ahora) | ¿Coincide? | Comprobantes con mismo NUMCOMO/año |
|---|---|---|---|---|---|---|---|
| 28 | SOL-2026-012 | 15/25  | MP051 | *(sin vencimiento)* | *(sin vencimiento)* | Sí | **2** ⚠️ |
| 34 | SOL-2026-013 | 222/26 | ME088 | *(sin vencimiento)* | *(sin vencimiento)* | Sí | 1 (sin colisión) |
| 43 | SOL-2026-014 | 214/26 | MP004 | *(sin vencimiento)* | *(sin vencimiento)* | Sí | **2** ⚠️ |
| 44 | SOL-2026-015 | 212/26 | MP007 | 2028-01-28 | 2028-01-28 | Sí | **2** ⚠️ (mismo FECCOR exacto — desempate no determinístico) |

Ninguna de las 4 muestra hoy una fecha guardada distinta de la fecha actual — pero en 3 de los 4
casos eso depende de un desempate por `FECCOR` que, para dos de ellos, resuelve entre comprobantes
con **VENCOM realmente distinto** (ver detalle abajo). El motivo por el que hoy "coincide" es que el
agente resuelve el comprobante por `N01Id` directo (`comprobantes_ir_nuevos` /
`lineas_comprobante_por_id`, sin pasar por la búsqueda ambigua de `NUMCOMO`+año), mientras que
`obtener_vencimiento_lote`/`buscar_lineas_ir` — usadas por otras pantallas para volver a consultar
el mismo IR más adelante (por ejemplo al confirmar un envío) — sí pasan por esa búsqueda ambigua.
Es decir: **el valor guardado en el momento de creación es confiable, pero cualquier re-consulta
posterior del mismo IR por los métodos ambiguos corre el riesgo de traer el comprobante
equivocado.**

## 2) Detalle de las colisiones confirmadas (ligadas a las 4 solicitudes)

### IR 15/25 (solicitud 28, MP051)
```
N01Id=221180  FECCOM=2025-01-09  FECCOR=2025-01-09  VENCOM=(sin fecha)
N01Id=221836  FECCOM=2025-01-06  FECCOR=2025-01-06  VENCOM=2026-08-24   <- vencimiento real
```
`ORDER BY FECCOR DESC` elige N01Id=221180 (FECCOR más reciente) — que **no tiene vencimiento
cargado** — descartando el comprobante que sí lo tiene (N01Id=221836). Ninguno de los dos es del
2020-04-02.

### IR 214/26 (solicitud 43, MP004)
```
N01Id=221160  FECCOM=2026-08-07  FECCOR=2026-08-07  VENCOM=(sin fecha)
N01Id=221715  FECCOM=2026-08-07  FECCOR=2026-08-07  VENCOM=(sin fecha)
```
Mismo día exacto, mismo NUMCOMO — dos comprobantes distintos e indistinguibles por fecha. Hoy no se
nota en el vencimiento porque ambos están vacíos, pero son dos documentos ERP diferentes bajo el
mismo "214/26".

### IR 212/26 (solicitud 44, MP007)
```
N01Id=221157  FECCOM=2026-08-04  FECCOR=2026-08-04  VENCOM=(sin fecha)
N01Id=221728  FECCOM=2026-08-04  FECCOR=2026-08-04  VENCOM=2028-01-28   <- vencimiento real
```
**FECCOR idéntico entre ambos** — `TOP 1 ... ORDER BY FECCOR DESC` no tiene desempate
determinístico acá. Hoy devolvió el comprobante correcto (2028-01-28, coincide con lo guardado),
pero nada garantiza que siga siendo así en otra ejecución.

## 3) Censo completo de colisiones en GIN01CPB (fuera del 2020-04-02 exacto)

Se buscaron todos los grupos `(NUMCOMO, YEAR(FECCOR))` con más de un comprobante IR
(`LETCOMO='X'`), excluyendo los que caen exactamente en 2020-04-02 (el lote ya documentado). Se
encontraron **7 grupos** (14 comprobantes involucrados):

| IR | Año | Comprobantes (N01Id / FECCOM / FECCOR / VENCOM) | ¿Vinculado a una solicitud del agente? |
|---|---|---|---|
| 103/20 | 2020 | 88169 (2020-04-07, sin venc.) · 221765 (2020-04-07, sin venc.) · 88574 (2020-04-02, sin venc.) | No |
| 169/20 | 2020 | 90409 (2020-05-14→FECCOR 05-13, sin venc.) · 221853 (2020-05-13, sin venc.) | No |
| 277/20 | 2020 | 93558 (2020-07-24, sin venc.) · 221875 (2020-04-24, sin venc.) · 88703 (2020-04-02, sin venc.) | No |
| **15/25** | 2025 | 221180 (2025-01-09, sin venc.) · 221836 (2025-01-06, **venc. 2026-08-24**) | **Sí — solicitud 28** |
| 81/26 | 2026 | 221724 (2026-02-03, sin venc.) · 221725 (2026-02-03, sin venc.) | No |
| **212/26** | 2026 | 221157 (2026-08-04, sin venc.) · 221728 (2026-08-04, **venc. 2028-01-28**) | **Sí — solicitud 44** |
| **214/26** | 2026 | 221160 (2026-08-07, sin venc.) · 221715 (2026-08-07, sin venc.) | **Sí — solicitud 43** |

**Patrón notable:** en los 7 grupos, uno de los comprobantes en colisión tiene un `N01Id` "viejo"
(en el rango 88000-93000, o simplemente el más bajo del par) y el otro tiene un `N01Id` en el rango
**221xxx** — el mismo rango donde está operando el agente ahora mismo. En los 3 casos de 2020, el
comprobante "nuevo" (221xxx) **duplica una fecha ya de 2020** con un `N01Id` de carga reciente — sugiere
que algún proceso re-cargó/re-insertó comprobantes históricos con IDs nuevos en algún momento
reciente. En los 4 casos de 2025-2026, ambos comprobantes del par ya están en el rango 221xxx —
son colisiones genuinamente nuevas, no reinserciones de datos viejos.

## Conclusión (sin proponer código todavía)

1. La colisión de `(NUMCOMO, año)` **no es un evento cerrado del 2020-04-02** — hay casos
   confirmados en 2025 y, más preocupante, dos casos con fecha de **la semana previa a esta
   investigación** (2026-08-04 y 2026-08-07). El patrón parece activo/continuo, no histórico.
2. El riesgo concreto: cualquier pantalla o proceso que vuelva a resolver un IR ya usado por
   `buscar_lineas_ir`/`obtener_vencimiento_lote` (no por `N01Id` directo) puede traer el comprobante
   equivocado — con vencimiento distinto al real — cuando el IR en cuestión tiene colisión.
3. El caso de IR 212/26 muestra además un problema de **desempate no determinístico**
   (`FECCOR` idéntico entre ambos comprobantes) independiente de cuál de los dos sea "el correcto".
4. Alcance medido: 7 grupos de colisión / 14 comprobantes en todo `GIN01CPB` (excluyendo el
   2020-04-02 exacto), de los cuales 4 son recientes (2025 en adelante) y 3 de esos 4 ya afectaron
   a solicitudes reales generadas por el agente.

No se propone ningún cambio de código en este documento — queda para diseñarlo en conjunto una vez
revisado este alcance.
