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
from qfieldsync.setting_manager import SettingManager, Scope, String

pluginName = "QFieldSync"


class Preferences(SettingManager):
    def __init__(self):
        SettingManager.__init__(self, pluginName, False)
        self.add_setting(String('exportDirectory', Scope.Global, os.path.expanduser("~/QField/export")))
        self.add_setting(String('exportDirectoryProject', Scope.Project, None))
        self.add_setting(String('importDirectory', Scope.Global, os.path.expanduser("~/QField/import")))
        self.add_setting(String('importDirectoryProject', Scope.Project, None))

