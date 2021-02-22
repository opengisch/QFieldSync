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

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtGui import QIcon, QPixmap
from functools import partial


def selectFolder(line_edit_widget):
    line_edit_widget.setText(QtWidgets.QFileDialog.getExistingDirectory(directory=line_edit_widget.text()))


def make_folder_selector(widget):
    return partial(selectFolder, line_edit_widget=widget)


def make_icon(icon_name):
    return QIcon(os.path.join(os.path.dirname(__file__), '..', 'resources', icon_name))


def make_pixmap(icon_name):
    return QPixmap(os.path.join(os.path.dirname(__file__), '..', 'resources', icon_name))
