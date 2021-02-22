# -*- coding: utf-8 -*-

"""
/***************************************************************************
 QFieldSync
                              -------------------
        begin                : 2016
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
import shutil
import tempfile

from qfieldsync.libqfieldsync import OfflineConverter
from qfieldsync.tests.utilities import test_data_folder
from qgis.core import Qgis, QgsProject, QgsRectangle, QgsOfflineEditing
from qgis.testing import start_app, unittest
from qgis.testing.mocked import get_iface

start_app()


class OfflineConverterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.iface = get_iface()

    def setUp(self):
        QgsProject.instance().clear()

    def test_copy(self):
        source_folder = tempfile.mkdtemp()
        export_folder = tempfile.mkdtemp()
        shutil.copytree(os.path.join(test_data_folder(), 'simple_project'), os.path.join(source_folder,
                                                                                         'simple_project'))

        project = self.load_project(os.path.join(source_folder, 'simple_project', 'project.qgs'))
        extent = QgsRectangle()
        offline_editing = QgsOfflineEditing()
        offline_converter = OfflineConverter(project, export_folder, extent, offline_editing)
        offline_converter.convert()

        files = os.listdir(export_folder)

        self.assertIn('project_qfield.qgs', files)
        self.assertIn('france_parts_shape.shp', files)
        self.assertIn('france_parts_shape.dbf', files)
        self.assertIn('curved_polys.gpkg', files)
        self.assertIn('spatialite.db', files)

        dcim_folder = os.path.join(export_folder, "DCIM")
        dcim_files = os.listdir(dcim_folder)
        self.assertIn('qfield-photo_1.jpg', dcim_files)
        self.assertIn('qfield-photo_2.jpg', dcim_files)
        self.assertIn('qfield-photo_3.jpg', dcim_files)
        dcim_subfolder = os.path.join(dcim_folder, "subfolder")
        dcim_subfiles = os.listdir(dcim_subfolder)
        self.assertIn('qfield-photo_sub_1.jpg', dcim_subfiles)
        self.assertIn('qfield-photo_sub_2.jpg', dcim_subfiles)
        self.assertIn('qfield-photo_sub_3.jpg', dcim_subfiles)

        shutil.rmtree(export_folder)
        shutil.rmtree(source_folder)

    def load_project(self, path):
        project = QgsProject.instance()
        self.assertTrue(project.read(path))
        return project

    def test_primary_keys_custom_property(self):
        source_folder = tempfile.mkdtemp()
        export_folder = tempfile.mkdtemp()
        shutil.copytree(
            os.path.join(test_data_folder(), 'pk_project'),
            os.path.join(source_folder,'pk_project'))

        project = self.load_project(os.path.join(source_folder, 'pk_project', 'project.qgs'))
        extent = QgsRectangle()
        offline_editing = QgsOfflineEditing()
        offline_converter = OfflineConverter(project, export_folder, extent, offline_editing)
        offline_converter.convert()

        exported_project = self.load_project(os.path.join(export_folder, 'project_qfield.qgs'))
        if Qgis.QGIS_VERSION_INT < 31601:
            layer = exported_project.mapLayersByName('somedata (offline)')[0]
        else:
            layer = exported_project.mapLayersByName('somedata')[0]
        self.assertEqual(layer.customProperty('QFieldSync/sourceDataPrimaryKeys'), 'pk')

        shutil.rmtree(export_folder)
        shutil.rmtree(source_folder)
