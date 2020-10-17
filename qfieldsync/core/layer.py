import os
import shutil
import json

from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsDataSourceUri,
    QgsMapLayer,
    QgsReadWriteContext,
    QgsProject,
    QgsProviderRegistry,
    QgsProviderMetadata,
    Qgis
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

    # No action for online DB layers
    # - will in general leave the source untouched
    NO_ACTION = "no_action"

    # Copy action for file based layers
    # - will be made relative
    # - the file(s) will be copied
    COPY = 'copy'

    # Keep already copied data or files if existent
    KEEP_EXISTENT = 'keep_existent'

    # remove from the project
    REMOVE = "remove"


class LayerSource(object):

    def __init__(self, layer):
        self.layer = layer
        self._action = None
        self._photo_naming = {}
        self._is_geometry_locked = None
        self.read_layer()

        self.storedInlocalizedDataPath = False
        if self.layer.dataProvider() is not None:
            pathResolver = QgsProject.instance().pathResolver()
            metadata = QgsProviderRegistry.instance().providerMetadata(self.layer.dataProvider().name())
            if metadata is not None:
                decoded = metadata.decodeUri(self.layer.source())
                if "path" in decoded:
                    path = pathResolver.writePath(decoded["path"])
                    if path.startswith("localized:"):
                        self.storedInlocalizedDataPath = True

    def read_layer(self):
        self._action = self.layer.customProperty('QFieldSync/action')
        self._photo_naming = json.loads(self.layer.customProperty('QFieldSync/photo_naming') or '{}')
        self._is_geometry_locked = self.layer.customProperty('QFieldSync/is_geometry_locked', False)

    def apply(self):
        self.layer.setCustomProperty('QFieldSync/action', self.action)
        self.layer.setCustomProperty('QFieldSync/photo_naming', json.dumps(self._photo_naming))

        # custom properties does not store the data type, so it is safer to remove boolean custom properties, rather than setting them to the string 'false' (which is boolean `True`)
        if self.is_geometry_locked:
            self.layer.setCustomProperty('QFieldSync/is_geometry_locked', True)
        else:
            self.layer.removeCustomProperty('QFieldSync/is_geometry_locked')

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
        return self._photo_naming.get(field_name, "'DCIM/{layername}_' || format_date(now(),'yyyyMMddhhmmsszzz') || '.jpg'".format(layername=slugify(self.layer.name())))

    def set_photo_naming(self, field_name: str, expression: str):
        self._photo_naming[field_name] = expression

    @property
    def default_action(self):
        if self.is_file:
            return SyncAction.COPY
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
        if self.layer.dataProvider() is not None:
            metadata = QgsProviderRegistry.instance().providerMetadata(self.layer.dataProvider().name())
            if metadata is not None:
                decoded = metadata.decodeUri(self.layer.source())
                if "path" in decoded:
                    if os.path.isfile(decoded["path"]):
                        return True
        return False

    @property
    def available_actions(self):
        actions = list()

        if self.is_file and not self.storedInlocalizedDataPath:
            actions.append((SyncAction.COPY, QCoreApplication.translate('LayerAction', 'Copy')))
            actions.append((SyncAction.KEEP_EXISTENT, QCoreApplication.translate('LayerAction', 'Keep Existent (Copy If Missing)')))
        else:
            actions.append((SyncAction.NO_ACTION, QCoreApplication.translate('LayerAction', 'No Action')))

        if self.layer.type() == QgsMapLayer.VectorLayer:
            actions.append((SyncAction.OFFLINE, QCoreApplication.translate('LayerAction', 'Offline Editing')))

        actions.append((SyncAction.REMOVE, QCoreApplication.translate('LayerAction', 'Remove')))

        return actions

    @property
    def is_supported(self):
        # ecw raster
        if self.layer.source().endswith('ecw'):
            return False
        else:
            return True

    @property
    def can_lock_geometry(self):
        return self.layer.type() == QgsMapLayer.VectorLayer

    @property
    def is_geometry_locked(self):
        return bool(self._is_geometry_locked)

    @is_geometry_locked.setter
    def is_geometry_locked(self, is_geometry_locked):
        self._is_geometry_locked = is_geometry_locked

    @property
    def warning(self):
        if self.layer.source().endswith('ecw'):
            return QCoreApplication.translate('DataSourceWarning',
                                              'ECW layers are not supported by QField.')
        return None

    @property
    def name(self):
        return self.layer.name()

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

        file_path = ''
        layer_name = ''
        subset = ''
        
        if self.layer.dataProvider() is not None:
            metadata = QgsProviderRegistry.instance().providerMetadata(self.layer.dataProvider().name())
            if metadata is not None:
                decoded = metadata.decodeUri(self.layer.source())
                if "path" in decoded:
                    file_path = decoded["path"]
                if "layerName" in decoded:
                    layer_name = decoded["layerName"]
                if "subset" in decoded:
                    subset = decoded["subset"]
        if file_path == '':
            file_path = self.layer.source()

        if os.path.isfile(file_path):
            source_path, file_name = os.path.split(file_path)
            basename, extensions = get_file_extension_group(file_name)
            for ext in extensions:
                dest_file = os.path.join(target_path, basename + ext)
                if os.path.exists(os.path.join(source_path, basename + ext)) and \
                        (keep_existent is False or not os.path.isfile(dest_file)):
                    shutil.copy(os.path.join(source_path, basename + ext), dest_file)

            new_source = ''
            if Qgis.QGIS_VERSION_INT >= 31200 and self.layer.dataProvider() is not None:
                metadata = QgsProviderRegistry.instance().providerMetadata(self.layer.dataProvider().name())
                if metadata is not None:
                    new_source = metadata.encodeUri({"path":os.path.join(target_path, file_name),"layerName":layer_name,"subset":subset})
            if new_source == '':
                if self.layer.dataProvider() and self.layer.dataProvider().name == "spatialite":
                    uri = QgsDataSourceUri()
                    uri.setDatabase(os.path.join(target_path, file_name))
                    uri.setTable(layer_name)
                    new_source = uri.uri()
                else:
                    new_source = os.path.join(target_path, file_name)
                    if layer_name != '':
                        new_source = "{}|{}".format(new_source, layer_name)

            self._change_data_source(new_source)
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
