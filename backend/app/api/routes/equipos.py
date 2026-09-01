"""
Control de Variables de Equipos -- arranca con el Equipo de Purificación de
Agua (13 variables: ORP, pH, 7 presiones, 3 caudales, conductividad), pero
las variables y sus rangos aceptables son datos de tabla
(lims_equipos/lims_equipo_variables, ver migración), no texto hardcodeado
-- para poder sumar otros equipos más adelante sin tocar código, solo
cargando filas nuevas en esas dos tablas.

lims_equipo_lecturas es la cabecera de una lectura puntual (equipo, fecha,
hora, quién la hizo/verificó); lims_equipo_lectura_valores tiene una fila
por cada variable con valor efectivamente cargado (no todas las 13,
solamente las completadas). "Fuera de rango" NO se guarda como columna --
se calcula siempre contra los límites ACTUALES de la variable (ver
_fuera_de_rango), tanto al cargar como al mostrar el historial.
"""
import csv
import io
from datetime import date, datetime, timedelta
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.security import get_current_user, require_rol
from app.db.connections import limss_db
from app.schemas.equipos import (
    DiaSinRegistroResponse,
    EquipoCreate,
    EquipoResponse,
    EquipoUpdate,
    LecturaCreate,
    LecturaResponse,
    ValorLecturaResponse,
    VariableEquipoCreate,
    VariableEquipoResponse,
    VariableEquipoUpdate,
)
from app.services import audit

router = APIRouter(prefix="/api/equipos", tags=["Control de Variables de Equipos"])

_ROLES = ("analista_qc", "qa", "admin")

# date.weekday(): 0=lunes ... 6=domingo -- índices 0-4 son los días hábiles
# que este reporte evalúa (ver dias_sin_registrar).
_NOMBRES_DIA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _a_fecha(valor) -> Optional[date]:
    """El driver ODBC no devuelve un tipo consistente para columnas DATE en
    este entorno (a veces date/datetime, a veces str); se normaliza siempre
    a date antes de operar (mismo helper que ya usa el resto del proyecto,
    ver muestras.py)."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor))


def _a_datetime(valor: Optional[date]) -> Optional[datetime]:
    """El driver ODBC "SQL Server" (legacy, configurado en .env) no puede
    bindear objetos date de Python (SQLBindParameter falla) -- se convierte
    a datetime, que sí soporta (mismo problema y mismo fix que en
    solicitudes_muestreo.py/auditoria.py)."""
    if valor is None:
        return None
    return datetime.combine(valor, datetime.min.time())


def _fuera_de_rango(valor: float, limite_inferior, limite_superior) -> bool:
    """Fuera de rango si hay un límite de ese lado y el valor lo cruza --
    los dos límites son opcionales de forma independiente (ver
    Conductividad: solo limite_superior, ningún piso definido)."""
    if limite_inferior is not None and valor < float(limite_inferior):
        return True
    if limite_superior is not None and valor > float(limite_superior):
        return True
    return False


def _fila_a_equipo(r) -> EquipoResponse:
    return EquipoResponse(id_equipo=r.id_equipo, nombre=r.nombre, descripcion=r.descripcion, activo=bool(r.activo))


def _fila_a_variable(r) -> VariableEquipoResponse:
    return VariableEquipoResponse(
        id_variable=r.id_variable, codigo=r.codigo, nombre=r.nombre, grupo=r.grupo,
        unidad_medida=r.unidad_medida,
        limite_inferior=float(r.limite_inferior) if r.limite_inferior is not None else None,
        limite_superior=float(r.limite_superior) if r.limite_superior is not None else None,
        orden=r.orden, activo=bool(r.activo),
    )


@router.get("", response_model=list[EquipoResponse])
def listar_equipos(
    activo: Optional[bool] = Query(True, description="None = todos, True = solo activos (default), False = solo inactivos"),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    condicion = ""
    params: list = []
    if activo is not None:
        condicion = "WHERE activo = ?"
        params.append(1 if activo else 0)
    cursor.execute(f"SELECT id_equipo, nombre, descripcion, activo FROM lims_equipos {condicion} ORDER BY nombre", *params)
    return [_fila_a_equipo(r) for r in cursor.fetchall()]


@router.post("", response_model=EquipoResponse, status_code=201)
def crear_equipo(
    body: EquipoCreate,
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """ABM de Equipos (Datos Maestros) -- antes la única forma de cargar un
    equipo nuevo era por SQL directo, lo que iba en contra de la idea
    original del módulo (variables/equipos como dato de tabla, no un
    cambio de código/base a mano)."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO lims_equipos (nombre, descripcion, activo) VALUES (?, ?, 1)",
        body.nombre, body.descripcion,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_equipo = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="equipo", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_equipo,
        valor_nuevo=body.model_dump(),
    )

    cursor.execute("SELECT id_equipo, nombre, descripcion, activo FROM lims_equipos WHERE id_equipo = ?", id_equipo)
    return _fila_a_equipo(cursor.fetchone())


