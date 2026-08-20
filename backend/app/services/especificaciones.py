from typing import Optional


def tiene_ensayos_analisis(cursor, id_especificacion: Optional[int]) -> bool:
    """Si la especificación no tiene NINGÚN ensayo de etapa 'analisis' (solo
    checklist de etapa 'muestreo'), la muestra que genera no tiene nada que
    mandar a un laboratorio -- no debe pasar por envío, protocolo ni carga
    de resultados de laboratorio, queda lista para Dictamen apenas se
    completa el checklist de muestreo. Sin especificación resuelta todavía
    (id_especificacion None), se asume que sí requiere envío -- comportamiento
    conservador de siempre, no se puede afirmar lo contrario sin la
    especificación."""
    if id_especificacion is None:
        return True
    cursor.execute(
        "SELECT 1 FROM lims_especificacion_ensayos WHERE id_especificacion = ? AND etapa = 'analisis' AND activo = 1",
        id_especificacion,
    )
    return cursor.fetchone() is not None
