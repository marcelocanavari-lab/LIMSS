from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class EquipoResponse(BaseModel):
    id_equipo: int
    nombre: str
    descripcion: Optional[str] = None
    activo: bool = True


class EquipoCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)


class EquipoUpdate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)
    activo: bool


class VariableEquipoResponse(BaseModel):
    id_variable: int
    codigo: Optional[str] = None
    nombre: str
    # Agrupador visual de la pantalla ("Presión de"/"Caudal de") -- None para
    # las variables sueltas (ORP, pH, Conductividad). Dato de tabla, no
    # texto hardcodeado en el frontend, para poder sumar otros equipos con
    # sus propios grupos sin tocar código.
    grupo: Optional[str] = None
    unidad_medida: Optional[str] = None
    limite_inferior: Optional[float] = None
    limite_superior: Optional[float] = None
    orden: int
    activo: bool = True


class VariableEquipoCreate(BaseModel):
    codigo: Optional[str] = Field(None, max_length=20)
    nombre: str = Field(..., min_length=1, max_length=100)
    grupo: Optional[str] = Field(None, max_length=50)
    unidad_medida: Optional[str] = Field(None, max_length=20)
    limite_inferior: Optional[float] = None
    limite_superior: Optional[float] = None
    orden: int


class VariableEquipoUpdate(VariableEquipoCreate):
    activo: bool


class ValorLecturaInput(BaseModel):
    id_variable: int
    valor: float


class LecturaCreate(BaseModel):
    id_equipo: int
    fecha: date
    # "HH:MM", igual que <input type="time"> del frontend -- no se guarda
    # como TIME/DATETIME porque la columna ya es VARCHAR(5) (ver migración).
    hora: str = Field(..., min_length=1, max_length=5)
    id_usuario_realizo: Optional[int] = None
    id_usuario_verifico: Optional[int] = None
    # Solo las variables con un valor efectivamente cargado -- no se
    # inserta una fila en lims_equipo_lectura_valores por cada variable del
    # equipo, solo por las que la persona completó.
    valores: list[ValorLecturaInput] = []


class ValorLecturaResponse(BaseModel):
    id_variable: int
    codigo: Optional[str] = None
    nombre: str
    grupo: Optional[str] = None
    unidad_medida: Optional[str] = None
    limite_inferior: Optional[float] = None
    limite_superior: Optional[float] = None
    valor: float
    # Calculado server-side contra los límites ACTUALES de la variable (ver
    # _fuera_de_rango en routes/equipos.py) -- no se congela en la fila de
    # lims_equipo_lectura_valores porque esa tabla no tiene una columna para
    # eso (ver migración); si el límite de una variable cambia más adelante,
    # las lecturas viejas se reevalúan contra el límite nuevo al mostrarlas.
    fuera_de_rango: bool


class LecturaResponse(BaseModel):
    id_lectura: int
    id_equipo: int
    equipo_nombre: str
    fecha: date
    hora: Optional[str] = None
    id_usuario_realizo: Optional[int] = None
    usuario_realizo_nombre: Optional[str] = None
    id_usuario_verifico: Optional[int] = None
    usuario_verifico_nombre: Optional[str] = None
    fecha_registro: datetime
    valores: list[ValorLecturaResponse] = []
    # Para el Historial: permite marcar la fila/tarjeta como con alguna
    # desviación sin que el frontend tenga que recorrer `valores` de nuevo.
    tiene_fuera_de_rango: bool = False
