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

import os
import shutil
import json

from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsDataSourceUri,
    QgsMapLayer,
    QgsReadWriteContext
)

from qfieldsync.utils.file_utils import slugify


# When copying files, if any of the extension in any of the groups is found,
# other files with the same extension in the same folder will be copied as well.
file_extension_groups = [
    ['.shp', '.shx', '.dbf', '.sbx', '.sbn', '.shp.xml', '.prj','.cpg','.qpj','.qix'],
    ['.tab','.dat','.map','.xls','.xlsx','.id','.ind','.wks','.dbf'],
    ['.png','.pgw'],
    ['.jpg','.jgw'],
    ['.tif','.tfw','.wld']
]


def get_file_extension_group(filename):
    """
    Return the basename and an extension group (if applicable)

    Examples:
         airports.shp -> 'airport', ['.shp', '.shx', '.dbf', '.sbx', '.sbn', '.shp.xml']
         forests.gpkg -> 'forests', ['.gpkg']
    """
    for group in file_extension_groups:
        for extension in group:
            if filename.endswith(extension):
                return filename[:-len(extension)], group
    basename, ext = os.path.splitext(filename)
    return basename, [ext]


class SyncAction(object):
    """
    Enumeration of sync actions
    """

    # Make an offline editing copy
    def __init__(self):
        raise RuntimeError('Should only be used as enumeration')

    # Take an offline editing copy of this layer
    OFFLINE = "offline"

    # No action will in general leave the source untouched.
    # For file based layers, the source
    # - will be made relative
    # - the file(s) will be copied
    NO_ACTION = "no_action"

    # Keep already copied data or files if existent
    KEEP_EXISTENT = 'keep_existent'

    # remove from the project
    REMOVE = "remove"


