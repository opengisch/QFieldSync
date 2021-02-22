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
import os
from qgis.PyQt.QtCore import pyqtSlot
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QPushButton
)
from qgis.core import QgsProject
from qgis.PyQt.uic import loadUiType

from qfieldsync.core.preferences import Preferences

from qfieldsync.utils.qgis_utils import open_project, import_checksums_of_project
from qfieldsync.utils.qt_utils import make_folder_selector

from qfieldsync.libqfieldsync.utils.exceptions import NoProjectFoundError
from qfieldsync.libqfieldsync.utils.file_utils import get_project_in_folder, import_file_checksum, copy_images
from qfieldsync.libqfieldsync import ProjectConfiguration

DialogUi, _ = loadUiType(os.path.join(os.path.dirname(__file__), '../ui/synchronize_dialog.ui'))


class SynchronizeDialog(QDialog, DialogUi):

    def __init__(self, iface, offline_editing, parent=None):
        """Constructor.
        """
        super(SynchronizeDialog, self).__init__(parent=parent)
        self.setupUi(self)
        self.iface = iface
        self.preferences = Preferences()
        self.offline_editing = offline_editing
        self.button_box.button(QDialogButtonBox.Save).setText(self.tr('Synchronize'))
        self.button_box.button(QDialogButtonBox.Save).clicked.connect(self.start_synchronization)
        self.qfieldDir.setText(self.preferences.value('importDirectoryProject') or self.preferences.value('importDirectory'))
        self.qfieldDir_button.clicked.connect(make_folder_selector(self.qfieldDir))

        self.offline_editing_done = False

    def start_synchronization(self):
        self.button_box.button(QDialogButtonBox.Save).setEnabled(False)
        qfield_folder = self.qfieldDir.text()
        self.preferences.set_value('importDirectoryProject', qfield_folder)
        try:
            current_import_file_checksum = import_file_checksum(qfield_folder)
            imported_files_checksums = import_checksums_of_project(qfield_folder)

            if imported_files_checksums and current_import_file_checksum and current_import_file_checksum in imported_files_checksums:
                message = self.tr("Data from this file are already synchronized with the original project.")
                raise NoProjectFoundError(message)
            qgs_file = get_project_in_folder(qfield_folder)
            open_project(qgs_file)
            self.offline_editing.progressStopped.connect(self.update_done)
            self.offline_editing.layerProgressUpdated.connect(self.update_total)
            self.offline_editing.progressModeSet.connect(self.update_mode)
            self.offline_editing.progressUpdated.connect(self.update_value)
            self.offline_editing.synchronize()
            if self.offline_editing_done:
                original_project_path = ProjectConfiguration(QgsProject.instance()).original_project_path
                if original_project_path:
                    # import the DCIM folder
                    copy_images(os.path.join(qfield_folder, "DCIM"),os.path.join(os.path.dirname(original_project_path), "DCIM"))
                    if open_project(original_project_path):
                        # save the data_file_checksum to the project and save it
                        imported_files_checksums.append(import_file_checksum(qfield_folder))
                        ProjectConfiguration(QgsProject.instance()).imported_files_checksums = imported_files_checksums
                        QgsProject.instance().write()
                        self.iface.messageBar().pushInfo('QFieldSync', self.tr("Opened original project {}".format(original_project_path)))
                    else:
                        self.iface.messageBar().pushInfo('QFieldSync', self.tr("The data has been synchronized successfully but the original project ({}) could not be opened".format(original_project_path)))
                else:
                    self.iface.messageBar().pushInfo('QFieldSync', self.tr("No original project path found"))
                self.close()
            else:
                message = self.tr("The project you imported does not seem to be an offline project")
                raise NoProjectFoundError(message)
        except NoProjectFoundError as e:
            self.iface.messageBar().pushWarning('QFieldSync', str(e))

    @pyqtSlot(int, int)
    def update_total(self, current, layer_count):
        self.totalProgressBar.setMaximum(layer_count)
        self.totalProgressBar.setValue(current)

    @pyqtSlot(int)
    def update_value(self, progress):
        self.layerProgressBar.setValue(progress)

    @pyqtSlot('QgsOfflineEditing::ProgressMode', int)
    def update_mode(self, _, mode_count):
        self.layerProgressBar.setMaximum(mode_count)
        self.layerProgressBar.setValue(0)

    @pyqtSlot()
    def update_done(self):
        self.offline_editing.progressStopped.disconnect(self.update_done)
        self.offline_editing.layerProgressUpdated.disconnect(self.update_total)
        self.offline_editing.progressModeSet.disconnect(self.update_mode)
        self.offline_editing.progressUpdated.disconnect(self.update_value)
        self.offline_editing_done = True
