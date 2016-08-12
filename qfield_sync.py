# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QFieldSync
                                 A QGIS plugin
 Sync your projects to QField on android
                              -------------------
        begin                : 2015-05-20
        git sha              : $Format:%H$
        copyright            : (C) 2015 by OPENGIS.ch
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
from __future__ import absolute_import

try:
    from builtins import object
except:
    pass

import os.path
from PyQt4.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QSettings
from PyQt4.QtGui import QAction, QIcon
# Initialize Qt resources from file resources.py
from . import resources_rc
from . import config
from .push_dialog import PushDialog
from .settings_dialog import SettingsDialog

try:
    from .utils.utils import warn_project_is_dirty
except:
    warn_project_is_dirty = lambda: True


class QFieldSync(object):
    """QGIS Plugin Implementation."""
    QFIELD_SCOPE = "QFieldSync"

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'QFieldSync_{}.qm'.format(locale))
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&QFieldSync')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'QFieldSync')
        self.toolbar.setObjectName(u'QFieldSync')

        # initialize settings
        self.export_folder = QSettings().value(config.EXPORT_DIRECTORY_SETTING, os.path.expanduser("~"))
        self.import_folder = QSettings().value(config.IMPORT_DIRECTORY_SETTING, os.path.expanduser("~"))
        self.update_qgis_settings()

    def update_qgis_settings(self):
        s = QSettings()
        s.setValue(config.EXPORT_DIRECTORY_SETTING, self.export_folder)
        s.setValue(config.IMPORT_DIRECTORY_SETTING, self.import_folder)
        s.sync()

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('QFieldSync', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        refresh_icon_path = ':/plugins/QFieldSync/refresh.png'
        self.add_action(
            None,
            text=self.tr(u'Settings'),
            callback=self.show_settings,
            parent=self.iface.mainWindow())
        self.add_action(
            refresh_icon_path,
            text=self.tr(u'Sync to QField'),
            callback=self.push_project,
            parent=self.iface.mainWindow())

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&QFieldSync'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    def show_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec_()

    def get_settings(self):
        return {"import_folder": self.import_folder, "export_folder": self.export_folder}

    def get_export_folder(self):
        return self.get_settings()["export_folder"]

    def get_import_folder(self):
        return self.get_settings()["import_folder"]

    def update_settings(self, import_folder, export_folder):
        self.import_folder = import_folder
        self.export_folder = export_folder
        self.update_qgis_settings()


    def push_project(self):
        """Run method that performs all the real work"""
        if warn_project_is_dirty():
            # show the dialog
            dlg = PushDialog(self.iface, self)
            # Run the dialog event loop
            dlg.exec_()
