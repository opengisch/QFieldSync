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

from pathlib import Path

from qgis.core import QgsProject

from qfieldsync.libqfieldsync.utils.file_utils import get_project_in_folder
from qfieldsync.libqfieldsync import ProjectConfiguration


def get_project_title(project: QgsProject) -> str:
    """ Gets project title, or if non available, the basename of the filename"""
    if project.title():
        return project.title()
    else:
        return Path(project.fileName()).stem


def open_project(filename: str) -> bool:
    project = QgsProject.instance()
    project.clear()
    project.setFileName(filename)
    return project.read()


def import_checksums_of_project(folder):
    project = QgsProject.instance()
    qgs_file = get_project_in_folder(folder)
    open_project(qgs_file)
    original_project_path = ProjectConfiguration(project).original_project_path
    open_project(original_project_path)
    return ProjectConfiguration(project).imported_files_checksums
