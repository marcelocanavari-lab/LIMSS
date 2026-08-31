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
