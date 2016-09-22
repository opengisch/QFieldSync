# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QFieldSyncDialog
                                 A QGIS plugin
 Sync your projects to QField on android
                             -------------------
        begin                : 2015-05-20
        git sha              : $Format:%H$
        copyright            : (C) 2015 by OPENGIS.ch
        email                : info@opengis.ch
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from __future__ import absolute_import
from __future__ import print_function

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QDialog, QDialogButtonBox, QPushButton, QMessageBox
from qgis.PyQt.QtWidgets import QApplication, QMessageBox
from qgis.gui import QgsMessageBar
from qgis.core import QgsOfflineEditing, QgsProject

from qfieldsync.utils.file_utils import get_project_in_folder
from qfieldsync.utils.qgis_utils import open_project
from qfieldsync.utils.qt_utils import get_ui_class, make_folder_selector
from qfieldsync.config import *

FORM_CLASS = get_ui_class('synchronize_base.ui')


class PullDialog(QDialog, FORM_CLASS):
    def __init__(self, iface, plugin_instance):
        """Constructor."""
        super(PullDialog, self).__init__(parent=None)
        self.setupUi(self)
        self.iface = iface
        self.offline_editing = plugin_instance.offline_editing
        self.push_btn = QPushButton(self.tr('Synchronize'))
        self.push_btn.clicked.connect(self.start_synchronization)
        self.button_box.addButton(self.push_btn, QDialogButtonBox.ActionRole)
        self.qfieldDir.setText(plugin_instance.get_import_folder())
        self.qfieldDir_btn.clicked.connect(make_folder_selector(self.qfieldDir))

    def start_synchronization(self):
        if (QgsProject.instance().isDirty()):
            title = self.tr('Continue synchronization?')
            text = self.tr('The currently open project is not saved. '
                           'QFieldSync will overwrite it. Continue?')
            answer = QMessageBox.question(self, title, text,
                                          QMessageBox.Yes,
                                          QMessageBox.No)
            if answer == QMessageBox.No:
                return

        qfield_folder = self.qfieldDir.text()
        qgs_file = get_project_in_folder(qfield_folder)
        open_project(qgs_file)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.offline_editing.synchronize()  # no way to know exactly if it
        QApplication.setOverrideCursor()
        self.close()