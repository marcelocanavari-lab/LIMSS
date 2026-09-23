from typing import Iterable, Optional

from app.schemas.solicitudes_muestreo import ChecklistMuestreoItem, ChecklistMuestreoRespuesta


def tiene_ensayos_analisis(cursor, id_especificacion: Optional[int]) -> bool:
    """Si la especificación no tiene NINGÚN ensayo de categoría con momento
    'analisis' (solo checklist de categorías con momento 'muestreo' --
    Aspecto del Contenedor y/o Aspectos de la Materia Prima), la muestra que
    genera no tiene nada que mandar a un laboratorio -- no debe pasar por
    envío, protocolo ni carga de resultados de laboratorio, queda lista para
    Dictamen apenas se completa el checklist de muestreo. Se compara contra
    lims_categorias_ensayo.momento, no contra el nombre de una categoría
    puntual -- así sigue funcionando sin importar cuántas categorías de
    "muestreo" existan (ver migración de etapa/grupo_muestreo a
    lims_categorias_ensayo). Sin especificación resuelta todavía
    (id_especificacion None), se asume que sí requiere envío -- comportamiento
    conservador de siempre, no se puede afirmar lo contrario sin la
    especificación."""
    if id_especificacion is None:
        return True
    cursor.execute(
        """
        SELECT 1 FROM lims_especificacion_ensayos se
        INNER JOIN lims_categorias_ensayo cat ON cat.id_categoria = se.id_categoria
        WHERE se.id_especificacion = ? AND cat.momento = 'analisis' AND se.activo = 1
        """,
        id_especificacion,
    )
    return cursor.fetchone() is not None


def resolver_laboratorio_especificacion(cursor, id_especificacion: Optional[int]) -> tuple[str, Optional[str]]:
    """Estado del laboratorio de análisis de una especificación, para la
    columna "Laboratorio" del listado de Solicitudes de Muestreo (ver
    _fila_a_solicitud en solicitudes_muestreo.py) -- calculado en vivo contra
    los ensayos de análisis ACTIVOS, no contra el campo legacy
    lims_solicitudes_muestreo.id_laboratorio, que dejó de escribirse desde el
    rediseño de esa pantalla (ver SolicitudMuestreoCreate.id_laboratorio) y
    por eso quedaba en NULL para cualquier solicitud nueva sin importar si
    sus ensayos estaban bien configurados. Devuelve (estado, nombre):
      - ("sin_analisis", None): sin ningún ensayo 'analisis' activo (solo
        checklist de 'muestreo' -- caso normal de Material de Empaque). No es
        un problema, no hay nada que enviar a un laboratorio.
      - ("ok", "Lab A, Lab B"): TODOS los ensayos de análisis activos tienen
        laboratorio asignado -- nombres DISTINCT, separados por coma si hay
        más de uno entre los ensayos de la especificación.
      - ("falta_asignar", None): al menos un ensayo de análisis activo no
        tiene laboratorio asignado -- el único estado que debería alertar.
    Sin especificación resuelta todavía (id_especificacion None), se trata
    igual que sin ensayos de análisis: no hay nada contra qué resolver."""
    if id_especificacion is None:
        return "sin_analisis", None
    cursor.execute(
        """
        SELECT lab.nombre
        FROM lims_especificacion_ensayos se
        INNER JOIN lims_categorias_ensayo cat ON cat.id_categoria = se.id_categoria
        LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = se.id_laboratorio
        WHERE se.id_especificacion = ? AND cat.momento = 'analisis' AND se.activo = 1
        """,
        id_especificacion,
    )
    filas = cursor.fetchall()
    if not filas:
        return "sin_analisis", None
    if any(f.nombre is None for f in filas):
        return "falta_asignar", None
    nombres = sorted({f.nombre for f in filas})
    return "ok", ", ".join(nombres)


