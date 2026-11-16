import os
import sqlite3
import tempfile

from src.central_red_global.servidor.crm_salida.motor.subida import (
    _bloques,
    _ordenar_tablas,
    leer_base,
)


def test_las_ventas_salen_antes_que_los_renglones():
    orden = _ordenar_tablas(
        ["detalles_ventas", "abastecimiento", "ventas", "clientes", "zz_cierre"]
    )
    assert orden.index("ventas") < orden.index("detalles_ventas")
    assert orden.index("clientes") < orden.index("abastecimiento")
    assert orden[-1] == "zz_cierre"


def test_la_lectura_empieza_por_ventas():
    fd, ruta = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = sqlite3.connect(ruta)
        conn.execute("CREATE TABLE detalles_ventas (id INTEGER, nombre TEXT)")
        conn.execute("CREATE TABLE ventas (id INTEGER, total REAL)")
        conn.execute("INSERT INTO detalles_ventas VALUES (1, 'asado')")
        conn.execute("INSERT INTO ventas VALUES (1, 10)")
        conn.commit()
        conn.close()
        primera = next(leer_base(ruta))[0]
        assert primera == "ventas"
    finally:
        os.remove(ruta)


def test_la_semana_nueva_sale_antes_que_la_vieja():
    columnas = ["id", "fecha", "total"]
    filas = [
        [1, "2026-11-02 10:00:00", 5],
        [2, "2026-11-15 18:00:00", 9],
        [3, "2026-11-10 12:00:00", 7],
    ]
    lotes = _bloques(columnas, filas)
    ids = [fila[0] for lote in lotes for fila in lote]
    assert ids == [2, 3, 1]


def test_los_renglones_siguen_la_semana_del_ticket():
    columnas = ["id", "id_venta", "nombre"]
    filas = [
        [10, 1, "viejo"],
        [11, 2, "nuevo"],
    ]
    semanas = {"1": "2026-11-02", "2": "2026-11-09"}
    ids = [fila[0] for lote in _bloques(columnas, filas, semanas) for fila in lote]
    assert ids == [11, 10]
