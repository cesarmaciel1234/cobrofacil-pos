import os
import sqlite3
import tempfile

from src.central_red_global.servidor.crm_salida.motor.subida import (
    _bloques,
    _ordenar_tablas,
    leer_base,
)


def test_el_envio_lee_mariadb_aunque_este_proceso_figure_en_sqlite(monkeypatch):
    class Motor:
        def _connect_kwargs(self):
            return {
                "host": "127.0.0.1",
                "port": 3306,
                "user": "root",
                "password": "no-se-imprime",
                "database": "punpro_db",
            }

    class Gestor:
        db_engine_type = "sqlite"
        _forced_local_offline = True
        mariadb_engine = None

    class Cursor:
        def execute(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Conn:
        def cursor(self):
            return Cursor()

    vistos = {}

    def conectar(**kwargs):
        vistos["host"] = kwargs.get("host")
        vistos["read_timeout"] = kwargs.get("read_timeout")
        return Conn()

    monkeypatch.setattr("src.base_de_datos.database.db_manager", Gestor())
    monkeypatch.setattr(
        "src.db_engines.mariadb_engine.MariaDBEngine",
        lambda host="127.0.0.1": Motor(),
    )
    import pymysql

    monkeypatch.setattr(pymysql, "connect", conectar)

    from src.central_red_global.servidor.crm_salida.motor.subida import _conexion_mariadb

    assert _conexion_mariadb() is not None
    assert vistos["host"] == "127.0.0.1"
    assert vistos["read_timeout"] == 120


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


def test_el_dia_mas_nuevo_sale_entero():
    columnas = ["id", "fecha", "total"]
    filas = [[i, "2026-11-14 10:00:00", 1] for i in range(151)]
    filas.append([999, "2026-11-02 10:00:00", 1])
    lotes = _bloques(columnas, filas)
    assert len(lotes[0]) == 151
    assert lotes[1][0][0] == 999


def test_los_renglones_del_dia_salen_juntos():
    columnas = ["id", "id_venta", "nombre"]
    filas = [[1, 1, "a"], [2, 1, "b"], [3, 2, "c"]]
    semanas = {"1": "2026-11-09", "2": "2026-11-02"}
    dias = {"1": "2026-11-14", "2": "2026-11-02"}
    lotes = _bloques(columnas, filas, semanas, dias)
    assert [fila[0] for fila in lotes[0]] == [1, 2]
    assert lotes[1][0][0] == 3


def test_los_renglones_siguen_la_semana_del_ticket():
    columnas = ["id", "id_venta", "nombre"]
    filas = [
        [10, 1, "viejo"],
        [11, 2, "nuevo"],
    ]
    semanas = {"1": "2026-11-02", "2": "2026-11-09"}
    ids = [fila[0] for lote in _bloques(columnas, filas, semanas) for fila in lote]
    assert ids == [11, 10]
