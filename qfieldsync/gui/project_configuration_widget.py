# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              -------------------
        begin                : 21.11.2016
        git sha              : :%H$
        copyright            : (C) 2016 by OPENGIS.ch
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
from requests import HTTPError

from qgis.PyQt.QtCore import Qt, QTemporaryDir
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QLabel
from qgis.PyQt.uic import loadUiType

from qgis.core import QgsProject, QgsMapLayerProxyModel, Qgis, QgsOfflineEditing
from qgis.gui import (
    QgsOptionsWidgetFactory,
    QgsOptionsPageWidget,
)

from qfieldsync.gui.layers_config_widget import LayersConfigWidget
from qfieldsync.utils.cloud_utils import to_cloud_title

from qfieldsync.libqfieldsync import (LayerSource, ProjectConfiguration, ProjectProperties, OfflineConverter, SyncAction)


WidgetUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), '../ui/project_configuration_widget.ui'),
    import_from='..'
)


class ProjectConfigurationWidget(WidgetUi, QgsOptionsPageWidget):
    """
    Configuration widget for QFieldSync on a particular project.
    """

    def __init__(self, parent=None):
        """Constructor."""
        super().__init__(parent)
        self.setupUi(self)

        self.project = QgsProject.instance()
        self.__project_configuration = ProjectConfiguration(self.project)

        self.preferOnlineLayersRadioButton.toggled.connect(self.onLayerActionPreferenceChanged)
        self.singleLayerRadioButton.toggled.connect(self.baseMapTypeChanged)

        self.reloadProject()

    def reloadProject(self):
        """
        Load all layers from the map layer registry into the table.
        """
        self.unsupportedLayersList = list()

        infoLabel = QLabel()
        infoLabel.setPixmap(QIcon.fromTheme('info').pixmap(16, 16))
        infoLabel.setToolTip(self.tr('To improve the overall user experience with QFieldCloud, it is recommended that all vector layers use UUID as primary key.'))

        layer_sources = [LayerSource(l) for l in QgsProject.instance().mapLayers().values()]
        self.cloudLayersConfigWidget = LayersConfigWidget(self.project, True, layer_sources)
        self.cableLayersConfigWidget = LayersConfigWidget(self.project, False, layer_sources)
        self.cloudAdvancedSettings.layout().addWidget(self.cloudLayersConfigWidget)
        self.cloudExportTab.layout().addWidget(infoLabel, 0, 2)
        self.cableExportTab.layout().addWidget(self.cableLayersConfigWidget)

        # Load Map Themes
        for theme in self.project.mapThemeCollection().mapThemes():
            self.mapThemeComboBox.addItem(theme)

        self.layerComboBox.setFilters(QgsMapLayerProxyModel.RasterLayer)

        self.__project_configuration = ProjectConfiguration(self.project)
        self.createBaseMapGroupBox.setChecked(self.__project_configuration.create_base_map)

        if self.__project_configuration.base_map_type == ProjectProperties.BaseMapType.SINGLE_LAYER:
            self.singleLayerRadioButton.setChecked(True)
        else:
            self.mapThemeRadioButton.setChecked(True)

        self.mapThemeComboBox.setCurrentIndex(
            self.mapThemeComboBox.findText(self.__project_configuration.base_map_theme))
        layer = QgsProject.instance().mapLayer(self.__project_configuration.base_map_layer)
        self.layerComboBox.setLayer(layer)
        self.mapUnitsPerPixel.setText(str(self.__project_configuration.base_map_mupp))
        self.tileSize.setText(str(self.__project_configuration.base_map_tile_size))
        self.onlyOfflineCopyFeaturesInAoi.setChecked(self.__project_configuration.offline_copy_only_aoi)
        self.preferOnlineLayersRadioButton.setChecked(self.__project_configuration.layer_action_preference == 'online')
        self.preferOfflineLayersRadioButton.setChecked(self.__project_configuration.layer_action_preference == 'offline')

        if self.unsupportedLayersList:
            self.unsupportedLayersLabel.setVisible(True)

            unsupported_layers_text = '<b>{}: </b>'.format(self.tr('Warning'))
            unsupported_layers_text += self.tr("There are unsupported layers in your project which will not be available in QField.")
            unsupported_layers_text += self.tr(" If needed, you can create a Base Map to include those layers in your packaged project.")
            self.unsupportedLayersLabel.setText(unsupported_layers_text)


    def apply(self):
        """
        Update layer configuration in project
        """
        self.cloudLayersConfigWidget.apply()
        self.cableLayersConfigWidget.apply()

        self.__project_configuration.create_base_map = self.createBaseMapGroupBox.isChecked()
        self.__project_configuration.base_map_theme = self.mapThemeComboBox.currentText()
        try:
            self.__project_configuration.base_map_layer = self.layerComboBox.currentLayer().id()
        except AttributeError:
            pass
        if self.singleLayerRadioButton.isChecked():
            self.__project_configuration.base_map_type = ProjectProperties.BaseMapType.SINGLE_LAYER
        else:
            self.__project_configuration.base_map_type = ProjectProperties.BaseMapType.MAP_THEME

        self.__project_configuration.base_map_mupp = float(self.mapUnitsPerPixel.text())
        self.__project_configuration.base_map_tile_size = int(self.tileSize.text())

        self.__project_configuration.offline_copy_only_aoi = self.onlyOfflineCopyFeaturesInAoi.isChecked()
        self.__project_configuration.layer_action_preference = 'online' if self.preferOnlineLayersRadioButton.isChecked() else 'offline'


    def onLayerActionPreferenceChanged(self):
        '''Triggered when prefer online or offline radio buttons have been changed'''
        prefer_online = self.preferOnlineLayersRadioButton.isChecked()

        for i in range(self.cloudLayersConfigWidget.layersTable.rowCount()):
            item = self.cloudLayersConfigWidget.layersTable.item(i, 0)
            layer_source = item.data(Qt.UserRole)
            cmb = self.cloudLayersConfigWidget.layersTable.cellWidget(i, 2)

            # it would be annoying to change the action on removed layers
            if cmb.itemData(cmb.currentIndex()) == SyncAction.REMOVE:
                continue

            idx, _cloud_action = layer_source.prefered_cloud_action(prefer_online)
            cmb.setCurrentIndex(idx)
            layer_source.cloud_action = cmb.itemData(cmb.currentIndex())

    def baseMapTypeChanged(self):
        if self.singleLayerRadioButton.isChecked():
            self.baseMapTypeStack.setCurrentWidget(self.singleLayerPage)
        else:
            self.baseMapTypeStack.setCurrentWidget(self.mapThemePage)