@router.put("/{id_equipo}", response_model=EquipoResponse)
def editar_equipo(
    id_equipo: int,
    body: EquipoUpdate,
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Incluye la baja lógica (activo=0) -- nunca se borra la fila, para no
    perder el historial de lecturas asociadas a este equipo (ver
    lims_equipo_lecturas.id_equipo, sin ON DELETE CASCADE ni motivo para
    tenerlo)."""
    cursor = conn.cursor()
    cursor.execute("SELECT id_equipo, nombre, descripcion, activo FROM lims_equipos WHERE id_equipo = ?", id_equipo)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    valor_anterior = {"nombre": row.nombre, "descripcion": row.descripcion, "activo": bool(row.activo)}

    cursor.execute(
        "UPDATE lims_equipos SET nombre = ?, descripcion = ?, activo = ? WHERE id_equipo = ?",
        body.nombre, body.descripcion, 1 if body.activo else 0, id_equipo,
    )

    audit.registrar(
        conn, entidad="equipo", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_equipo,
        valor_anterior=valor_anterior, valor_nuevo=body.model_dump(),
    )

    cursor.execute("SELECT id_equipo, nombre, descripcion, activo FROM lims_equipos WHERE id_equipo = ?", id_equipo)
    return _fila_a_equipo(cursor.fetchone())


@router.get("/{id_equipo}/variables", response_model=list[VariableEquipoResponse])
def listar_variables_equipo(
    id_equipo: int,
    activo: Optional[bool] = Query(True, description="None = todas, True = solo activas (default), False = solo inactivas"),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_equipos WHERE id_equipo = ?", id_equipo)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    condicion = "WHERE id_equipo = ?"
    params: list = [id_equipo]
    if activo is not None:
        condicion += " AND activo = ?"
        params.append(1 if activo else 0)

    cursor.execute(
        f"""
        SELECT id_variable, codigo, nombre, grupo, unidad_medida, limite_inferior, limite_superior, orden, activo
        FROM lims_equipo_variables
        {condicion}
        ORDER BY orden
        """,
        *params,
    )
    return [_fila_a_variable(r) for r in cursor.fetchall()]


@router.post("/{id_equipo}/variables", response_model=VariableEquipoResponse, status_code=201)
def crear_variable_equipo(
    id_equipo: int,
    body: VariableEquipoCreate,
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_equipos WHERE id_equipo = ?", id_equipo)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    if body.codigo:
        cursor.execute(
            "SELECT 1 FROM lims_equipo_variables WHERE id_equipo = ? AND codigo = ?",
            id_equipo, body.codigo,
        )
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail=f"Ya existe una variable con código '{body.codigo}' en este equipo")

    cursor.execute(
        """
        INSERT INTO lims_equipo_variables
            (id_equipo, codigo, nombre, grupo, unidad_medida, limite_inferior, limite_superior, orden, activo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        id_equipo, body.codigo, body.nombre, body.grupo, body.unidad_medida,
        body.limite_inferior, body.limite_superior, body.orden,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_variable = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="equipo_variable", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_variable,
        valor_nuevo={"id_equipo": id_equipo, **body.model_dump()},
    )

    cursor.execute(
        "SELECT id_variable, codigo, nombre, grupo, unidad_medida, limite_inferior, limite_superior, orden, activo FROM lims_equipo_variables WHERE id_variable = ?",
        id_variable,
    )
    return _fila_a_variable(cursor.fetchone())


@router.put("/{id_equipo}/variables/{id_variable}", response_model=VariableEquipoResponse)
def editar_variable_equipo(
    id_equipo: int,
    id_variable: int,
    body: VariableEquipoUpdate,
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Incluye poder ajustar limite_inferior/limite_superior (si cambia el
    rango aceptable) y la baja lógica (activo=0) -- nunca se borra, para no
    perder el historial de lecturas que ya tienen un valor cargado para
    esta variable (lims_equipo_lectura_valores.id_variable)."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM lims_equipo_variables WHERE id_variable = ? AND id_equipo = ?",
        id_variable, id_equipo,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Variable no encontrada en este equipo")

    if body.codigo:
        cursor.execute(
            "SELECT 1 FROM lims_equipo_variables WHERE id_equipo = ? AND codigo = ? AND id_variable != ?",
            id_equipo, body.codigo, id_variable,
        )
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail=f"Ya existe una variable con código '{body.codigo}' en este equipo")

    valor_anterior = {
        "codigo": row.codigo, "nombre": row.nombre, "grupo": row.grupo, "unidad_medida": row.unidad_medida,
        "limite_inferior": float(row.limite_inferior) if row.limite_inferior is not None else None,
        "limite_superior": float(row.limite_superior) if row.limite_superior is not None else None,
        "orden": row.orden, "activo": bool(row.activo),
    }

    cursor.execute(
        """
        UPDATE lims_equipo_variables
        SET codigo = ?, nombre = ?, grupo = ?, unidad_medida = ?, limite_inferior = ?, limite_superior = ?, orden = ?, activo = ?
        WHERE id_variable = ?
        """,
        body.codigo, body.nombre, body.grupo, body.unidad_medida, body.limite_inferior, body.limite_superior,
        body.orden, 1 if body.activo else 0, id_variable,
    )

    audit.registrar(
        conn, entidad="equipo_variable", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_variable,
        valor_anterior=valor_anterior, valor_nuevo=body.model_dump(),
    )

    cursor.execute(
        "SELECT id_variable, codigo, nombre, grupo, unidad_medida, limite_inferior, limite_superior, orden, activo FROM lims_equipo_variables WHERE id_variable = ?",
        id_variable,
    )
    return _fila_a_variable(cursor.fetchone())


def _obtener_lectura(cursor, id_lectura: int) -> LecturaResponse:
    cursor.execute(
        """
        SELECT l.*, e.nombre AS equipo_nombre,
               ur.nombre + ' ' + ur.apellido AS usuario_realizo_nombre,
               uv.nombre + ' ' + uv.apellido AS usuario_verifico_nombre
        FROM lims_equipo_lecturas l
        INNER JOIN lims_equipos e ON e.id_equipo = l.id_equipo
        LEFT JOIN lims_usuarios ur ON ur.id_usuario = l.id_usuario_realizo
        LEFT JOIN lims_usuarios uv ON uv.id_usuario = l.id_usuario_verifico
        WHERE l.id_lectura = ?
        """,
        id_lectura,
    )
    l = cursor.fetchone()
    if not l:
        raise HTTPException(status_code=404, detail="Lectura no encontrada")

    cursor.execute(
        """
        SELECT v.id_variable, v.codigo, v.nombre, v.grupo, v.unidad_medida,
               v.limite_inferior, v.limite_superior, lv.valor
        FROM lims_equipo_lectura_valores lv
        INNER JOIN lims_equipo_variables v ON v.id_variable = lv.id_variable
        WHERE lv.id_lectura = ?
        ORDER BY v.orden
        """,
        id_lectura,
    )
    valores = [
        ValorLecturaResponse(
            id_variable=r.id_variable, codigo=r.codigo, nombre=r.nombre, grupo=r.grupo,
            unidad_medida=r.unidad_medida,
            limite_inferior=float(r.limite_inferior) if r.limite_inferior is not None else None,
            limite_superior=float(r.limite_superior) if r.limite_superior is not None else None,
            valor=float(r.valor),
            fuera_de_rango=_fuera_de_rango(float(r.valor), r.limite_inferior, r.limite_superior),
        )
        for r in cursor.fetchall()
    ]

    return LecturaResponse(
        id_lectura=l.id_lectura, id_equipo=l.id_equipo, equipo_nombre=l.equipo_nombre,
        fecha=_a_fecha(l.fecha), hora=l.hora,
        id_usuario_realizo=l.id_usuario_realizo, usuario_realizo_nombre=l.usuario_realizo_nombre,
        id_usuario_verifico=l.id_usuario_verifico, usuario_verifico_nombre=l.usuario_verifico_nombre,
        fecha_registro=l.fecha_registro,
        valores=valores,
        tiene_fuera_de_rango=any(v.fuera_de_rango for v in valores),
    )


@router.post("/lecturas", response_model=LecturaResponse, status_code=201)
def crear_lectura(
    body: LecturaCreate,
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_equipos WHERE id_equipo = ? AND activo = 1", body.id_equipo)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Equipo no encontrado o inactivo")

    if body.valores:
        cursor.execute(
            "SELECT id_variable FROM lims_equipo_variables WHERE id_equipo = ? AND activo = 1",
            body.id_equipo,
        )
        ids_validos = {r.id_variable for r in cursor.fetchall()}
        invalidas = [v.id_variable for v in body.valores if v.id_variable not in ids_validos]
        if invalidas:
            raise HTTPException(
                status_code=400,
                detail=f"Las variables {invalidas} no pertenecen a este equipo (o están inactivas)",
            )

    cursor.execute(
        """
        INSERT INTO lims_equipo_lecturas
            (id_equipo, fecha, hora, id_usuario_realizo, id_usuario_verifico, fecha_registro)
        VALUES (?, ?, ?, ?, ?, GETDATE())
        """,
        body.id_equipo, _a_datetime(body.fecha), body.hora, body.id_usuario_realizo, body.id_usuario_verifico,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_lectura = int(cursor.fetchone().id)

    for v in body.valores:
        cursor.execute(
            "INSERT INTO lims_equipo_lectura_valores (id_lectura, id_variable, valor) VALUES (?, ?, ?)",
            id_lectura, v.id_variable, v.valor,
        )

    audit.registrar(
        conn, entidad="equipo_lectura", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_lectura,
        valor_nuevo=body.model_dump(mode="json"),
    )

    return _obtener_lectura(cursor, id_lectura)


def _listar_ids_lecturas(cursor, id_equipo: Optional[int], fecha_desde: Optional[date], fecha_hasta: Optional[date]) -> list[int]:
    condiciones = []
    params: list = []
    if id_equipo is not None:
        condiciones.append("id_equipo = ?")
        params.append(id_equipo)
    if fecha_desde is not None:
        condiciones.append("fecha >= ?")
        params.append(_a_datetime(fecha_desde))
    if fecha_hasta is not None:
        condiciones.append("fecha <= ?")
        params.append(_a_datetime(fecha_hasta))
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

    cursor.execute(
        f"SELECT id_lectura FROM lims_equipo_lecturas {where} ORDER BY fecha DESC, hora DESC, id_lectura DESC",
        *params,
    )
    return [r.id_lectura for r in cursor.fetchall()]


@router.get("/lecturas", response_model=list[LecturaResponse])
def listar_lecturas(
    id_equipo: Optional[int] = Query(None),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    solo_fuera_de_rango: bool = Query(False, description="Si es True, devuelve solo las lecturas con al menos un valor fuera de rango -- reporte de desviaciones"),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    ids = _listar_ids_lecturas(cursor, id_equipo, fecha_desde, fecha_hasta)
    lecturas = [_obtener_lectura(cursor, id_lectura) for id_lectura in ids]
    if solo_fuera_de_rango:
        lecturas = [l for l in lecturas if l.tiene_fuera_de_rango]
    return lecturas


@router.get("/lecturas/exportar")
def exportar_lecturas_csv(
    id_equipo: int = Query(..., description="Requerido -- las columnas del CSV salen de las variables ACTIVAS de este equipo"),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """CSV (se abre directo en Excel) del Reporte de Mediciones -- mismo
    criterio que /api/reportes/libro-ingresos/exportar: el proyecto no tiene
    ninguna dependencia de generación de .xlsx real, CSV es lo más simple
    que Excel abre nativamente sin sumar una dependencia nueva. Columnas
    fijas por las variables ACTUALES y ACTIVAS del equipo (ordenadas por
    `orden`) -- si una lectura vieja tiene un valor de una variable ya
    desactivada, ese valor no aparece en esta exportación (sí en el
    historial en pantalla, que no filtra por variables activas)."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_equipos WHERE id_equipo = ?", id_equipo)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    cursor.execute(
        "SELECT id_variable, nombre FROM lims_equipo_variables WHERE id_equipo = ? AND activo = 1 ORDER BY orden",
        id_equipo,
    )
    variables = cursor.fetchall()

    ids = _listar_ids_lecturas(cursor, id_equipo, fecha_desde, fecha_hasta)
    lecturas = [_obtener_lectura(cursor, id_lectura) for id_lectura in ids]

    buffer = io.StringIO()
    buffer.write("﻿")  # BOM -- para que Excel detecte UTF-8 y no rompa los acentos
    writer = csv.writer(buffer)
    writer.writerow(["Fecha", "Hora"] + [v.nombre for v in variables] + ["Realizo", "Verifico"])
    for l in lecturas:
        valores_por_variable = {val.id_variable: val.valor for val in l.valores}
        writer.writerow(
            [l.fecha.isoformat(), l.hora or ""]
            + [valores_por_variable.get(v.id_variable, "") for v in variables]
            + [l.usuario_realizo_nombre or "", l.usuario_verifico_nombre or ""]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="mediciones_equipo.csv"'},
    )


@router.get("/lecturas/exportar-desviaciones")
def exportar_desviaciones_csv(
    id_equipo: Optional[int] = Query(None),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    id_variable: Optional[int] = Query(None, description="Si se pasa, solo desviaciones de esa variable puntual"),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """CSV del Reporte de valores fuera de rango -- una fila POR DESVIACIÓN
    (lectura + variable puntual que se salió del rango), no por lectura:
    una misma lectura con 3 variables fuera de rango genera 3 filas, cada
    una auditable/ordenable por separado. Mismo criterio de exportación
    que exportar_lecturas_csv (CSV, sin dependencia de .xlsx)."""
    cursor = conn.cursor()
    ids = _listar_ids_lecturas(cursor, id_equipo, fecha_desde, fecha_hasta)
    lecturas = [_obtener_lectura(cursor, id_lectura) for id_lectura in ids]

    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer)
    writer.writerow(["Equipo", "Fecha", "Hora", "Variable", "Valor", "Limite inferior", "Limite superior", "Realizo", "Verifico"])
    for l in lecturas:
        for val in l.valores:
            if not val.fuera_de_rango:
                continue
            if id_variable is not None and val.id_variable != id_variable:
                continue
            writer.writerow([
                l.equipo_nombre, l.fecha.isoformat(), l.hora or "",
                f"{val.grupo} {val.nombre}".strip() if val.grupo else val.nombre,
                val.valor,
                val.limite_inferior if val.limite_inferior is not None else "",
                val.limite_superior if val.limite_superior is not None else "",
                l.usuario_realizo_nombre or "", l.usuario_verifico_nombre or "",
            ])

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="desviaciones_equipo.csv"'},
    )


@router.get("/lecturas/dias-sin-registrar", response_model=list[DiaSinRegistroResponse])
def dias_sin_registrar(
    id_equipo: int = Query(...),
    fecha_desde: date = Query(...),
    fecha_hasta: date = Query(...),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Reporte de "Días sin registrar" -- días hábiles (lunes a viernes)
    dentro del rango elegido en los que NO se cargó ninguna lectura para el
    equipo, para detectar huecos en el control diario. Los fines de semana
    quedan siempre excluidos (el laboratorio no abre esos días, no
    corresponde exigir registro)."""
    if fecha_hasta < fecha_desde:
        raise HTTPException(status_code=400, detail="fecha_hasta no puede ser anterior a fecha_desde")

    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_equipos WHERE id_equipo = ?", id_equipo)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    cursor.execute(
        """
        SELECT DISTINCT CAST(fecha AS DATE) AS fecha
        FROM lims_equipo_lecturas
        WHERE id_equipo = ? AND fecha >= ? AND fecha <= ?
        """,
        id_equipo, _a_datetime(fecha_desde), _a_datetime(fecha_hasta),
    )
    fechas_con_registro = {_a_fecha(r.fecha) for r in cursor.fetchall()}

    dias_faltantes = []
    dia = fecha_desde
    while dia <= fecha_hasta:
        if dia.weekday() < 5 and dia not in fechas_con_registro:
            dias_faltantes.append(DiaSinRegistroResponse(fecha=dia, dia_semana=_NOMBRES_DIA[dia.weekday()]))
        dia += timedelta(days=1)

    return dias_faltantes
