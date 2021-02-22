# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QFieldSync
                             -------------------
        begin                : 2020-07-13
        git sha              : $Format:%H$
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
from typing import List

from qgis.core import QgsDataProvider, QgsDataItemProvider, QgsDataItem, QgsDataCollectionItem, QgsErrorItem
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qfieldsync.gui.cloud_projects_dialog import CloudProjectsDialog
from qgis.utils import iface

from qfieldsync.gui.cloud_login_dialog import CloudLoginDialog
from qfieldsync.core.cloud_project import CloudProject
from qfieldsync.core.cloud_api import CloudNetworkAccessManager


class DataItemProvider(QgsDataItemProvider):

    def __init__(self, network_manager: CloudNetworkAccessManager):
        QgsDataItemProvider.__init__(self)
        self.network_manager = network_manager

    def name(self):
        return 'QFieldSyncProvider'

    def capabilities(self):
        return QgsDataProvider.Net

    def createDataItem(self, path, parentItem):
        if not parentItem:
            root_item = QFieldSyncRootItem(self.network_manager)
            return root_item
        else:
            return


class QFieldSyncRootItem(QgsDataCollectionItem):
    """ QFieldSync root """

    def __init__(self, network_manager: CloudNetworkAccessManager):
        QgsDataCollectionItem.__init__(self, None, 'QFieldSync', '/QFieldSync')
        self.setIcon(QIcon(os.path.join(os.path.dirname(__file__), '../resources/cloud_off.svg')))
        self.network_manager = network_manager
        self.error = None

        self.network_manager.login_success.connect(lambda: self.refresh_icon())
        self.network_manager.token_changed.connect(lambda: self.refresh_icon())
        self.network_manager.projects_cache.projects_updated.connect(lambda: self.refresh())

    def createChildren(self):
        items = []

        if not self.network_manager.has_token():
            return []

        if self.error:
            error_item = QgsErrorItem(self, self.error, '/QFieldSync/error')
            error_item.setIcon(QIcon(os.path.join(os.path.dirname(__file__), '../resources/cloud.svg')))
            return [error_item]

        my_projects = QFieldSyncGroupItem(self, 'My projects', 'private', '../resources/cloud.svg', 1)
        my_projects.setState(QgsDataItem.Populated)
        # my_projects.setCapabilities(my_projects.capabilities2() & QgsDataItem.Fast) # TODO freezes
        my_projects.refresh()
        items.append(my_projects)

        public_projects = QFieldSyncGroupItem(self, 'Public projects', 'public', '../resources/cloud.svg', 2)
        public_projects.setState(QgsDataItem.Populated)
        # public_projects.setCapabilities(public_projects.capabilities2() & QgsDataItem.Fast) # TODO freezes
        public_projects.refresh()
        items.append(public_projects)

        return items

    def actions(self, parent):
        actions = []
        currently_open_project = self.network_manager.projects_cache.currently_open_project

        projects_overview_action = QAction(QIcon(os.path.join(os.path.dirname(__file__), '../resources/cloud.svg')), self.tr('Projects Overview'), parent)
        projects_overview_action.triggered.connect(lambda: CloudProjectsDialog(self.network_manager, iface.mainWindow()).show())

        refresh_action = QAction(QIcon(os.path.join(os.path.dirname(__file__), '../resources/refresh.png')), 'Refresh projects', parent)
        refresh_action.triggered.connect(lambda: self.network_manager.projects_cache.refresh())

        current_project_action = QAction(QIcon(), self.tr('Current Cloud Project'), parent)
        current_project_action.setEnabled(bool(currently_open_project))
        current_project_action.triggered.connect(lambda: CloudProjectsDialog(self.network_manager, iface.mainWindow(), project=currently_open_project).show_project_form())

        actions.append(projects_overview_action)
        # TODO if enabled, it causes freezing of the whole UI
        # actions.append(refresh_action)
        actions.append(current_project_action)

        return actions


    def handleDoubleClick(self):
        if self.network_manager.has_token():
            return False

        if self.network_manager.is_login_active:
            return False

        dlg = CloudLoginDialog(self.network_manager)
        dlg.authenticate()

        return True


    def refresh_icon(self):
        if self.network_manager.has_token():
            self.setIcon(QIcon(os.path.join(os.path.dirname(__file__), '../resources/cloud.svg')))
        else:
            self.setIcon(QIcon(os.path.join(os.path.dirname(__file__), '../resources/cloud_off.svg')))

        self.refresh()


class QFieldSyncGroupItem(QgsDataCollectionItem):
    """ QFieldSync group data item. """

    def __init__(self, parent, name, project_type, icon, order):
        super(QFieldSyncGroupItem, self).__init__(parent, name, '/QFieldSync/' + name)

        self.network_manager = parent.network_manager
        self.project_type = project_type
        self.setIcon(QIcon(os.path.join(os.path.dirname(__file__), icon)))
        self.setSortKey(order)


    def createChildren(self):
        items = []

        projects: List[CloudProject] = self.network_manager.projects_cache.projects

        if projects is None:
            try:
                # TODO try to be make it Fast Fertile
                self.network_manager.projects_cache.refresh_not_async()
            except Exception as err:
                return []

            projects = self.network_manager.projects_cache.projects

        for project in self.network_manager.projects_cache.projects:
            if ((self.project_type == 'public' and not project.is_private)
                or (self.project_type == 'private' and project.is_private)):
                item = QFieldSyncProjectItem(self, project)
                item.setState(QgsDataItem.Populated)
                items.append(item)

        return items


    def actions(self, parent):
        actions = []

        create = QAction(QIcon(os.path.join(os.path.dirname(__file__), '../resources/edit.svg')), 'Create new project', parent)
        create.triggered.connect(lambda: CloudProjectsDialog(self.network_manager, iface.mainWindow()).show_project_form())

        actions.append(create)

        return actions


class QFieldSyncProjectItem(QgsDataItem):
    """ QFieldSync project item. """

    def __init__(self, parent, project):
        super(QFieldSyncProjectItem, self).__init__(QgsDataItem.Collection, parent, project.name, '/QFieldSync/project/' + project.id)
        self.project_id = project.id

    def _create_dialog(self) -> CloudProjectsDialog:
        network_manager = self.parent().parent().network_manager
        # it is important to get the project like this, because if the project list is refreshed, here we will store an old reference
        project = network_manager.projects_cache.find_project(self.project_id)
        return CloudProjectsDialog(network_manager, iface.mainWindow(), project=project)

    def actions(self, parent):
        actions = []

        sync_action = QAction(QIcon(os.path.join(os.path.dirname(__file__), '../resources/cloud.svg')), 'Sync', parent)
        sync_action.triggered.connect(lambda: self._create_dialog().sync())

        properties_action = QAction(QIcon(os.path.join(os.path.dirname(__file__), '../resources/refresh.png')), 'Project properties', parent)
        properties_action.triggered.connect(lambda: self._create_dialog().show_project_form())

        actions.append(sync_action)
        actions.append(properties_action)

        return actions

    def handleDoubleClick(self):
        self._create_dialog().show_project_form()
        return True
