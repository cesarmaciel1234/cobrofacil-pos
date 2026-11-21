from src.central_red_global.servidor.pareja import buscar


def test_descubrimiento_rechaza_otra_identidad_de_tienda(monkeypatch):
    monkeypatch.setattr(buscar, "_guardada", lambda: "192.168.1.20")
    monkeypatch.setattr(buscar, "_store_id_guardado", lambda: "tienda-a")
    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda _host: True)

    elegida = buscar._elegir_aviso(
        [
            {
                "server_ip": "192.168.1.30",
                "store_id": "tienda-b",
                "mode": "MAESTRA",
            },
            {
                "server_ip": "192.168.1.40",
                "store_id": "tienda-a",
                "mode": "MAESTRA",
            },
        ]
    )

    assert elegida["server_ip"] == "192.168.1.40"


def test_descubrimiento_rechaza_maestra_sin_identidad(monkeypatch):
    monkeypatch.setattr(buscar, "_guardada", lambda: "192.168.1.20")
    monkeypatch.setattr(buscar, "_store_id_guardado", lambda: "tienda-a")
    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda _host: True)

    assert buscar._elegir_aviso(
        [
            {
                "server_ip": "192.168.1.30",
                "mode": "MAESTRA",
            },
        ]
    ) == {}


def test_sin_identidad_no_salta_de_ip_a_otro_servidor(monkeypatch):
    monkeypatch.setattr(buscar, "_guardada", lambda: "192.168.1.20")
    monkeypatch.setattr(buscar, "_store_id_guardado", lambda: "")
    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda _host: True)

    assert buscar._elegir_aviso(
        [
            {
                "server_ip": "192.168.1.30",
                "store_id": "tienda-a",
                "mode": "MAESTRA",
            },
        ]
    ) == {}


def test_descubrimiento_prefiere_ip_enlazada_si_sigue_anunciada(monkeypatch):
    monkeypatch.setattr(buscar, "_guardada", lambda: "192.168.1.20")
    monkeypatch.setattr(buscar, "_store_id_guardado", lambda: "tienda-a")
    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda _host: True)
    guardada = {
        "server_ip": "192.168.1.20",
        "store_id": "tienda-a",
        "mode": "MAESTRA",
    }

    assert buscar._elegir_aviso(
        [
            {
                "server_ip": "192.168.1.30",
                "store_id": "tienda-a",
                "mode": "MAESTRA",
            },
            guardada,
        ]
    ) == guardada


def test_buscar_no_acepta_ip_guardada_sin_anuncio_de_identidad(monkeypatch):
    from src.central_red_global import master_presence

    monkeypatch.setattr(master_presence, "es_pc_maestra_local", lambda: False)
    monkeypatch.setattr(buscar, "_guardada", lambda: "192.168.1.20")
    monkeypatch.setattr(buscar, "_store_id_guardado", lambda: "tienda-a")
    monkeypatch.setattr(buscar, "oir_anuncios", lambda: [])
    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda _host: True)

    assert buscar.buscar() == ""


def test_buscar_rechaza_ip_guardada_con_identidad_distinta(monkeypatch):
    from src.central_red_global import master_presence

    monkeypatch.setattr(master_presence, "es_pc_maestra_local", lambda: False)
    monkeypatch.setattr(buscar, "_guardada", lambda: "192.168.1.20")
    monkeypatch.setattr(buscar, "_store_id_guardado", lambda: "tienda-a")
    monkeypatch.setattr(
        buscar,
        "oir_anuncios",
        lambda: [{"server_ip": "192.168.1.20", "store_id": "tienda-b"}],
    )
    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda _host: True)

    assert buscar.buscar() == ""


def test_buscar_confirma_identidad_del_host_guardado(monkeypatch):
    from src.central_red_global import master_presence

    llamadas = []
    monkeypatch.setattr(master_presence, "es_pc_maestra_local", lambda: False)
    monkeypatch.setattr(buscar, "_guardada", lambda: "192.168.1.20")
    monkeypatch.setattr(buscar, "_store_id_guardado", lambda: "tienda-a")
    monkeypatch.setattr(
        buscar,
        "oir_anuncios",
        lambda: llamadas.append("udp") or [{
            "server_ip": "192.168.1.20",
            "store_id": "tienda-a",
            "mode": "MAESTRA",
        }],
    )
    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda _host: True)

    assert buscar.buscar() == "192.168.1.20"
    assert llamadas == ["udp"]


