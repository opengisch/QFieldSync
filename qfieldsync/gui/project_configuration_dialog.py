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

from qgis.gui import QgsGui

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox

from qfieldsync.gui.project_configuration_widget import ProjectConfigurationWidget


class ProjectConfigurationDialog(QDialog):
    """
    Configuration dialog for QFieldSync on a particular project.
    """

    def __init__(self, parent=None):
        """Constructor."""
        super(ProjectConfigurationDialog, self).__init__(parent=parent)

        self.setMinimumWidth(500)
        QgsGui.instance().enableAutoGeometryRestore(self)

        self.setWindowTitle("QFieldSync Project Properties")
        
        self.projectConfigurationWidget = ProjectConfigurationWidget(self)
        
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(lambda: self.onAccepted())
        self.buttonBox.rejected.connect(self.reject)
        
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.projectConfigurationWidget)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def onAccepted(self):
        self.projectConfigurationWidget.apply()
        self.close()
