from typing import NamedTuple, Optional

from app.services.formato import formatear_cantidad


class BultoIndividual(NamedTuple):
    """Un bulto físico puntual, ya resuelto a partir de los grupos de una
    solicitud (o del fallback legacy sin grupos) -- lo que necesita cada
    etiqueta CUARENTENA/APROBADO/RECHAZADO para imprimirse: su número
    dentro del total combinado (bulto_actual/bulto_total, contador
    continuo a través de todos los grupos) y la cantidad de ESE grupo en
    particular (no la cantidad general del ingreso). cantidad_valor es el
    mismo dato que cantidad_texto pero sin formatear ni la unidad --
    necesario para el QR de la etiqueta (ver impresion_sato.py), que
    codifica solo el número."""
    bulto_actual: int
    bulto_total: int
    cantidad_texto: Optional[str]
    cantidad_valor: Optional[float]


def obtener_grupos_bultos(cursor, id_solicitud: int):
    """Grupos de bultos cargados para una solicitud (cantidad de bultos x
    cantidad de unidades cada uno, ver migración que crea
    lims_solicitud_bultos), en el orden en que se cargaron. Lista vacía si
    la solicitud no tiene grupos cargados -- caso legacy, ver
    expandir_bultos."""
    cursor.execute(
        "SELECT id_bulto_grupo, cantidad_bultos, cantidad_unidades, unidad_medida FROM lims_solicitud_bultos "
        "WHERE id_solicitud = ? ORDER BY orden",
        id_solicitud,
    )
    return cursor.fetchall()


def expandir_bultos(
    grupos, nro_bultos_fallback: int, cantidad_texto_fallback: Optional[str],
    cantidad_valor_fallback: Optional[float] = None,
) -> list[BultoIndividual]:
    """Una entrada por bulto físico, con un contador continuo (1..N) a
    través de todos los grupos combinados -- lo que consumen los loops de
    impresión de CUARENTENA/APROBADO/RECHAZADO en vez de repetir esta
    cuenta en cada uno.

    Sin grupos cargados (`grupos` vacío -- solicitud vieja, de antes de
    esta feature, o simplemente sin bultos desglosados), arma un único
    "grupo implícito" de `nro_bultos_fallback` bultos, todos con el texto
    (y valor numérico) de cantidad general de la solicitud/muestra -- mismo
    comportamiento que existía antes de los grupos de bultos, sin romper
    nada."""
    if not grupos:
        total = max(1, nro_bultos_fallback)
        return [
            BultoIndividual(i, total, cantidad_texto_fallback, cantidad_valor_fallback)
            for i in range(1, total + 1)
        ]

    total = sum(g.cantidad_bultos for g in grupos)
    resultado = []
    contador = 0
    for g in grupos:
        if g.cantidad_unidades is not None:
            cantidad_texto_grupo = f"{formatear_cantidad(g.cantidad_unidades)} {g.unidad_medida or ''}".strip()
            cantidad_valor_grupo = float(g.cantidad_unidades)
        else:
            cantidad_texto_grupo = cantidad_texto_fallback
            cantidad_valor_grupo = cantidad_valor_fallback
        for _ in range(g.cantidad_bultos):
            contador += 1
            resultado.append(BultoIndividual(contador, total, cantidad_texto_grupo, cantidad_valor_grupo))
    return resultado


def guardar_grupos_bultos(cursor, id_solicitud: int, grupos: list) -> Optional[int]:
    """Reemplaza (DELETE + INSERT) los grupos de bultos de una solicitud --
    completar-datos se puede llamar más de una vez sobre la misma
    solicitud, así que esto tiene que ser idempotente en vez de acumular
    filas viejas. `grupos` es una lista de objetos con .cantidad_bultos,
    .cantidad_unidades, .unidad_medida (ver BultoGrupoInput en
    app/schemas/solicitudes_muestreo.py). Devuelve la suma de
    cantidad_bultos (para sincronizar lims_solicitudes_muestreo.nro_bultos)
    o None si `grupos` viene vacío/no se pasó -- en ese caso el llamador
    conserva el nro_bultos que ya tenía (mismo criterio que el resto de
    completar_datos: solo se toca lo que efectivamente venga cargado)."""
    cursor.execute("DELETE FROM lims_solicitud_bultos WHERE id_solicitud = ?", id_solicitud)
    if not grupos:
        return None
    for i, g in enumerate(grupos):
        cursor.execute(
            """
            INSERT INTO lims_solicitud_bultos
                (id_solicitud, cantidad_bultos, cantidad_unidades, unidad_medida, orden)
            VALUES (?, ?, ?, ?, ?)
            """,
            id_solicitud, g.cantidad_bultos, g.cantidad_unidades, g.unidad_medida, i,
        )
    return sum(g.cantidad_bultos for g in grupos)
