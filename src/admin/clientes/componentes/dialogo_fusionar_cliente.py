"""Diálogo para unificar / mutar dos clientes en uno solo sin pérdida de datos."""

from decimal import Decimal
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QCursor, QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.admin.clientes.theme import _CLI
from src.clientes_fiado.cerebro.cerebro import cerebro
from src.utils.letra import fuente_id, fuente_nombre, fuente_numero, vestir_id, vestir_nombre, vestir_numero
from src.utils.qt_compat import qt_exec


class DialogoFusionarCliente(QDialog):
    """
    Permite consolidar dos fichas de clientes en una sola:
    - Cliente destino (se conserva)
    - Cliente origen (se absorbe y se elimina la duplicidad)
    Todos los movimientos de cuenta corriente, tickets fiados y cobros
    se migran íntegramente y la deuda se recalcula de forma atómica.
    """

    def __init__(self, cliente_id_inicial=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unificar / Mutar Clientes")
        self.setModal(True)
        self.setMinimumWidth(820)
        self.setMinimumHeight(600)
        self.setStyleSheet(
            f"QDialog {{ background: #F8FAFC; }} "
            f"QLabel {{ color: {_CLI['text']}; border: none; }}"
        )

        self._clientes_todos = []
        self._id_destino = None
        self._id_origen = None
        self._cliente_inicial = cliente_id_inicial

        self._build_ui()
        self._cargar_catalogo_clientes()

        if self._cliente_inicial:
            self._preseleccionar_inicial(self._cliente_inicial)

    def _build_ui(self):
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(24, 20, 24, 20)
        root_lay.setSpacing(14)

        # ── Cabecera ──────────────────────────────────────────────
        hdr = QVBoxLayout()
        hdr.setSpacing(4)
        lbl_tit = QLabel("Unificar y Mutar Clientes Duplicados")
        lbl_tit.setStyleSheet(
            "font-family: 'Segoe UI', sans-serif; font-size: 20px; font-weight: 900; color: #0F172A;"
        )
        hdr.addWidget(lbl_tit)

        lbl_sub = QLabel(
            "Consolida dos cuentas en una sola ficha. Todos los tickets de venta fiados, abonos, "
            "cargos históricos y movimientos se trasladan a la ficha principal sin pérdida de datos."
        )
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet(
            "font-family: 'Segoe UI', sans-serif; font-size: 13px; color: #64748B; font-weight: 600;"
        )
        hdr.addWidget(lbl_sub)
        root_lay.addLayout(hdr)

        # ── Columnas de selección (Destino vs Origen) ──────────────
        cards_lay = QHBoxLayout()
        cards_lay.setSpacing(14)

        # Tarjeta 1: Destino (Se conserva)
        self.card_dest, self.cmb_dest, self.lbl_dest_info = self._crear_panel_cliente(
            titulo="1. CLIENTE PRINCIPAL (SE CONSERVA)",
            color_borde="#3B82F6",
            color_badge="#DBEAFE",
            texto_badge="✔ SE CONSERVA EN EL SISTEMA",
            color_badge_txt="#1E40AF",
            es_destino=True,
        )
        cards_lay.addWidget(self.card_dest, stretch=1)

        # Botón central para invertir
        col_inv = QVBoxLayout()
        col_inv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_invertir = QPushButton("⇄\nInvertir")
        self.btn_invertir.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_invertir.setToolTip("Intercambiar cliente principal y duplicado")
        self.btn_invertir.setFixedSize(68, 68)
        self.btn_invertir.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #2563EB; border: 2px solid #CBD5E1; "
            "border-radius: 12px; font-family: 'Segoe UI', sans-serif; font-weight: 900; font-size: 13px; }"
            "QPushButton:hover { background: #EFF6FF; border-color: #3B82F6; }"
            "QPushButton:pressed { background: #DBEAFE; }"
        )
        self.btn_invertir.clicked.connect(self._invertir_seleccion)
        col_inv.addWidget(self.btn_invertir)
        cards_lay.addLayout(col_inv)

        # Tarjeta 2: Origen (Se absorbe)
        self.card_orig, self.cmb_orig, self.lbl_orig_info = self._crear_panel_cliente(
            titulo="2. CLIENTE DUPLICADO (A ABSORBER)",
            color_borde="#F59E0B",
            color_badge="#FEF3C7",
            texto_badge="⚠️ SE ABSORBE Y ELIMINA",
            color_badge_txt="#92400E",
            es_destino=False,
        )
        cards_lay.addWidget(self.card_orig, stretch=1)
        root_lay.addLayout(cards_lay, stretch=1)

        # ── Resumen / Vista previa de la consolidación ─────────────
        self.panel_resumen = QFrame()
        self.panel_resumen.setStyleSheet(
            "QFrame { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 12px; }"
        )
        res_lay = QVBoxLayout(self.panel_resumen)
        res_lay.setContentsMargins(14, 10, 14, 10)
        res_lay.setSpacing(6)

        lbl_res_tit = QLabel("VISTA PREVIA DEL RESULTADO CONSOLIDADO")
        lbl_res_tit.setStyleSheet(
            "font-family: 'Segoe UI', sans-serif; font-size: 11px; font-weight: 900; color: #475569; letter-spacing: 0.5px;"
        )
        res_lay.addWidget(lbl_res_tit)

        self.lbl_resumen_detalle = QLabel("Seleccione ambos clientes para calcular la deuda y movimientos a unificar.")
        self.lbl_resumen_detalle.setWordWrap(True)
        self.lbl_resumen_detalle.setStyleSheet(
            "font-family: 'Segoe UI', sans-serif; font-size: 13px; color: #0F172A; font-weight: 700;"
        )
        res_lay.addWidget(self.lbl_resumen_detalle)
        root_lay.addWidget(self.panel_resumen)

        # ── Botones de pie ────────────────────────────────────────
        foot_lay = QHBoxLayout()
        foot_lay.setSpacing(10)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet("color: #DC2626; font-weight: 800; font-size: 12px;")
        foot_lay.addWidget(self.lbl_estado, stretch=1)

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_cancelar.setFixedHeight(40)
        btn_cancelar.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #475569; border: 1px solid #CBD5E1; "
            "border-radius: 8px; font-weight: 800; font-size: 13px; padding: 0 18px; }"
            "QPushButton:hover { background: #F1F5F9; border-color: #94A3B8; }"
        )
        btn_cancelar.clicked.connect(self.reject)
        foot_lay.addWidget(btn_cancelar)

        self.btn_confirmar = QPushButton("UNIFICAR CLIENTES")
        self.btn_confirmar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_confirmar.setFixedHeight(40)
        self.btn_confirmar.setEnabled(False)
        self.btn_confirmar.setStyleSheet(
            "QPushButton { background: #2563EB; color: #FFFFFF; border: none; "
            "border-radius: 8px; font-weight: 900; font-size: 13px; padding: 0 24px; }"
            "QPushButton:hover { background: #1D4ED8; }"
            "QPushButton:pressed { background: #1E40AF; }"
            "QPushButton:disabled { background: #CBD5E1; color: #64748B; }"
        )
        self.btn_confirmar.clicked.connect(self._ejecutar_fusion)
        foot_lay.addWidget(self.btn_confirmar)

        root_lay.addLayout(foot_lay)

    def _crear_panel_cliente(self, titulo, color_borde, color_badge, texto_badge, color_badge_txt, es_destino):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: #FFFFFF; border: 2px solid {color_borde}; border-radius: 12px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        tit = QLabel(titulo)
        tit.setStyleSheet(
            "font-family: 'Segoe UI', sans-serif; font-size: 12px; font-weight: 900; color: #0F172A;"
        )
        lay.addWidget(tit)

        badge = QLabel(f" {texto_badge} ")
        badge.setStyleSheet(
            f"background: {color_badge}; color: {color_badge_txt}; border: none; "
            f"border-radius: 6px; font-weight: 800; font-size: 11px; padding: 3px 6px;"
        )
        badge.setFixedHeight(22)
        lay.addWidget(badge)

        cmb = QComboBox()
        cmb.setEditable(True)
        cmb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        cmb.setStyleSheet(
            "QComboBox { background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px; "
            "padding: 6px 10px; font-family: 'Segoe UI', sans-serif; font-size: 13px; font-weight: 700; }"
            "QComboBox:focus { border-color: #2563EB; background: #FFFFFF; }"
        )
        completer = cmb.completer()
        if completer:
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.activated.connect(lambda text, c=cmb: self._on_completer_activated(c, text))

        if cmb.lineEdit():
            cmb.lineEdit().editingFinished.connect(
                self._on_dest_cambiado if es_destino else self._on_orig_cambiado
            )

        lay.addWidget(cmb)

        info_lbl = QLabel("Sin cliente seleccionado")
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(
            "background: #F8FAFC; border: 1px dashed #E2E8F0; border-radius: 8px; padding: 10px; "
            "font-family: 'Segoe UI', sans-serif; font-size: 12px; color: #334155;"
        )
        lay.addWidget(info_lbl, stretch=1)

        if es_destino:
            cmb.currentIndexChanged.connect(self._on_dest_cambiado)
        else:
            cmb.currentIndexChanged.connect(self._on_orig_cambiado)

        return frame, cmb, info_lbl

    def _cargar_catalogo_clientes(self):
        try:
            todos = cerebro.listar() or []
        except Exception:
            todos = []
        self._clientes_todos = [dict(c) for c in todos]

        self.cmb_dest.blockSignals(True)
        self.cmb_orig.blockSignals(True)
        self.cmb_dest.clear()
        self.cmb_orig.clear()

        self.cmb_dest.addItem("-- Seleccionar cliente destino --", None)
        self.cmb_orig.addItem("-- Seleccionar cliente duplicado --", None)

        for c in sorted(self._clientes_todos, key=lambda x: str(x.get("nombre") or "").casefold()):
            cid = c.get("id")
            nombre = str(c.get("nombre") or "").strip()
            dni = str(c.get("dni") or "").strip()
            deuda = float(c.get("deuda_actual") or 0)
            dni_txt = f" · DNI: {dni}" if dni else ""
            deuda_txt = f" · Deuda: ${deuda:,.2f}" if deuda > 0 else " · Al día"
            item_text = f"#{cid} {nombre}{dni_txt}{deuda_txt}"

            self.cmb_dest.addItem(item_text, cid)
            self.cmb_orig.addItem(item_text, cid)

        self.cmb_dest.blockSignals(False)
        self.cmb_orig.blockSignals(False)

    def _preseleccionar_inicial(self, cid):
        cliente_ref = self._hallar_cliente(cid)
        if not cliente_ref:
            idx_dest = self.cmb_dest.findData(cid)
            if idx_dest > 0:
                self.cmb_dest.setCurrentIndex(idx_dest)
            return

        nombre_ref = str(cliente_ref.get("nombre") or "").strip().casefold()
        candidatos = [
            c for c in self._clientes_todos
            if int(c.get("id")) != int(cid) and str(c.get("nombre") or "").strip().casefold() == nombre_ref
        ]
        if candidatos:
            candidato_id = candidatos[0]["id"]
            # Si el cliente abierto tiene ID mayor (creado después por el cajero),
            # se propone conservar el cliente original histórico (menor ID) y absorber el duplicado.
            if int(cid) > int(candidato_id):
                id_a_conservar = candidato_id
                id_a_absorber = cid
            else:
                id_a_conservar = cid
                id_a_absorber = candidato_id

            idx_dest = self.cmb_dest.findData(id_a_conservar)
            if idx_dest > 0:
                self.cmb_dest.setCurrentIndex(idx_dest)
            idx_orig = self.cmb_orig.findData(id_a_absorber)
            if idx_orig > 0:
                self.cmb_orig.setCurrentIndex(idx_orig)
        else:
            idx_dest = self.cmb_dest.findData(cid)
            if idx_dest > 0:
                self.cmb_dest.setCurrentIndex(idx_dest)

    def _hallar_cliente(self, cid):
        if not cid:
            return None
        for c in self._clientes_todos:
            if int(c.get("id") or 0) == int(cid):
                return c
        return None

    def _resolver_cliente_combo(self, cmb):
        cid = cmb.currentData()
        if cid:
            return cid
        txt = cmb.currentText().strip()
        if not txt or txt.startswith("--"):
            return None
        import re
        m = re.search(r"#?(\d+)", txt)
        if m:
            try:
                cand_id = int(m.group(1))
                if any(int(c.get("id") or 0) == cand_id for c in self._clientes_todos):
                    return cand_id
            except (ValueError, TypeError):
                pass
        txt_lower = txt.casefold()
        for c in self._clientes_todos:
            if str(c.get("nombre") or "").strip().casefold() == txt_lower:
                return c.get("id")
            if str(c.get("dni") or "").strip() == txt:
                return c.get("id")
        for i in range(1, cmb.count()):
            if txt_lower in cmb.itemText(i).casefold():
                return cmb.itemData(i)
        return None

    def _on_completer_activated(self, cmb, text):
        idx = cmb.findText(text)
        if idx >= 0:
            cmb.setCurrentIndex(idx)
        else:
            cid = self._resolver_cliente_combo(cmb)
            if cid:
                idx = cmb.findData(cid)
                if idx >= 0:
                    cmb.setCurrentIndex(idx)

    def _on_dest_cambiado(self):
        cid = self._resolver_cliente_combo(self.cmb_dest)
        self._id_destino = cid
        self._actualizar_info_card(cid, self.lbl_dest_info, es_destino=True)
        self._actualizar_vista_previa()

    def _on_orig_cambiado(self):
        cid = self._resolver_cliente_combo(self.cmb_orig)
        self._id_origen = cid
        self._actualizar_info_card(cid, self.lbl_orig_info, es_destino=False)
        self._actualizar_vista_previa()

    def _actualizar_info_card(self, cid, lbl_widget, es_destino):
        if not cid:
            lbl_widget.setText("Sin cliente seleccionado")
            return

        cli = self._hallar_cliente(cid)
        if not cli:
            lbl_widget.setText("No se encontró la información del cliente")
            return

        nombre = str(cli.get("nombre") or "—").strip()
        dni = str(cli.get("dni") or "Sin DNI").strip() or "Sin DNI"
        tel = str(cli.get("telefono") or "Sin teléfono").strip() or "Sin teléfono"
        dir_cli = str(cli.get("direccion") or "Sin dirección").strip() or "Sin dirección"
        deuda = float(cli.get("deuda_actual") or 0)
        limite = float(cli.get("limite_credito") or 0)
        tipo = str(cli.get("tipo_cliente") or "regular").title()

        # Contar movimientos registrados
        try:
            movs = cerebro.movimientos(cid) or []
            n_movs = len(movs)
        except Exception:
            n_movs = 0

        color_deuda = "#DC2626" if deuda > 0 else "#059669"
        deuda_html = f"<span style='color: {color_deuda}; font-weight: 900; font-size: 14px;'>${deuda:,.2f}</span>"

        html = (
            f"<div style='line-height: 1.4;'>"
            f"<b>ID:</b> <span style='font-family: Consolas;'>#{cid}</span><br>"
            f"<b>Nombre:</b> <span style='font-size: 13px; font-weight: 900;'>{nombre}</span><br>"
            f"<b>DNI:</b> {dni} &nbsp;·&nbsp; <b>Tel:</b> {tel}<br>"
            f"<b>Dirección:</b> {dir_cli}<br>"
            f"<b>Categoría:</b> {tipo} &nbsp;·&nbsp; <b>Límite:</b> ${limite:,.2f}<br>"
            f"<b>Deuda actual:</b> {deuda_html}<br>"
            f"<b>Historial:</b> {n_movs} movimientos registrados"
            f"</div>"
        )
        lbl_widget.setText(html)

    def _invertir_seleccion(self):
        dest_idx = self.cmb_dest.currentIndex()
        orig_idx = self.cmb_orig.currentIndex()

        self.cmb_dest.blockSignals(True)
        self.cmb_orig.blockSignals(True)

        self.cmb_dest.setCurrentIndex(orig_idx)
        self.cmb_orig.setCurrentIndex(dest_idx)

        self.cmb_dest.blockSignals(False)
        self.cmb_orig.blockSignals(False)

        self._id_destino = self.cmb_dest.currentData()
        self._id_origen = self.cmb_orig.currentData()

        self._actualizar_info_card(self._id_destino, self.lbl_dest_info, es_destino=True)
        self._actualizar_info_card(self._id_origen, self.lbl_orig_info, es_destino=False)
        self._actualizar_vista_previa()

    def _actualizar_vista_previa(self):
        self.lbl_estado.setText("")
        self.btn_confirmar.setEnabled(False)

        dest_id = self._id_destino
        orig_id = self._id_origen

        if not dest_id or not orig_id:
            self.lbl_resumen_detalle.setText("Seleccione ambos clientes para calcular la deuda y movimientos a unificar.")
            return

        if int(dest_id) == int(orig_id):
            self.lbl_estado.setText("⚠️ Debe seleccionar dos clientes distintos para realizar la fusión.")
            self.lbl_resumen_detalle.setText("No se puede unificar un cliente consigo mismo.")
            return

        c_dest = self._hallar_cliente(dest_id)
        c_orig = self._hallar_cliente(orig_id)
        if not c_dest or not c_orig:
            return

        deuda_dest = float(c_dest.get("deuda_actual") or 0)
        deuda_orig = float(c_orig.get("deuda_actual") or 0)
        deuda_total_estimada = deuda_dest + deuda_orig

        # Movimientos del origen que pasarán al destino
        try:
            movs_orig = cerebro.movimientos(orig_id) or []
            n_transf = len(movs_orig)
        except Exception:
            n_transf = 0

        nom_dest = str(c_dest.get("nombre") or "").strip()
        nom_orig = str(c_orig.get("nombre") or "").strip()

        dni_dest = str(c_dest.get("dni") or "").strip()
        dni_orig = str(c_orig.get("dni") or "").strip()
        dni_res = dni_dest or (f"{dni_orig} (heredado del duplicado)" if dni_orig else "Sin DNI")

        html = (
            f"<div style='line-height: 1.5;'>"
            f"• <b>Ficha conservada:</b> #{dest_id} <b>{nom_dest}</b><br>"
            f"• <b>Ficha absorbida y eliminada:</b> #{orig_id} <b>{nom_orig}</b><br>"
            f"• <b>Tickets y movimientos a transferir:</b> <span style='color: #2563EB; font-weight: 800;'>{n_transf} movimientos</span><br>"
            f"• <b>Deuda consolidada final:</b> "
            f"<span style='color: #DC2626; font-weight: 900; font-size: 15px;'>${deuda_total_estimada:,.2f}</span> "
            f"(Destino: ${deuda_dest:,.2f} + Duplicado: ${deuda_orig:,.2f})<br>"
            f"• <b>DNI final:</b> {dni_res}"
            f"</div>"
        )
        self.lbl_resumen_detalle.setText(html)
        self.btn_confirmar.setEnabled(True)

    def _ejecutar_fusion(self):
        dest_id = self._id_destino
        orig_id = self._id_origen

        if not dest_id or not orig_id or int(dest_id) == int(orig_id):
            return

        c_dest = self._hallar_cliente(dest_id)
        c_orig = self._hallar_cliente(orig_id)
        nom_dest = str(c_dest.get("nombre") or "").strip()
        nom_orig = str(c_orig.get("nombre") or "").strip()

        pregunta = (
            f"¿Está seguro de fusionar y unificar estos dos clientes?\n\n"
            f"▶ Cliente Principal (Se Conserva): #{dest_id} - {nom_dest}\n"
            f"▶ Cliente Duplicado (A Absorber): #{orig_id} - {nom_orig}\n\n"
            f"Todos los tickets de venta fiados, pagos y deudas de #{orig_id} se trasladarán "
            f"a la cuenta de #{dest_id}. La ficha duplicada se eliminará para no generar confusiones.\n\n"
            f"Esta operación es definitiva y no puede deshacerse."
        )

        resp = QMessageBox.question(
            self,
            "Confirmar unificación de clientes",
            pregunta,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        self.btn_confirmar.setEnabled(False)
        self.lbl_estado.setText("Procesando unificación y recalculando deudas...")

        exito, nueva_deuda, info = cerebro.fusionar_clientes(dest_id, orig_id)

        if not exito:
            self.btn_confirmar.setEnabled(True)
            msg_error = str(info) if isinstance(info, str) else "Error al fusionar clientes."
            self.lbl_estado.setText(f"❌ {msg_error}")
            QMessageBox.critical(self, "Error al unificar", f"No se pudo completar la unificación:\n{msg_error}")
            return

        movs_migrados = info.get("movimientos_migrados", 0) if isinstance(info, dict) else 0

        QMessageBox.information(
            self,
            "Unificación exitosa",
            f"Los clientes se han unificado correctamente.\n\n"
            f"• Ficha conservada: #{dest_id} {nom_dest}\n"
            f"• Movimientos y tickets transferidos: {movs_migrados}\n"
            f"• Nueva deuda consolidada: ${nueva_deuda:,.2f}\n"
            f"• Duplicado #{orig_id} eliminado exitosamente.",
        )
        self.accept()
