import sqlite3
import pytest
from src.base_de_datos.database import db_manager
from src.clientes_fiado.oficina.huella import tabla, eventos
from src.clientes_fiado.oficina.cuenta.motor import MotorCuenta


@pytest.fixture
def fusion_db(tmp_path, monkeypatch):
    ruta = tmp_path / "fusion_test.db"
    conn = sqlite3.connect(ruta)
    conn.executescript(
        """
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            telefono TEXT,
            limite_credito REAL,
            deuda_actual REAL,
            fecha_registro TEXT,
            dni TEXT,
            tipo_cliente TEXT,
            direccion TEXT,
            uid TEXT,
            actualizado_en TEXT
        );
        CREATE TABLE cuenta_corriente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            fecha TEXT,
            tipo TEXT,
            monto REAL,
            saldo_resultante REAL,
            descripcion TEXT,
            venta_id INTEGER,
            medio_pago TEXT,
            perfil TEXT,
            registrado_por TEXT
        );
        CREATE TABLE clientes_auditoria (
            evento TEXT,
            fecha TEXT,
            accion TEXT,
            cliente_uid TEXT,
            cliente_id INTEGER,
            nombre TEXT,
            pc TEXT,
            caja TEXT,
            usuario TEXT,
            base TEXT,
            detalle TEXT,
            llego_en TEXT,
            llego_via TEXT
        );
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY,
            fecha TEXT,
            total REAL,
            cliente_nombre TEXT
        );

        INSERT INTO clientes (id, nombre, telefono, limite_credito, deuda_actual, dni, tipo_cliente, uid)
        VALUES (21, 'silvio falcon', '11223344', 10000.0, 10000.0, '30111222', 'regular', 'UID-21');

        INSERT INTO clientes (id, nombre, telefono, limite_credito, deuda_actual, dni, tipo_cliente, uid)
        VALUES (170, 'silvio falcon', '', 50000.0, 29272.5, '', 'cliente_express', 'UID-170');

        INSERT INTO cuenta_corriente (id, cliente_id, fecha, tipo, monto, saldo_resultante, descripcion, venta_id)
        VALUES (1, 21, '2026-11-11 10:40:40', 'CARGO', 10000.0, 10000.0, 'Venta a crédito Ticket #1093125', 1093125);

        INSERT INTO cuenta_corriente (id, cliente_id, fecha, tipo, monto, saldo_resultante, descripcion, venta_id)
        VALUES (2, 170, '2026-11-14 10:26:40', 'CARGO', 29272.5, 29272.5, 'Venta a crédito Ticket #1093338', 1093338);

        INSERT INTO ventas (id, fecha, total, cliente_nombre)
        VALUES (1093125, '2026-11-11 10:40:40', 10000.0, 'silvio falcon');

        INSERT INTO ventas (id, fecha, total, cliente_nombre)
        VALUES (1093338, '2026-11-14 10:26:40', 29272.5, 'silvio falcon');
        """
    )
    conn.commit()
    conn.close()

    def conectar():
        db = sqlite3.connect(ruta, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    monkeypatch.setattr(db_manager, "get_connection", conectar)
    monkeypatch.setattr(tabla, "asegurar", lambda *_a, **_kw: True)
    monkeypatch.setattr(eventos, "guardar_en", lambda *_a, **_kw: True)
    return ruta


def _leer(ruta, sql, params=()):
    with sqlite3.connect(ruta) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchall()


def test_fusionar_clientes_exitoso(fusion_db):
    motor = MotorCuenta()
    exito, nueva_deuda, info = motor.fusionar_clientes(id_destino=21, id_origen=170)

    assert exito is True
    assert nueva_deuda == pytest.approx(39272.5)
    assert info["id_destino"] == 21
    assert info["id_origen"] == 170
    assert info["movimientos_migrados"] == 1

    # Check client 21 in DB
    rows_21 = _leer(fusion_db, "SELECT * FROM clientes WHERE id = 21")
    assert len(rows_21) == 1
    cli_21 = dict(rows_21[0])
    assert cli_21["deuda_actual"] == pytest.approx(39272.5)
    assert cli_21["dni"] == "30111222"
    assert cli_21["telefono"] == "11223344"
    assert cli_21["limite_credito"] == pytest.approx(50000.0)

    # Check client 170 is deleted
    rows_170 = _leer(fusion_db, "SELECT * FROM clientes WHERE id = 170")
    assert len(rows_170) == 0

    # Check cuenta_corriente movements are now both under client 21
    movs = [dict(r) for r in _leer(fusion_db, "SELECT * FROM cuenta_corriente WHERE cliente_id = 21 ORDER BY id ASC")]
    assert len(movs) == 2
    assert movs[0]["id"] == 1
    assert movs[0]["saldo_resultante"] == pytest.approx(10000.0)
    assert movs[1]["id"] == 2
    assert movs[1]["saldo_resultante"] == pytest.approx(39272.5)


def test_fusionar_cliente_mismo_id(fusion_db):
    motor = MotorCuenta()
    exito, deuda, msg = motor.fusionar_clientes(21, 21)
    assert exito is False
    assert "consigo mismo" in msg


def test_fusionar_cliente_inexistente(fusion_db):
    motor = MotorCuenta()
    exito, deuda, msg = motor.fusionar_clientes(21, 9999)
    assert exito is False
    assert "No se encontró" in msg


def test_fusionar_clientes_con_abonos_y_cargos_multiples(fusion_db):
    motor = MotorCuenta()
    # Insert an abono on client 170
    with sqlite3.connect(fusion_db) as conn:
        conn.execute(
            """
            INSERT INTO cuenta_corriente (cliente_id, fecha, tipo, monto, saldo_resultante, descripcion)
            VALUES (170, '2026-11-14 11:00:00', 'ABONO', 5000.0, 24272.5, 'Cobro parcial')
            """
        )
        conn.execute("UPDATE clientes SET deuda_actual = 24272.5 WHERE id = 170")

    exito, nueva_deuda, info = motor.fusionar_clientes(21, 170)
    assert exito is True
    # Initial 21 was 10,000; 170 had 29,272.5 - 5,000 = 24,272.5. Total = 34,272.5
    assert nueva_deuda == pytest.approx(34272.5)

    movs = [dict(r) for r in _leer(fusion_db, "SELECT * FROM cuenta_corriente WHERE cliente_id = 21 ORDER BY id ASC")]
    assert len(movs) == 3
    assert movs[0]["saldo_resultante"] == pytest.approx(10000.0)
    assert movs[1]["saldo_resultante"] == pytest.approx(39272.5)
    assert movs[2]["saldo_resultante"] == pytest.approx(34272.5)


def test_dialogo_fusionar_cliente_ui(fusion_db):
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from src.admin.clientes.componentes.dialogo_fusionar_cliente import DialogoFusionarCliente

    dlg = DialogoFusionarCliente(cliente_id_inicial=170)
    assert dlg._id_destino == 21
    assert dlg._id_origen == 170
    assert dlg.btn_confirmar.isEnabled() is True
    assert "39,272.50" in dlg.lbl_resumen_detalle.text()

    dlg._invertir_seleccion()
    assert dlg._id_destino == 170
    assert dlg._id_origen == 21

    dlg._invertir_seleccion()
    assert dlg._id_destino == 21
    assert dlg._id_origen == 170