def ensayos_muestreo_faltantes(cursor, id_muestra: int, id_especificacion: Optional[int]):
    """Ensayos de categoría 'muestreo' ACTIVOS de la especificación que
    todavía no tienen fila en lims_resultados_muestreo para esta muestra --
    usado por la herramienta de "Destrabar sin checklist" (ver
    destrabar_sin_checklist en muestras.py) para saber exactamente qué
    ítems necesitan el placeholder "N/A - Destrabado manualmente". Devuelve
    filas con id_espec_ensayo y nombre_ensayo (para el audit trail)."""
    if id_especificacion is None:
        return []
    cursor.execute(
        """
        SELECT se.id_espec_ensayo, m.nombre_ensayo
        FROM lims_especificacion_ensayos se
        INNER JOIN lims_categorias_ensayo cat ON cat.id_categoria = se.id_categoria
        INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
        LEFT JOIN lims_resultados_muestreo r ON r.id_espec_ensayo = se.id_espec_ensayo AND r.id_muestra = ?
        WHERE se.id_especificacion = ? AND cat.momento = 'muestreo' AND se.activo = 1
          AND r.id_resultado IS NULL
        ORDER BY se.orden
        """,
        id_muestra, id_especificacion,
    )
    return cursor.fetchall()


def muestra_elegible_destrabar_checklist(cursor, id_muestra: int):
    """(elegible, motivo_no_elegible, faltantes) -- una muestra es candidata
    a "Destrabar sin checklist" (ver destrabar_sin_checklist en muestras.py)
    solo cuando estructuralmente NO puede completar su checklist por el
    flujo normal: sigue 'en_análisis', sin dictamen todavía, su
    especificación no tiene ningún ensayo 'análisis' activo (si lo tuviera,
    el camino normal es Envío/Carga de Resultados, no este) y le falta al
    menos un resultado de 'muestreo'. Validación server-side deliberada --
    nunca confiar en que el frontend mandó la lista correcta, mismo criterio
    que vincular_especificacion en muestras.py."""
    cursor.execute("SELECT estado, id_especificacion FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    m = cursor.fetchone()
    if not m:
        return False, "Muestra no encontrada", []
    if m.estado != "en_análisis":
        return False, f"La muestra está en estado '{m.estado}', no 'en_análisis'", []
    if m.id_especificacion is None:
        return False, "La muestra no tiene especificación vinculada", []
    cursor.execute("SELECT 1 FROM lims_dictamenes WHERE id_muestra = ?", id_muestra)
    if cursor.fetchone():
        return False, "La muestra ya tiene un dictamen emitido", []
    if tiene_ensayos_analisis(cursor, m.id_especificacion):
        return False, "La especificación tiene ensayos de análisis -- corresponde el flujo normal de Envío/Carga de Resultados", []
    faltantes = ensayos_muestreo_faltantes(cursor, id_muestra, m.id_especificacion)
    if not faltantes:
        return False, "El checklist ya está completo -- la muestra ya debería estar en la Bandeja de Dictamen", []
    return True, None, faltantes


def obtener_checklist_muestreo(cursor, id_muestra: Optional[int], id_especificacion: Optional[int]) -> list[ChecklistMuestreoItem]:
    """Ítems de categorías con momento 'muestreo' (Aspecto del Contenedor,
    Aspectos de la Materia Prima -- ver lims_categorias_ensayo) de una
    especificación, con la respuesta ya cargada en lims_resultados_muestreo
    para esta muestra (si la hay). Compartido por Ejecutar Muestreo
    (Solicitud de Muestreo) y por el checklist de Nueva Muestra (creación
    directa, sin solicitud) -- ambos flujos terminan en la misma tabla,
    keyed por id_muestra, así que no hace falta duplicar esta consulta.
    id_muestra puede ser None (todavía no existe la muestra -- formulario en
    blanco).

    Trae id_categoria/codigo/nombre de cada ítem (no solo el momento) para
    que el frontend pueda agrupar la lista en secciones separadas por
    categoría (Contenedor vs. Materia Prima) -- ver ChecklistMuestreo.jsx.
    Ordena por el orden de la categoría primero y el del ensayo después, así
    la lista ya sale agrupable sin tener que reordenar del lado del cliente."""
    if id_especificacion is None:
        return []
    cursor.execute(
        """
        SELECT se.id_espec_ensayo, se.orden, m.nombre_ensayo, se.especificacion_texto,
               r.valor_cualitativo,
               cat.id_categoria, cat.codigo AS categoria_codigo, cat.nombre AS categoria_nombre
        FROM lims_especificacion_ensayos se
        INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
        INNER JOIN lims_categorias_ensayo cat ON cat.id_categoria = se.id_categoria
        LEFT JOIN lims_resultados_muestreo r ON r.id_espec_ensayo = se.id_espec_ensayo AND r.id_muestra = ?
        WHERE se.id_especificacion = ? AND cat.momento = 'muestreo' AND se.activo = 1
        ORDER BY cat.orden, se.orden
        """,
        id_muestra, id_especificacion,
    )
    return [
        ChecklistMuestreoItem(
            id_espec_ensayo=e.id_espec_ensayo, orden=e.orden, nombre_ensayo=e.nombre_ensayo,
            especificacion_texto=e.especificacion_texto, valor_cualitativo=e.valor_cualitativo,
            id_categoria=e.id_categoria, categoria_codigo=e.categoria_codigo, categoria_nombre=e.categoria_nombre,
        )
        for e in cursor.fetchall()
    ]


def guardar_checklist_muestreo(
    cursor,
    id_muestra: int,
    id_especificacion: Optional[int],
    respuestas: Iterable[ChecklistMuestreoRespuesta],
    id_usuario: int,
) -> None:
    """Guarda las respuestas del checklist de etapa 'muestreo' para una
    muestra -- mismo criterio laxo que el resto del guardado de resultados
    en la app: se ignoran en silencio los id_espec_ensayo que no pertenecen
    a la especificación de la muestra, en vez de bloquear todo el guardado
    por un ítem inválido.

    Upsert (no INSERT ciego): a diferencia de confirmar_orden_trabajo, que
    solo puede ejecutarse una vez porque está atado al estado 'pendiente' de
    una solicitud, este helper también lo usa el checklist de Nueva Muestra,
    que no tiene ese guardado de estado -- tiene que ser seguro llamarlo más
    de una vez sobre la misma muestra sin duplicar filas en
    lims_resultados_muestreo."""
    if id_especificacion is None:
        return
    cursor.execute(
        """
        SELECT se.id_espec_ensayo FROM lims_especificacion_ensayos se
        INNER JOIN lims_categorias_ensayo cat ON cat.id_categoria = se.id_categoria
        WHERE se.id_especificacion = ? AND cat.momento = 'muestreo' AND se.activo = 1
        """,
        id_especificacion,
    )
    validos = {r.id_espec_ensayo for r in cursor.fetchall()}
    for respuesta in respuestas:
        if respuesta.id_espec_ensayo not in validos:
            continue
        valor = respuesta.valor_cualitativo.strip()
        dentro = valor.lower() == "cumple" if valor else None
        cursor.execute(
            "SELECT id_resultado FROM lims_resultados_muestreo WHERE id_muestra = ? AND id_espec_ensayo = ?",
            id_muestra, respuesta.id_espec_ensayo,
        )
        existente = cursor.fetchone()
        if existente:
            cursor.execute(
                """
                UPDATE lims_resultados_muestreo
                SET valor_cualitativo = ?, dentro_especificacion = ?, id_usuario_carga = ?, fecha_carga = GETDATE()
                WHERE id_resultado = ?
                """,
                valor, dentro, id_usuario, existente.id_resultado,
            )
        else:
            cursor.execute(
                """
                INSERT INTO lims_resultados_muestreo
                    (id_muestra, id_espec_ensayo, valor_cualitativo, dentro_especificacion, id_usuario_carga, fecha_carga)
                VALUES (?, ?, ?, ?, ?, GETDATE())
                """,
                id_muestra, respuesta.id_espec_ensayo, valor, dentro, id_usuario,
            )