def test_identidad_para_ip_acepta_la_tienda_enlazada(monkeypatch):
    monkeypatch.setattr(buscar, "oir_anuncios", lambda: [{
        "server_ip": "192.168.1.30",
        "store_id": "tienda-a",
        "mode": "MAESTRA",
    }])
    monkeypatch.setattr(buscar, "_store_id_guardado", lambda: "tienda-a")
    monkeypatch.setattr(buscar, "_guardada", lambda: "192.168.1.20")
    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda _host: True)

    assert buscar.identidad_para_ip("192.168.1.30") == "tienda-a"


def test_identidad_para_ip_rechaza_otro_negocio(monkeypatch):
    monkeypatch.setattr(buscar, "oir_anuncios", lambda: [{
        "server_ip": "192.168.1.30",
        "store_id": "tienda-b",
        "mode": "MAESTRA",
    }])
    monkeypatch.setattr(buscar, "_store_id_guardado", lambda: "tienda-a")
    monkeypatch.setattr(buscar, "_guardada", lambda: "192.168.1.20")
    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda _host: True)

    assert buscar.identidad_para_ip("192.168.1.30") == ""


def test_reconectar_en_fondo_actualiza_engine_a_ip_adoptada(monkeypatch):
    from src.base_de_datos.repos.red import RedRepoMixin

    class Engine:
        host = "192.168.1.20"

    class Repo(RedRepoMixin):
        db_engine_type = "mariadb"
        mariadb_engine = Engine()
        is_master = False

        def _host_tienda(self):
            return "192.168.1.30"

        def _buscar_maestra_en_fondo(self, host):
            self.descubierta = host

    repo = Repo()
    assert repo.asegurar_lectura_tienda() is False
    assert repo.descubierta == "192.168.1.30"


def test_busqueda_en_fondo_reconecta_a_la_ip_descubierta(monkeypatch):
    import threading

    from src.base_de_datos.repos import red

    encontrada = threading.Event()

    class Repo(red.RedRepoMixin):
        def _host_tienda(self):
            return "192.168.1.20"

        def reconectar_mariadb(self, host):
            self.host_enlazado = host
            encontrada.set()

    monkeypatch.setattr(
        "src.central_red_global.servidor.pareja.buscar.buscar",
        lambda: "192.168.1.30",
    )
    repo = Repo()
    repo._buscar_maestra_en_fondo("192.168.1.20")

    assert encontrada.wait(2)
    assert repo.host_enlazado == "192.168.1.30"


def test_reserva_no_se_promueve_sin_identidad_de_tienda(monkeypatch):
    from src.central_red_global.servidor.pareja import promover
    from src.config import config
    from src.jefe.nodo_portable.espejo import copia

    monkeypatch.setattr(copia, "existe", lambda: True)
    monkeypatch.setattr(config, "get", lambda key, default=None: "" if key == "store_id" else default)

    assert promover._promover() is False


def test_cesion_exige_identidad_y_tienda_comprobada(monkeypatch):
    from src.base_de_datos.autoblindaje.quien.maestra import Quien
    from src.central_red_global import master_presence
    from src.central_red_global.servidor.pareja import promover
    from src.config import config
    from src.services.mariadb_controller import mariadb_controller

    data = {"is_master": True, "db_host": "127.0.0.1", "store_id": "tienda-a"}
    monkeypatch.setattr(config, "data", data)
    monkeypatch.setattr(config, "save", lambda: None)
    monkeypatch.setattr(config, "_leer_json", lambda: dict(config.data))
    monkeypatch.setattr(master_presence, "es_pc_maestra_local", lambda: True)
    monkeypatch.setattr(Quien, "_es_esta_pc", lambda _ip: False)
    avisos = [{"server_ip": "192.0.2.1", "store_id": "tienda-b", "db_engine": "mariadb"}]
    monkeypatch.setattr(buscar, "oir_anuncios", lambda: avisos)
    comprobadas = []
    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda ip: comprobadas.append(ip) or False)
    apagados = []
    monkeypatch.setattr(mariadb_controller, "stop_server", lambda: apagados.append(True))

    assert promover.ceder_si_hay_otra() is False
    assert comprobadas == []
    assert apagados == []
    assert data["is_master"] is True

    avisos[0]["store_id"] = "tienda-a"
    assert promover.ceder_si_hay_otra() is False
    assert comprobadas == ["192.0.2.1"]
    assert apagados == []

    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda _ip: True)
    assert promover.ceder_si_hay_otra() is True
    assert data["db_host"] == "192.0.2.1"
    assert data["is_master"] is False
    assert apagados == [True]


