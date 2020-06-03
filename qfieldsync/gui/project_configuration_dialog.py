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

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QDialog, QTableWidgetItem, QToolButton, QComboBox, QMenu, QAction
from qgis.PyQt.uic import loadUiType

from qgis.core import QgsProject, QgsMapLayerProxyModel, QgsMapLayer, Qgis
from qgis.gui import QgsFieldExpressionWidget

from qfieldsync.core import ProjectConfiguration
from qfieldsync.core.layer import LayerSource, SyncAction
from qfieldsync.core.project import ProjectProperties


DialogUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), '../ui/project_configuration_dialog.ui'),
    import_from='..'
)


class ProjectConfigurationDialog(QDialog, DialogUi):
    """
    Configuration dialog for QFieldSync on a particular project.
    """

    def __init__(self, iface, parent=None):
        """Constructor."""
        super(ProjectConfigurationDialog, self).__init__(parent=parent)
        self.iface = iface

        self.accepted.connect(self.onAccepted)
        self.project = QgsProject.instance()
        self.__project_configuration = ProjectConfiguration(self.project)

        self.setupUi(self)
        self.multipleToggleButton.setIcon(QIcon(os.path.join(os.path.dirname(__file__), '../resources/visibility.svg')))

        self.toggle_menu = QMenu(self)
        self.remove_all_action = QAction(self.tr("remove all layers"), self.toggle_menu)
        self.toggle_menu.addAction(self.remove_all_action)
        self.remove_hidden_action = QAction(self.tr("remove hidden layers"), self.toggle_menu)
        self.toggle_menu.addAction(self.remove_hidden_action)
        self.add_all_copy_action = QAction(self.tr("add all layers"), self.toggle_menu)
        self.toggle_menu.addAction(self.add_all_copy_action)
        self.add_visible_copy_action = QAction(self.tr("add visible layers"), self.toggle_menu)
        self.toggle_menu.addAction(self.add_visible_copy_action)
        self.add_all_offline_action = QAction(self.tr("add all vector layers as offline"), self.toggle_menu)
        self.toggle_menu.addAction(self.add_all_offline_action)
        self.add_visible_offline_action = QAction(self.tr("add visible vector layers as offline"), self.toggle_menu)
        self.toggle_menu.addAction(self.add_visible_offline_action)
        self.multipleToggleButton.setMenu(self.toggle_menu)
        self.multipleToggleButton.setAutoRaise(True)
        self.multipleToggleButton.setPopupMode(QToolButton.InstantPopup)
        self.toggle_menu.triggered.connect(self.toggle_menu_triggered)

        self.singleLayerRadioButton.toggled.connect(self.baseMapTypeChanged)
        self.unsupportedLayersList = list()

        self.reloadProject()

    def reloadProject(self):
        """
        Load all layers from the map layer registry into the table.
        """
        self.unsupportedLayersList = list()
        self.layersTable.setRowCount(0)
        self.layersTable.setSortingEnabled(False)

        cbxs = []
        for layer in self.project.mapLayers().values():
            layer_source = LayerSource(layer)
            if not layer_source.is_supported:
                self.unsupportedLayersList.append(layer_source)
            count = self.layersTable.rowCount()
            self.layersTable.insertRow(count)
            item = QTableWidgetItem(layer.name())
            item.setData(Qt.UserRole, layer_source)
            item.setData(Qt.EditRole, layer.name())
            self.layersTable.setItem(count, 0, item)

            cbx = QComboBox()
            for action, description in layer_source.available_actions:
                cbx.addItem(description)
                cbx.setItemData(cbx.count() - 1, action, Qt.UserRole)
                if layer_source.action == action:
                    cbx.setCurrentIndex(cbx.count() - 1)
            cbx.currentIndexChanged.connect(lambda index, layer_source=layer_source: self.layer_action_changed(
                layer_source, cbx.itemData(index)))

            self.layersTable.setCellWidget(count, 1, cbx)

        self.layersTable.resizeColumnsToContents()
        self.layersTable.sortByColumn(0, Qt.AscendingOrder)
        self.layersTable.setSortingEnabled(True)

        self.photoResourceTable.setColumnCount(3)
        self.photoResourceTable.setHorizontalHeaderLabels([self.tr('Layer'), self.tr('Field'), self.tr('Naming Expression')])
        self.photoResourceTable.horizontalHeaderItem(2).setToolTip(self.tr('Enter expression for a file path with the extension .jpg'))
        self.photoResourceTable.horizontalHeader().setStretchLastSection(True)
        self.photoResourceTable.setRowCount(0)
        row = 0
        for layer in self.project.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.VectorLayer:
                layer_source = LayerSource(layer)
                i = 0
                for field in layer.fields():
                    ews = layer.editorWidgetSetup(i)
                    i += 1
                    if ews.type() == 'ExternalResource':
                        # for later: if ews.config().get('DocumentViewer', QgsExternalResourceWidget.NoContent) == QgsExternalResourceWidget.Image:
                        self.photoResourceTable.insertRow(row)
                        item = QTableWidgetItem(layer.name())
                        item.setData(Qt.UserRole, layer_source)
                        self.photoResourceTable.setItem(row, 0, item)
                        item = QTableWidgetItem(field.name())
                        self.photoResourceTable.setItem(row, 1, item)
                        ew = QgsFieldExpressionWidget()
                        ew.setLayer(layer)
                        expression = layer_source.photo_naming(field.name())
                        ew.setExpression(expression)
                        self.photoResourceTable.setCellWidget(row, 2, ew)
                        row += 1
        self.photoResourceTable.resizeColumnsToContents()

        # Remove the tab when not yet suported in QGIS
        if Qgis.QGIS_VERSION_INT < 31300:
            self.tabWidget.removeTab(self.tabWidget.count() - 1)

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

        if self.unsupportedLayersList:
            self.unsupportedLayers.setVisible(True)

            unsupported_layers_text = '<b>{}</b><br>'.format(self.tr('Warning'))
            unsupported_layers_text += self.tr("There are unsupported layers in your project. They will not be available on QField.")

            unsupported_layers_text += '<ul>'
            for layer in self.unsupportedLayersList:
                unsupported_layers_text += '<li>' + '<b>' + layer.name + ':</b> ' + layer.warning
            unsupported_layers_text += '<ul>'

            self.unsupportedLayers.setText(unsupported_layers_text)

    def layer_action_changed(self, layer_source: LayerSource, action: str):
        layer_source.action = action
        layer_source.apply()
        self.project.setDirty(True)

        reload = False
        for layer_id in layer_source.dependent_layers:
            for i in range(self.layersTable.rowCount()):
                item = self.layersTable.item(i, 0)
                layer_source = item.data(Qt.UserRole)
                if layer_source.layer.id() == layer_id:
                    if layer_source.action == SyncAction.REMOVE:
                        if layer_source.is_file:
                            layer_source.action = SyncAction.NO_ACTION
                        else:
                            layer_source.action = SyncAction.OFFLINE
                        layer_source.apply()
                        reload = True
                    break

        if reload:
            self.reloadProject()

    def onAccepted(self):
        """
        Update layer configuration in project
        """
        for i in range(self.layersTable.rowCount()):
            item = self.layersTable.item(i, 0)
            layer_source = item.data(Qt.UserRole)
            cbx = self.layersTable.cellWidget(i, 1)

            old_action = layer_source.action
            layer_source.action = cbx.itemData(cbx.currentIndex())
            if layer_source.action != old_action:
                self.project.setDirty(True)
                layer_source.apply()

        for i in range(self.photoResourceTable.rowCount()):
            layer_source: LayerSource = self.photoResourceTable.item(i, 0).data(Qt.UserRole)
            field_name = self.photoResourceTable.item(i, 1).text()
            old_expression = layer_source.photo_naming(field_name)
            new_expression = self.photoResourceTable.cellWidget(i, 2).currentText()
            layer_source.set_photo_naming(field_name, new_expression)
            self.project.setDirty(True)
            layer_source.apply()

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

    def baseMapTypeChanged(self):
        if self.singleLayerRadioButton.isChecked():
            self.baseMapTypeStack.setCurrentWidget(self.singleLayerPage)
        else:
            self.baseMapTypeStack.setCurrentWidget(self.mapThemePage)

    def toggle_menu_triggered(self, action):
        """
        Toggles usae of layers
        :param action: the menu action that triggered this
        """
        sync_action = SyncAction.NO_ACTION
        if action in (self.remove_hidden_action, self.remove_all_action):
            sync_action = SyncAction.REMOVE
        elif action in (self.add_all_offline_action, self.add_visible_offline_action):
            sync_action = SyncAction.OFFLINE

        # all layers
        if action in (self.remove_all_action, self.add_all_copy_action, self.add_all_offline_action):
            for i in range(self.layersTable.rowCount()):
                item = self.layersTable.item(i, 0)
                layer_source = item.data(Qt.UserRole)
                old_action = layer_source.action
                available_actions, _ = zip(*layer_source.available_actions)
                if sync_action in available_actions:
                    layer_source.action = sync_action
                    if layer_source.action != old_action:
                        self.project.setDirty(True)
                    layer_source.apply()
        # based on visibility
        elif action in (self.remove_hidden_action, self.add_visible_copy_action, self.add_visible_offline_action):
            visible = Qt.Unchecked if action == self.remove_hidden_action else Qt.Checked
            root = QgsProject.instance().layerTreeRoot()
            for layer in QgsProject.instance().mapLayers().values():
                node = root.findLayer(layer.id())
                if node and node.isVisible() == visible:
                    layer_source = LayerSource(layer)
                    old_action = layer_source.action
                    available_actions, _ = zip(*layer_source.available_actions)
                    if sync_action in available_actions:
                        layer_source.action = sync_action
                        if layer_source.action != old_action:
                            self.project.setDirty(True)
                        layer_source.apply()

        self.reloadProject()
