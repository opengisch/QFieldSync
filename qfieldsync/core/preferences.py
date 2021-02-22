import os
from qfieldsync.setting_manager import SettingManager, Scope, String, Dictionary, Bool

pluginName = "QFieldSync"


class Preferences(SettingManager):
    def __init__(self):
        SettingManager.__init__(self, pluginName, False)
        self.add_setting(String('exportDirectory', Scope.Global, os.path.expanduser("~/QField/export")))
        self.add_setting(String('exportDirectoryProject', Scope.Project, None))
        self.add_setting(String('importDirectory', Scope.Global, os.path.expanduser("~/QField/import")))
        self.add_setting(String('importDirectoryProject', Scope.Project, None))
        self.add_setting(Dictionary('qfieldCloudProjectLocalDirs', Scope.Global, {}))
        self.add_setting(Dictionary('qfieldCloudLastProjectFiles', Scope.Global, {}))
        self.add_setting(String('qfieldCloudServerUrl', Scope.Global, ''))
        self.add_setting(String('qfieldCloudAuthcfg', Scope.Global, ''))
        self.add_setting(Bool('qfieldCloudRememberMe', Scope.Global, True))