def test_cesion_no_apaga_mariadb_si_no_se_guardo_el_puesto(monkeypatch):
    from src.base_de_datos.autoblindaje.quien.maestra import Quien
    from src.central_red_global import master_presence
    from src.central_red_global.servidor.pareja import promover
    from src.config import config
    from src.services.mariadb_controller import mariadb_controller

    data = {"is_master": True, "db_host": "127.0.0.1", "store_id": "tienda-a"}
    monkeypatch.setattr(config, "data", data.copy())
    monkeypatch.setattr(config, "save", lambda: None)
    monkeypatch.setattr(config, "_leer_json", lambda: data.copy())
    monkeypatch.setattr(master_presence, "es_pc_maestra_local", lambda: True)
    monkeypatch.setattr(Quien, "_es_esta_pc", lambda _ip: False)
    monkeypatch.setattr(buscar, "oir_anuncios", lambda: [
        {"server_ip": "192.0.2.1", "store_id": "tienda-a", "db_engine": "mariadb"}
    ])
    monkeypatch.setattr(buscar, "tiene_la_tienda", lambda _ip: True)
    apagados = []
    monkeypatch.setattr(mariadb_controller, "stop_server", lambda: apagados.append(True))

    assert promover.ceder_si_hay_otra() is False
    assert config.data == data
    assert apagados == []


def test_cesion_no_adopta_sin_identidad_local(monkeypatch):
    from src.central_red_global import master_presence
    from src.central_red_global.servidor.pareja import promover
    from src.config import config

    monkeypatch.setattr(master_presence, "es_pc_maestra_local", lambda: True)
    monkeypatch.setattr(config, "get", lambda key, default=None: "" if key == "store_id" else default)
    monkeypatch.setattr(buscar, "oir_anuncios", lambda: (_ for _ in ()).throw(AssertionError("No debe buscar")))
    assert promover.ceder_si_hay_otra() is False


def test_promocion_limpia_referencias_a_titular_anterior(monkeypatch):
    import sys
    import types
    from unittest.mock import MagicMock

    from src.central_red_global.servidor.oficio import agente
    from src.central_red_global.servidor.pareja import promover
    from src.config import config
    from src.jefe.nodo_portable.espejo import copia
    from src.services.mariadb_controller import mariadb_controller

    data = {"is_master": False, "store_id": "tienda-a", "preferred_master_ip": "192.0.2.1",
            "carteleria_master_ip": "192.0.2.1"}
    monkeypatch.setattr(config, "data", data)
    monkeypatch.setattr(config, "save", lambda: None)
    monkeypatch.setattr(config, "_leer_json", lambda: dict(config.data))
    monkeypatch.setattr(copia, "existe", lambda: True)
    monkeypatch.setattr(copia, "ruta", lambda: "espejo-ficticio")
    monkeypatch.setattr(promover, "_titular_vive", lambda: False)
    monkeypatch.setattr(mariadb_controller, "start_server", lambda: True)
    monkeypatch.setattr(buscar, "puerto_abierto", lambda _host: True)
    retomas = []
    monkeypatch.setattr(agente, "retomar_oficio", lambda: retomas.append(True))

    manager = MagicMock()
    manager.mariadb_engine._connect_kwargs.return_value = {}
    monkeypatch.setitem(sys.modules, "src.base_de_datos.database", types.SimpleNamespace(db_manager=manager))
    monkeypatch.setitem(sys.modules, "src.base_de_datos.restaurar.aplicar.destino",
                        types.SimpleNamespace(Destino=lambda *args, **kwargs: object()))
    monkeypatch.setitem(sys.modules, "src.base_de_datos.restaurar.aplicar.sumar",
                        types.SimpleNamespace(sumar=lambda *args: {"sin_lugar": []}))

    assert promover._promover() is True
    assert data["is_master"] is True
    assert data["db_host"] == "127.0.0.1"
    assert data["preferred_master_ip"] == ""
    assert data["carteleria_master_ip"] == ""
    assert retomas == [True]

    data.update(is_master=False, db_host="192.0.2.1", preferred_master_ip="192.0.2.1",
                carteleria_master_ip="192.0.2.1")
    anterior = data.copy()
    monkeypatch.setattr(config, "_leer_json", lambda: anterior)
    assert promover._promover() is False
    assert config.data == anterior
    assert manager.is_master is False
    manager.reconectar_local.assert_called_once()
    assert retomas == [True]
