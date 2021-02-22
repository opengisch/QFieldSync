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

from qfieldsync.gui.project_configuration_dialog import ProjectConfigurationDialog
from qgis.PyQt.QtCore import (
    pyqtSlot,
    Qt
)
from qgis.PyQt.QtGui import (
    QIcon
)
from qgis.PyQt.QtWidgets import (
    QApplication,
    QMessageBox,
    QDialogButtonBox,
    QPushButton,
    QLabel,
    QSizePolicy,
    QDialog
)
from qgis.core import (
    QgsProject,
    QgsApplication,
    QgsProviderRegistry,
    QgsProviderMetadata,
    Qgis
)
from qgis.PyQt.uic import loadUiType
from ..utils.qgis_utils import get_project_title
from ..utils.qt_utils import make_folder_selector
from qfieldsync.core.preferences import Preferences

from qfieldsync.libqfieldsync.utils.file_utils import fileparts, open_folder
from qfieldsync.libqfieldsync import (LayerSource, ProjectConfiguration, OfflineConverter)

DialogUi, _ = loadUiType(os.path.join(os.path.dirname(__file__), '../ui/package_dialog.ui'))


class PackageDialog(QDialog, DialogUi):

    def __init__(self, iface, project, offline_editing, parent=None):
        """Constructor."""
        super(PackageDialog, self).__init__(parent=parent)
        self.setupUi(self)

        self.iface = iface
        self.offline_editing = offline_editing
        self.project = project
        self.qfield_preferences = Preferences()
        self.project_lbl.setText(get_project_title(self.project))
        self.button_box.button(QDialogButtonBox.Save).setText(self.tr('Create'))
        self.button_box.button(QDialogButtonBox.Save).clicked.connect(self.package_project)
        self.button_box.button(QDialogButtonBox.Reset).setText(self.tr('Configure current project...'))
        self.button_box.button(QDialogButtonBox.Reset).setIcon(QIcon(os.path.join(os.path.dirname(__file__), '../resources/project_properties.svg')))
        self.button_box.button(QDialogButtonBox.Reset).clicked.connect(self.show_settings)
        self.iface.mapCanvas().extentsChanged.connect(self.extent_changed)
        self.extent_changed()

        self.devices = None
        # self.refresh_devices()
        self.setup_gui()

        self.offline_editing.warning.connect(self.show_warning)

    def update_progress(self, sent, total):
        progress = float(sent) / total * 100
        self.progress_bar.setValue(progress)

    def setup_gui(self):
        """Populate gui and connect signals of the push dialog"""
        export_folder_path = self.qfield_preferences.value('exportDirectoryProject')
        if not export_folder_path:
            project_fn = QgsProject.instance().fileName()
            export_folder_name = fileparts(project_fn)[1]
            export_folder_path = os.path.join(self.qfield_preferences.value('exportDirectory'), export_folder_name)

        self.manualDir.setText(export_folder_path)
        self.manualDir_btn.clicked.connect(make_folder_selector(self.manualDir))
        self.update_info_visibility()

    def get_export_folder_from_dialog(self):
        """Get the export folder according to the inputs in the selected"""
        # manual
        return self.manualDir.text()

    def package_project(self):
        self.button_box.button(QDialogButtonBox.Save).setEnabled(False)
        self.informationStack.setCurrentWidget(self.progressPage)

        export_folder = self.get_export_folder_from_dialog()

        self.qfield_preferences.set_value('exportDirectoryProject', export_folder)

        offline_convertor = OfflineConverter(self.project, export_folder, self.iface.mapCanvas().extent(),
                                             self.offline_editing)

        # progress connections
        offline_convertor.total_progress_updated.connect(self.update_total)
        offline_convertor.task_progress_updated.connect(self.update_task)
        offline_convertor.warning.connect(lambda title, body: QMessageBox.warning(None, title, body))

        offline_convertor.convert()
        self.do_post_offline_convert_action()
        self.close()

        self.progress_group.setEnabled(False)

    def do_post_offline_convert_action(self):
        """
        Show an information label that the project has been copied
        with a nice link to open the result folder.
        """
        export_folder = self.get_export_folder_from_dialog()

        result_message = self.tr('Finished creating the project at {result_folder}. Please copy this folder to '
                                      'your QField device.').format(result_folder='<a href="{folder}">{folder}</a>'.format(folder=export_folder))
        self.iface.messageBar().pushMessage(result_message, Qgis.Success, 0)

    def update_info_visibility(self):
        """
        Show the info label if there are unconfigured layers
        """
        pathResolver = QgsProject.instance().pathResolver()
        showInfoConfiguration = False
        localizedDataPathLayers = []
        for layer in list(self.project.mapLayers().values()):
            if not LayerSource(layer).is_configured:
                showInfoConfiguration = True
            if layer.dataProvider() is not None:
                metadata = QgsProviderRegistry.instance().providerMetadata(layer.dataProvider().name())
                if metadata is not None:
                    decoded = metadata.decodeUri(layer.source())
                    if "path" in decoded:
                        path = pathResolver.writePath(decoded["path"])
                        if path.startswith("localized:"):
                            localizedDataPathLayers.append('- {} ({})'.format(layer.name(), path[10:]))

        self.infoConfigurationLabel.setVisible(showInfoConfiguration)
        if localizedDataPathLayers:
            if len(localizedDataPathLayers) == 1:
                self.infoLocalizedLayersLabel.setText(self.tr('The layer stored in a localized data path is:\n{}').format("\n".join(localizedDataPathLayers)))
            else:
                self.infoLocalizedLayersLabel.setText(self.tr('The layers stored in a localized data path are:\n{}').format("\n".join(localizedDataPathLayers)))
            self.infoLocalizedLayersLabel.setVisible(True)
            self.infoLocalizedPresentLabel.setVisible(True)
        else:
            self.infoLocalizedLayersLabel.setVisible(False)
            self.infoLocalizedPresentLabel.setVisible(False)
        self.infoGroupBox.setVisible(showInfoConfiguration or len(localizedDataPathLayers) > 0)

        project_configuration = ProjectConfiguration(self.project)

        if project_configuration.offline_copy_only_aoi or project_configuration.create_base_map:
            self.informationStack.setCurrentWidget(self.selectExtentPage)
        else:
            self.informationStack.setCurrentWidget(self.progressPage)

    def show_settings(self):
        if Qgis.QGIS_VERSION_INT >= 31500:
            self.iface.showProjectPropertiesDialog('QField')
        else:
            dlg = ProjectConfigurationDialog(self.iface.mainWindow())
            dlg.exec_()
        self.update_info_visibility()

    @pyqtSlot(int, int, str)
    def update_total(self, current, layer_count, message):
        if current == layer_count and (current == 100 or current == 0):
            QApplication.restoreOverrideCursor()
        elif current == 0 and layer_count == 100:
            QApplication.setOverrideCursor(Qt.WaitCursor)

        self.totalProgressBar.setMaximum(layer_count)
        self.totalProgressBar.setValue(current)
        self.statusLabel.setText(message)

    @pyqtSlot(int, int)
    def update_task(self, progress, max_progress):
        self.layerProgressBar.setMaximum(max_progress)
        self.layerProgressBar.setValue(progress)

    @pyqtSlot()
    def extent_changed(self):
        extent = self.iface.mapCanvas().extent()
        self.xMinLabel.setText(str(extent.xMinimum()))
        self.xMaxLabel.setText(str(extent.xMaximum()))
        self.yMinLabel.setText(str(extent.yMinimum()))
        self.yMaxLabel.setText(str(extent.yMaximum()))

    @pyqtSlot(str, str)
    def show_warning(self, _, message):
        # Most messages from the offline editing plugin are not important enough to show in the message bar.
        # In case we find important ones in the future, we need to filter them.
        QgsApplication.instance().messageLog().logMessage(message, 'QFieldSync')
