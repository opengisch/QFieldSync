# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QFieldSync
                             -------------------
        begin                : 2020-08-01
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


from enum import IntFlag
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union
import hashlib
import sqlite3

from qgis.core import QgsProject

from qfieldsync.core.preferences import Preferences


class ProjectFileCheckout(IntFlag):
    Deleted = 0
    Local = 1
    Cloud = 2
    LocalAndCloud = 3


class ProjectFile:
    def __init__(self, data: Dict[str, Any], local_dir: str = None) -> None:
        self._local_dir = local_dir
        self._temp_dir = None
        self._data = data


    @property
    def name(self) -> str:
        return self._data['name']


    @property
    def path(self) -> Path:
        return Path(self.name)


    @property
    def dir_name(self) -> str:
        return str(self.path.parent)


    @property
    def created_at(self) -> Optional[str]:
        if not self.versions:
            return
        
        return self.versions[-1].get('created_at')


    @property
    def updated_at(self) -> Optional[str]:
        if not self.versions:
            return
        
        return self.versions[-1].get('updated_at')


    @property
    def versions(self) -> Optional[List[Dict[str, str]]]:
        return self._data.get('versions')


    @property
    def checkout(self) -> ProjectFileCheckout:
        checkout = ProjectFileCheckout.Deleted

        if self.local_path and self.local_path.exists():
            checkout |= ProjectFileCheckout.Local

        # indirect way to check whether it is a cloud project
        if self.size is not None:
            checkout |= ProjectFileCheckout.Cloud

        return checkout


    @property
    def size(self) -> Optional[int]:
        return self._data.get('size')


    @property
    def sha256(self) -> Optional[str]:
        return self._data.get('sha256')


    @property
    def local_size(self) -> Optional[int]:
        if not self.local_path_exists:
            return

        return self.local_path.stat().st_size


    @property
    def local_path(self) -> Optional[Path]:
        if not self._local_dir:
            return

        return Path(self._local_dir + '/' + self.name)


    @property
    def local_path_exists(self) -> bool:
        if self.local_path:
            return self.local_path.exists()

        return False


    @property
    def local_sha256(self) -> Optional[str]:
        if not self.local_path_exists:
            return

        assert self.local_path
        assert self.local_path.is_file()

        with open(self.local_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()

    def flush(self) -> None:
        if not self._local_dir:
            return

        if self.name.endswith('.gpkg'):
            path = Path(str(self.local_path) + '-wal')
            if path.exists() and path.stat().st_size > 0:
                conn = sqlite3.connect(str(self.local_path))

                with conn:
                    conn.execute('PRAGMA wal_checkpoint')

class CloudProject:

    def __init__(self, project_data: Dict[str, Any]) -> None:
        """Constructor.
        """
        self._preferences = Preferences()
        self._files = {}
        self._data = {}
        self._cloud_files = None
        self._local_dir = None

        self.update_data(project_data)


    def update_data(self, new_data: Dict[str, Any]) -> None:
        self._data = {**self._data, **new_data}
        # make sure empty string is converted to None

        if 'local_dir' in new_data and self._local_dir != (new_data.get('local_dir') or None):
            self._local_dir = self._data.get('local_dir') or None
            
            del self._data['local_dir']

            old_project_local_dirs = self._preferences.value('qfieldCloudProjectLocalDirs')
            new_value = {
                **old_project_local_dirs,
                self.id: self._local_dir,
            }

            self._preferences.set_value('qfieldCloudProjectLocalDirs', new_value)

            if self._local_dir:
                Path(self._local_dir).mkdir(exist_ok=True, parents=True)

        # NOTE the cloud_files value is a list and may be in any order, so always assume that if the key is present in the new data, then there is a change
        if 'cloud_files' in new_data:
            self._cloud_files = self._data.get('cloud_files')

            del self._data['cloud_files']

            if isinstance(self._cloud_files, list):
                self._preferences.set_value('qfieldCloudLastProjectFiles', {
                    **self._preferences.value('qfieldCloudLastProjectFiles'),
                    self.id: [cloud_file['name'] for cloud_file in self._cloud_files],
                })
                self._cloud_files = sorted(self._cloud_files, key=lambda f: f['name'])
            else:
                assert self._cloud_files is None

        if 'cloud_files' in new_data or 'local_dir' in new_data or not self._files:
            self.refresh_files()


    @staticmethod
    def project_files(path: str) -> List[str]:
        project_filenames = []
        project_filenames += list(Path(path).glob('*.qgs'))
        project_filenames += list(Path(path).glob('*.qgz'))

        return project_filenames

    @staticmethod
    def get_cloud_project_id(path: str) -> Optional[str]:
        project_local_dirs: Dict[str, str] = Preferences().value('qfieldCloudProjectLocalDirs')

        for project_id, project_path in project_local_dirs.items():
            if project_path == path:
                return project_id

        return None


    @property
    def id(self) -> str:
        return self._data['id']


    @property
    def name(self) -> str:
        return self._data['name']


    @property
    def owner(self) -> str:
        return self._data['owner']


    @property
    def description(self) -> str:
        return self._data['description']


    @property
    def is_private(self) -> bool:
        return self._data['private']


    @property
    def created_at(self) -> str:
        return self._data['created_at']


    @property
    def updated_at(self) -> str:
        return self._data['updated_at']


    @property
    def local_dir(self) -> Optional[str]:
        return self._preferences.value('qfieldCloudProjectLocalDirs').get(self.id)


    # TODO remove this, use `get_files` instead
    @property
    def cloud_files(self) -> Optional[List]:
        return self._cloud_files


    @property
    def files_to_sync(self) -> Iterator[ProjectFile]:
        for project_file in self.get_files():
            project_file.flush()

            # don't attempt to sync files that are the same both locally and remote
            if project_file.sha256 == project_file.local_sha256:
                continue

            # ignore local files that are not in the temp directory
            if project_file.checkout & ProjectFileCheckout.Local and not project_file.local_path_exists:
                continue

            yield project_file


    @property
    def is_current_qgis_project(self) -> bool:
        project_home_path = QgsProject.instance().homePath()

        return len(project_home_path) > 0 and self.local_dir == project_home_path


    @property
    def url(self) -> str:
        return 'https://qfield.cloud/projects/{}'.format(self.id)

    @property
    def root_project_files(self) -> List[str]:
        if self.local_dir:
            return CloudProject.project_files(self.local_dir)
        else:
            return []

    @property
    def local_project_file(self) -> Optional[ProjectFile]:
        if len(self.root_project_files) != 1:
            return None

        for project_file in self.get_files():
            if project_file.local_path == self.root_project_files[0]:
                return project_file

        return None

    def get_files(self, checkout_filter: Optional[ProjectFileCheckout] = None) -> List[ProjectFile]:
        if checkout_filter is None:
            return list(self._files.values())

        return [file for file in self._files.values() if file.checkout & checkout_filter]


    def refresh_files(self) -> None:
        self._files = {}

        if self._cloud_files:
            for file_obj in self._cloud_files:
                self._files[file_obj['name']] = ProjectFile(file_obj, local_dir=self.local_dir)

        if self.local_dir:
            local_filenames = [f for f in [str(f.relative_to(self.local_dir)) for f in Path(self.local_dir).glob('**/*') if f.is_file()] if not f.startswith('.qfieldsync')]

            for filename in local_filenames:
                if filename in self._files:
                    continue

                if filename.endswith(('.gpkg-shm', '.gpkg-wal')):
                    continue

                if filename.endswith(('.qgs~', '.qgz~')):
                    continue

                self._files[filename] = ProjectFile({'name': filename}, local_dir=self.local_dir)