class LayerSource(object):

    def __init__(self, layer: QgsMapLayer):
        self.layer = layer
        self._action = None
        self._photo_naming = {}
        self.read_layer()

    def read_layer(self):
        self._action = self.layer.customProperty('QFieldSync/action')
        self._photo_naming = json.loads(self.layer.customProperty('QFieldSync/photo_naming') or '{}')

    def apply(self):
        self.layer.setCustomProperty('QFieldSync/action', self.action)
        self.layer.setCustomProperty('QFieldSync/photo_naming', json.dumps(self._photo_naming))

    @property
    def action(self):
        if self._action is None:
            return self.default_action
        else:
            return self._action

    @action.setter
    def action(self, action):
        self._action = action

    def photo_naming(self, field_name: str) -> str:
        return self._photo_naming.get(field_name, "'DCIM/{}_'||now()||'.jpg'".format(slugify(self.layer.name())))

    def set_photo_naming(self, field_name: str, expression: str):
        self._photo_naming[field_name] = expression

    @property
    def default_action(self):
        if self.is_file:
            return SyncAction.NO_ACTION
        elif not self.is_supported:
            return SyncAction.REMOVE
        elif self.layer.providerType() == 'postgres':
            return SyncAction.OFFLINE
        else:
            return SyncAction.NO_ACTION

    @property
    def is_configured(self):
        return self._action is not None

    @property
    def is_file(self):
        # reading the part before | so it's valid when gpkg
        if os.path.isfile(self.layer.source().split('|')[0]):
            return True
        elif os.path.isfile(QgsDataSourceUri(self.layer.dataProvider().dataSourceUri()).database()):
            return True
        else:
            return False

    @property
    def available_actions(self):
        actions = list()

        if self.is_file:
            actions.append((SyncAction.NO_ACTION, QCoreApplication.translate('LayerAction', 'copy')))
            actions.append((SyncAction.KEEP_EXISTENT, QCoreApplication.translate('LayerAction', 'keep existent (copy if missing)')))
        else:
            actions.append((SyncAction.NO_ACTION, QCoreApplication.translate('LayerAction', 'no action')))

        if self.layer.type() == QgsMapLayer.VectorLayer:
            actions.append((SyncAction.OFFLINE, QCoreApplication.translate('LayerAction', 'offline editing')))

        actions.append((SyncAction.REMOVE, QCoreApplication.translate('LayerAction', 'remove')))

        return actions

    @property
    def is_supported(self):
        # jpeg 2000
        if self.layer.source().endswith(('jp2', 'jpx')):
            return False
        # ecw raster
        elif self.layer.source().endswith('ecw'):
            return False
        else:
            return True

    @property
    def warning(self):
        if self.layer.source().endswith(('jp2', 'jpx')):
            return QCoreApplication.translate('DataSourceWarning',
                                              'JPEG2000 layers are not supported by QField.<br>You can rasterize '
                                              'them as basemap.'
                                              )
        if self.layer.source().endswith('ecw'):
            return QCoreApplication.translate('DataSourceWarning',
                                              'ECW layers are not supported by QField.<br>You can rasterize them '
                                              'as basemap.')
        return None

    @property
    def name(self):
        return self.layer.name()

    @property
    def dependent_layers(self) -> [str]:
        """
        Returns a list of layer IDs of the layers required by the current layer
        :return:
        """
        layers = []
        # fields
        if self.layer.type() == QgsMapLayer.VectorLayer:
            for field in self.layer.fields():
                ews = field.editorWidgetSetup()
                if ews.type() == 'ValueRelation':
                    layers.append(ews.config()['Layer'])
        return layers

    def copy(self, target_path, copied_files, keep_existent=False):
        """
        Copy a layer to a new path and adjust its datasource.

        :param layer: The layer to copy
        :param target_path: A path to a folder into which the data will be copied
        :param keep_existent: if True and target file already exists, keep it as it is
        """
        if not self.is_file:
            # Copy will also be called on non-file layers like WMS. In this case, just do nothing.
            return

        layer_name_suffix = ''
        # Shapefiles and GeoPackages have the path in the source
        uri_parts = self.layer.source().split('|', 1)
        file_path = uri_parts[0]
        if len(uri_parts) > 1:
            layer_name_suffix = uri_parts[1]
        # Spatialite have the path in the table part of the uri
        uri = QgsDataSourceUri(self.layer.dataProvider().dataSourceUri())

        if os.path.isfile(file_path):
            source_path, file_name = os.path.split(file_path)
            basename, extensions = get_file_extension_group(file_name)
            for ext in extensions:
                dest_file = os.path.join(target_path, basename + ext)
                if os.path.exists(os.path.join(source_path, basename + ext)) and \
                        (keep_existent is False or not os.path.isfile(dest_file)):
                    shutil.copy(os.path.join(source_path, basename + ext), dest_file)

            new_source = os.path.join(target_path, file_name)
            if layer_name_suffix:
                new_source = new_source + '|' + layer_name_suffix
            self._change_data_source(new_source)
        # Spatialite files have a uri
        else:
            file_path = uri.database()
            if os.path.isfile(file_path):
                source_path, file_name = os.path.split(file_path)
                basename, extensions = get_file_extension_group(file_name)
                for ext in extensions:
                    dest_file = os.path.join(target_path, basename + ext)
                    if os.path.exists(os.path.join(source_path, basename + ext)) and \
                            (keep_existent is False or not os.path.isfile(dest_file)):
                        shutil.copy(os.path.join(source_path, basename + ext),
                                    dest_file)
                uri.setDatabase(os.path.join(target_path, file_name))
                self._change_data_source(uri.uri())
        return copied_files

    def _change_data_source(self, new_data_source):
        """
        Changes the datasource string of the layer
        """
        context = QgsReadWriteContext()
        document = QDomDocument("style")
        map_layers_element = document.createElement("maplayers")
        map_layer_element = document.createElement("maplayer")
        self.layer.writeLayerXml(map_layer_element, document, context)

        # modify DOM element with new layer reference
        map_layer_element.firstChildElement("datasource").firstChild().setNodeValue(new_data_source)
        map_layers_element.appendChild(map_layer_element)
        document.appendChild(map_layers_element)

        # reload layer definition
        self.layer.readLayerXml(map_layer_element, context)
        self.layer.reload()
