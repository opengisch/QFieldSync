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

class ProjectProperties(object):

    def __init__(self):
        raise RuntimeError('This object holds only project property static variables')

    BASE_MAP_TYPE = '/baseMapType'
    CREATE_BASE_MAP = '/createBaseMap'
    BASE_MAP_THEME = '/baseMapTheme'
    BASE_MAP_LAYER = '/baseMapLayer'
    BASE_MAP_TILE_SIZE = '/baseMapTileSize'
    BASE_MAP_MUPP = '/baseMapMupp'
    OFFLINE_COPY_ONLY_AOI = '/offlineCopyOnlyAoi'
    ORIGINAL_PROJECT_PATH = '/originalProjectPath'
    IMPORTED_FILES_CHECKSUMS = '/importedFilesChecksums'

    class BaseMapType(object):

        def __init__(self):
            raise RuntimeError('This object holds only project property static variables')

        SINGLE_LAYER = 'singleLayer'
        MAP_THEME = 'mapTheme'


class ProjectConfiguration(object):
    """
    Manages the QFieldSync specific configuration for a QGIS project.
    """

    def __init__(self, project):
        self.project = project

    @property
    def create_base_map(self):
        create_base_map, _ = self.project.readBoolEntry('qfieldsync', ProjectProperties.CREATE_BASE_MAP, False)
        return create_base_map

    @create_base_map.setter
    def create_base_map(self, value):
        self.project.writeEntry('qfieldsync', ProjectProperties.CREATE_BASE_MAP, value)

    @property
    def base_map_type(self):
        base_map_type, _ = self.project.readEntry('qfieldsync', ProjectProperties.BASE_MAP_TYPE,
                                                  ProjectProperties.BaseMapType.SINGLE_LAYER)
        if base_map_type != ProjectProperties.BaseMapType.SINGLE_LAYER:
            return ProjectProperties.BaseMapType.MAP_THEME
        else:
            return ProjectProperties.BaseMapType.SINGLE_LAYER

    @base_map_type.setter
    def base_map_type(self, value):
        if value != ProjectProperties.BaseMapType.SINGLE_LAYER and value != ProjectProperties.BaseMapType.MAP_THEME:
            raise ValueError('Only supported types can be set')

        self.project.writeEntry('qfieldsync', ProjectProperties.BASE_MAP_TYPE, value)

    @property
    def base_map_theme(self):
        base_map_theme, _ = self.project.readEntry('qfieldsync', ProjectProperties.BASE_MAP_THEME)
        return base_map_theme

    @base_map_theme.setter
    def base_map_theme(self, value):
        self.project.writeEntry('qfieldsync', ProjectProperties.BASE_MAP_THEME, value)

    @property
    def base_map_layer(self):
        base_map_layer, _ = self.project.readEntry('qfieldsync', ProjectProperties.BASE_MAP_LAYER)
        return base_map_layer

    @base_map_layer.setter
    def base_map_layer(self, value):
        self.project.writeEntry('qfieldsync', ProjectProperties.BASE_MAP_LAYER, value)

    @property
    def base_map_tile_size(self):
        base_map_tile_size, _ = self.project.readNumEntry('qfieldsync', ProjectProperties.BASE_MAP_TILE_SIZE, 1024)
        return base_map_tile_size

    @base_map_tile_size.setter
    def base_map_tile_size(self, value):
        self.project.writeEntry('qfieldsync', ProjectProperties.BASE_MAP_TILE_SIZE, value)

    @property
    def base_map_mupp(self):
        base_map_mupp, _ = self.project.readDoubleEntry('qfieldsync', ProjectProperties.BASE_MAP_MUPP, 10.0)
        return base_map_mupp

    @base_map_mupp.setter
    def base_map_mupp(self, value):
        self.project.writeEntryDouble('qfieldsync', ProjectProperties.BASE_MAP_MUPP, value)

    @property
    def offline_copy_only_aoi(self):
        offline_copy_only_aoi, _ = self.project.readBoolEntry('qfieldsync', ProjectProperties.OFFLINE_COPY_ONLY_AOI)
        return offline_copy_only_aoi

    @offline_copy_only_aoi.setter
    def offline_copy_only_aoi(self, value):
        self.project.writeEntry('qfieldsync', ProjectProperties.OFFLINE_COPY_ONLY_AOI, value)

    @property
    def original_project_path(self):
        original_project_path, _ = self.project.readEntry('qfieldsync', ProjectProperties.ORIGINAL_PROJECT_PATH)
        return original_project_path

    @original_project_path.setter
    def original_project_path(self, value):
        self.project.writeEntry('qfieldsync', ProjectProperties.ORIGINAL_PROJECT_PATH, value)

    @property
    def imported_files_checksums(self):
        imported_files_checksums, _ = self.project.readListEntry('qfieldsync', ProjectProperties.IMPORTED_FILES_CHECKSUMS)
        return imported_files_checksums

    @imported_files_checksums.setter
    def imported_files_checksums(self, value):
        self.project.writeEntry('qfieldsync', ProjectProperties.IMPORTED_FILES_CHECKSUMS, value)
