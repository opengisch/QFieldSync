# -*- coding: utf-8 -*-

"""
/***************************************************************************
 QFieldSync
                              -------------------
        begin                : 2020
        copyright            : (C) 2020 by OPENGIS.ch
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

from qgis.PyQt.QtCore import QObject
from qgis.core import QgsProject, Qgis
from .layer import LayerSource, SyncAction


class QfieldSyncError(object):
    def __init__(self, layer, error_level, error_message):
        self.layer = layer
        self.error_level = error_level
        self.error_message = error_message


class ConfigurationCheckup(QObject):
    def __init__(self, project: QgsProject):
        """
        Returns a list of errors in the project configuration
        """
        super(ConfigurationCheckup, self).__init__(parent=None)
        self._errors = []
        for layer in list(project.mapLayers().values()):
            layer_source = LayerSource(layer)
            if not layer_source.is_configured:
                self._errors.append(QfieldSyncError(layer, Qgis.Warning, self.tr('Layer is not configured.')))

            if layer_source.action != SyncAction.REMOVE:
                for layer_id in layer_source.dependent_layers:
                    dependent_layer = project.mapLayer(layer_id)
                    dependent_layer_source = LayerSource(dependent_layer)
                    if dependent_layer_source.action == SyncAction.REMOVE:
                        self._errors.append(QfieldSyncError(
                            layer,
                            Qgis.Critical,
                            self.tr('Layer "{}" depends on "{}" which is removed from packaged project.'
                                    .format(layer.name(), dependent_layer.name()))
                        ))

    def errors(self) -> [QfieldSyncError]:
        return self._errors
