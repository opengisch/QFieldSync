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

from typing import Any, Dict, List, Optional, Tuple, Union
import json
import re
import requests
import urllib.parse
from pathlib import Path


from qgis.PyQt.QtCore import (
    QObject,
    pyqtSignal,
    QUrl,
    QUrlQuery,
    QFileSystemWatcher,
)
from qgis.PyQt.QtNetwork import (
    QNetworkRequest,
    QNetworkReply,
    QHttpMultiPart,
    QHttpPart,
)
from qgis.core import QgsNetworkAccessManager, QgsProject, QgsAuthMethodConfig, QgsApplication

from qfieldsync.core.cloud_project import CloudProject
from qfieldsync.core.preferences import Preferences


class CloudException(Exception):
    
    def __init__(self, reply, exception: Optional[Exception] = None):
        super(CloudException, self).__init__(exception)
        self.reply = reply
        self.parent = exception
        self.httpCode = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)


def from_reply(reply: QNetworkReply) -> Optional[CloudException]:
    if reply.error() == QNetworkReply.NoError:
        return None

    message = ''
    try:
        payload = str(reply.readAll())

        try:
            resp = json.loads(payload)
            if resp.get('code'):
                message = f'[{resp["code"]}] {resp["message"]}'
            else:
                message = resp['detail']
        except:
            if payload:
                message = payload[:500] 

                if len(payload) > 500:
                    message += '…'
    except:
        pass

    if not message:
        message = '[HTTP-{}/QT-{}] {}'.format(reply.attribute(QNetworkRequest.HttpStatusCodeAttribute), reply.error(), reply.errorString())

    return CloudException(reply, Exception(message))



class CloudNetworkAccessManager(QObject):
    
    token_changed = pyqtSignal()
    login_success = pyqtSignal()
    logout_success = pyqtSignal()
    logout_failed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        """Constructor.
        """
        super(CloudNetworkAccessManager, self).__init__(parent=parent)

        self.preferences = Preferences()
        self.url = ''
        self._token = ''
        self._username = ''
        self.projects_cache = CloudProjectsCache(self, self)
        self._nam = QgsNetworkAccessManager.instance()
        self.is_login_active = False

        # use the default URL
        self.set_url(self.preferences.value('qfieldCloudServerUrl'))


    def handle_response(self, reply: QNetworkReply, should_parse_json: bool = True) -> Optional[Union[List, Dict]]:
        payload_str = ''

        error = from_reply(reply)
        if error:
            if error.httpCode == 401 and not self.is_login_active:
                self.set_token('', True)
                self.logout_success.emit()
            raise error

        if not should_parse_json:
            return None

        try:
            payload_str = str(reply.readAll().data(), encoding='utf-8')
            return json.loads(payload_str)
        except Exception as error:
            raise CloudException(reply, error) from error


    def json_object(self, reply: QNetworkReply) -> Dict[str, Any]:
        payload = self.handle_response(reply, True)

        assert isinstance(payload, dict)

        return payload


    def json_array(self, reply: QNetworkReply) -> List[Any]:
        payload = self.handle_response(reply, True)

        assert isinstance(payload, list)

        return payload


    @staticmethod
    def server_urls() -> List[str]:
        return [
            'https://app.qfield.cloud/',
            'https://dev.qfield.cloud/',
            'http://localhost:8000/',
        ]


    def auth(self) -> QgsAuthMethodConfig:
        url = self.url
        auth_manager = QgsApplication.authManager()

        if not auth_manager.masterPasswordHashInDatabase():
            return QgsAuthMethodConfig()

        authcfg = self.preferences.value('qfieldCloudAuthcfg')
        cfg = QgsAuthMethodConfig()
        auth_manager.loadAuthenticationConfig(authcfg, cfg, True)

        return cfg

    
    def set_auth(self, url, **kwargs: str) -> None:
        if self.url != url:
            self.set_url(url)

        authcfg = self.preferences.value('qfieldCloudAuthcfg')
        cfg = QgsAuthMethodConfig()
        auth_manager = QgsApplication.authManager()
        auth_manager.setMasterPassword()
        auth_manager.loadAuthenticationConfig(authcfg, cfg, True)

        if cfg.id():
            cfg.setUri(url)

            for key, value in kwargs.items():
                cfg.setConfig(key, value)

            auth_manager.updateAuthenticationConfig(cfg)
        else:
            cfg.setMethod('Basic')
            cfg.setName('qfieldcloud')
            cfg.setUri(url)

            for key, value in kwargs.items():
                cfg.setConfig(key, value)

            auth_manager.storeAuthenticationConfig(cfg)
            self.preferences.set_value('qfieldCloudAuthcfg', cfg.id())


    def set_url(self, server_url: str) -> None:
        if not server_url:
            server_url = CloudNetworkAccessManager.server_urls()[0]

        self.url = server_url
        self.preferences.set_value('qfieldCloudServerUrl', server_url)


    @property
    def server_url(self):
        url = self.url + '/api/v1/'
        return re.sub(r'([^:]/)(/)+', r'\1', url)


    def login(self, username: str, password: str) -> QNetworkReply:
        """Login to QFieldCloud"""
        self.is_login_active = True

        reply = self.cloud_post('auth/login/', {
            'username': username,
            'password': password,
        })
        reply.finished.connect(lambda: self._on_login_finished(reply))

        return reply


    def get_user(self, token: str) -> QNetworkReply:
        """Gets current user and if token is still valid"""
        return self.cloud_get('auth/user/', {
            'token': token
        })


    def logout(self) -> QNetworkReply:
        """Logout to QFieldCloud"""

        reply = self.cloud_post('auth/logout/')
        reply.finished.connect(lambda: self._on_logout_finished(reply))

        return reply


    def get_projects(self, should_include_public: bool = False) -> QNetworkReply:
        """Get QFieldCloud projects"""

        return self.cloud_get('projects/')


    def get_projects_not_async(self, should_include_public: bool = False) -> List[Dict]:
        """Get QFieldCloud projects synchronously"""
        headers = {'Authorization': 'token {}'.format(self._token)}
        params = {'include-public': should_include_public}

        response = requests.get(self.server_url + self._prepare_uri('projects'), headers=headers, params=params)
        response.raise_for_status()

        return response.json()


    def create_project(self, name: str, owner: str, description: str, private: bool) -> QNetworkReply:
        """Create a new QFieldCloud project"""

        return self.cloud_post('projects/', {
            'name': name,
            'owner': owner,
            'description': description,
            'private': private,
        })


    def update_project(self, project_id: str, name: str, owner: str, description: str, private: bool) -> QNetworkReply:
        """Update an existing QFieldCloud project"""

        return self.cloud_put(['projects', project_id], {
            'name': name,
            'owner': owner,
            'description': description,
            'private': private,
        })


    def delete_project(self, project_id: str) -> QNetworkReply:
        """Delete an existing QFieldCloud project"""

        return self.cloud_delete(['projects', project_id])


    def get_files(self, project_id: str, client: str = 'qgis') -> QNetworkReply:
        """"Get project files and their versions"""

        return self.cloud_get(['files', project_id], {'client': client})


    def get_file(self, filename: str, local_filename: str, version: str = None) -> QNetworkReply:
        """"Download file"""

        return self.cloud_get('files/' + filename, local_filename=local_filename, params={'version': version})


    def delete_file(self, filename: str) -> QNetworkReply:
        return self.cloud_delete('files/' + filename)


    def set_token(self, token: str, update_auth: bool = False) -> None:
        """Sets QFieldCloud authentication token to be used by all the following requests. Set to empty string to disable token authentication."""
        if update_auth:
            self.set_auth(self.url, token=token)

        if self._token == token:
            return

        self._token = token

        self.token_changed.emit()


    def has_token(self) -> bool:
        return self._token is not None and len(self._token) > 0


    def cloud_get(self, uri: Union[str, List[str]], params: Dict[str, Any] = {}, local_filename: str = None) -> QNetworkReply:
        """Issues a GET HTTP request"""
        url = QUrl(self.server_url + self._prepare_uri(uri))
        query = QUrlQuery()

        self._clear_cloud_cookies(url)

        assert isinstance(params, dict)

        for param, value in params.items():
            if value is None:
                continue

            query.addQueryItem(param, str(value))

        url.setQuery(query)

        request = QNetworkRequest(url)
        request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        request.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json')

        if self._token:
            request.setRawHeader(b'Authorization', 'Token {}'.format(self._token).encode('utf-8'))

        reply = self._nam.get(request)
        reply.sslErrors.connect(lambda sslErrors: reply.ignoreSslErrors(sslErrors))
        reply.setParent(self)

        if local_filename is not None:
            reply.finished.connect(lambda: self._on_cloud_get_download_finished(reply, local_filename=local_filename))

        return reply


    def _on_cloud_get_download_finished(self, reply: QNetworkReply, local_filename: str) -> None:
        with open(local_filename, 'wb') as file:
            assert file.write(reply.readAll()) != -1, 'Error while writing to file "{}"'.format(local_filename)


    def cloud_post(self, uri: Union[str, List[str]], payload: Dict = None) -> QNetworkReply:
        url = QUrl(self.server_url + self._prepare_uri(uri))

        self._clear_cloud_cookies(url)

        request = QNetworkRequest(url)
        request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        request.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json')

        if self._token:
            request.setRawHeader(b'Authorization', 'Token {}'.format(self._token).encode('utf-8'))

        payload_bytes = b'' if payload is None else json.dumps(payload).encode('utf-8')
        reply = self._nam.post(request, payload_bytes)
        reply.sslErrors.connect(lambda sslErrors: reply.ignoreSslErrors(sslErrors))
        reply.setParent(self)

        return reply


    def cloud_put(self, uri: Union[str, List[str]], payload: Dict = None) -> QNetworkReply:
        url = QUrl(self.server_url + self._prepare_uri(uri))

        self._clear_cloud_cookies(url)

        request = QNetworkRequest(url)
        request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        request.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json')

        if self._token:
            request.setRawHeader(b'Authorization', 'Token {}'.format(self._token).encode('utf-8'))

        payload_bytes = b'' if payload is None else json.dumps(payload).encode('utf-8')
        reply = self._nam.put(request, payload_bytes)
        reply.sslErrors.connect(lambda sslErrors: reply.ignoreSslErrors(sslErrors))
        reply.setParent(self)

        return reply


    def cloud_delete(self, uri: Union[str, List[str]]) -> QNetworkReply:
        url = QUrl(self.server_url + self._prepare_uri(uri))

        self._clear_cloud_cookies(url)

        request = QNetworkRequest(url)
        request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        request.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json')

        if self._token:
            request.setRawHeader(b'Authorization', 'Token {}'.format(self._token).encode('utf-8'))

        reply = self._nam.deleteResource(request)
        reply.sslErrors.connect(lambda sslErrors: reply.ignoreSslErrors(sslErrors))
        reply.setParent(self)

        return reply


    def cloud_upload_files(self, uri: Union[str, List[str]], filenames: List[str], payload: Dict = None) -> QNetworkReply:
        url = QUrl(self.server_url + self._prepare_uri(uri))

        self._clear_cloud_cookies(url)

        request = QNetworkRequest(url)
        request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)

        if self._token:
            request.setRawHeader(b'Authorization', 'Token {}'.format(self._token).encode('utf-8'))

        multi_part = QHttpMultiPart(QHttpMultiPart.FormDataType)
        multi_part.setParent(self)

        # most of the time there is no other payload
        if payload is not None:
            json_part = QHttpPart()

            json_part.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json')
            json_part.setHeader(QNetworkRequest.ContentDispositionHeader, 'form-data; name="json"')
            json_part.setBody(json.dumps(payload).encode('utf-8'))
            
            multi_part.append(json_part)

        # now attach each file
        for filename in filenames:
            # this might be optimized by usung QFile and QHttpPart.setBodyDevice, but didn't work on the first
            with open(filename, 'rb') as file:
                file_part = QHttpPart()
                file_part.setBody(file.read())
                file_part.setHeader(QNetworkRequest.ContentDispositionHeader, 'form-data; name="file"; filename="{}"'.format(filename))

                multi_part.append(file_part)

        reply = self._nam.post(request, multi_part)
        reply.sslErrors.connect(lambda sslErrors: reply.ignoreSslErrors(sslErrors))
        reply.setParent(self)
        multi_part.setParent(reply)

        return reply


    def _prepare_uri(self, uri: Union[str, List[str]]) -> str:
        if isinstance(uri, str):
            encoded_uri = uri
        else:
            encoded_parts = []
            
            for part in uri:
                encoded_parts.append(urllib.parse.quote(part))

            encoded_uri = '/'.join(encoded_parts)

        if encoded_uri[-1] != '/':
            encoded_uri += '/'
        
        return encoded_uri


    def _on_logout_finished(self, reply: QNetworkReply) -> None:
        try:
            self.json_object(reply)
            self.set_token('', True)
            self.logout_success.emit()
        except CloudException as err:
            self.logout_failed.emit(str(err))
            return

    def _on_login_finished(self, reply: QNetworkReply) -> None:
        self.is_login_active = False

    def _clear_cloud_cookies(self, url: str) -> None:
        '''When the CSRF_TOKEN cookie is present and the plugin is reloaded, the token has expired'''
        for cookie in self._nam.cookieJar().cookiesForUrl(url):
            self._nam.cookieJar().deleteCookie(cookie)


class CloudProjectsCache(QObject):

    projects_started = pyqtSignal()
    projects_updated = pyqtSignal()
    projects_error = pyqtSignal(str)
    project_files_started = pyqtSignal(str)
    project_files_updated = pyqtSignal(str)
    project_files_error = pyqtSignal(str, str)

    def __init__(self, network_manager: CloudNetworkAccessManager, parent=None) -> None:
        super(CloudProjectsCache, self).__init__(parent)

        self.preferences = Preferences()
        self.network_manager = network_manager
        self._error_reason = ''
        self._projects: Optional[List[CloudProject]] = None
        self._projects_reply: Optional[QNetworkReply] = None
        self._fs_watcher = QFileSystemWatcher()
        self._fs_watcher.directoryChanged.connect(self._on_directory_changed)

        self.network_manager.token_changed.connect(self._on_token_changed)
        self.projects_updated.connect(self._on_projects_updated)

        if self.network_manager.has_token():
            self.refresh()


    @property
    def projects(self) -> Optional[List[CloudProject]]:
        return self._projects


    @property
    def error_reason(self) -> str:
        return self._error_reason


    @property
    def currently_open_project(self) -> Optional[CloudProject]:
        project_dir = QgsProject.instance().homePath()

        for project_id, local_dir in self.preferences.value('qfieldCloudProjectLocalDirs').items():
            if local_dir != project_dir:
                continue
            
            cloud_project = self.find_project(project_id)

            if cloud_project is not None:
                return cloud_project


    def refresh(self) -> QNetworkReply:
        # TODO this abort appears sometimes in the UI, think how to hide it?
        if self._projects_reply:
            self._projects_reply.abort()

        self.projects_started.emit()
        self._projects_reply = self.network_manager.get_projects()
        self._projects_reply.finished.connect(lambda: self._on_get_projects_reply_finished(self._projects_reply))

        return self._projects_reply


    def refresh_not_async(self) -> None:
        '''Projects are requested in synchronous manner.
        The function name is cumbersome to discourage it's potential user.
        Better use `refresh()`
        '''
        self.projects_started.emit()

        payload = self.network_manager.get_projects_not_async()

        self._projects = []

        for project_data in payload:
            self._projects.append(CloudProject(project_data))

        self.projects_updated.emit()


    def get_project_files(self, project_id: str) -> QNetworkReply:
        assert project_id

        self.project_files_started.emit(project_id)
        reply = self.network_manager.get_files(project_id)
        reply.finished.connect(lambda: self._on_get_project_files_reply_finished(reply, project_id=project_id))
        return reply


    def find_project(self, project_id: str) -> Optional[CloudProject]:
        if not self._projects or not project_id:
            return

        for project in self._projects:
            if project.id == project_id:
                return project

    def refresh_filesystem_watchers(self, _dirpath: str = '') -> None:
        # TODO in theory we can update only the _dirpath. There are gothas with links etc, better keep it KISS for now
        self._fs_watcher.removePaths(self._fs_watcher.directories())

        if self._projects:
            for project in self._projects:
                if not project.local_dir:
                    continue

                project_dirpath = Path(project.local_dir)
                for project_child_dirpath in project_dirpath.glob('**/'):
                    project_child_dirname = str(project_child_dirpath)

                    # ignore QFieldSync caches
                    if project_child_dirname.startswith(str(project_dirpath.joinpath('.qfieldsync'))):
                        continue

                    self._fs_watcher.addPath(project_child_dirname)

                self._fs_watcher.addPath(project.local_dir)

    def _on_get_projects_reply_finished(self, reply: QNetworkReply) -> None:
        if reply.error() == QNetworkReply.OperationCanceledError:
            return

        self._projects_reply = None

        try:
            payload = self.network_manager.json_array(reply)
        except Exception as err:
            self.projects_error.emit(str(err))
            return

        self._projects = []

        for project_data in payload:
            self._projects.append(CloudProject(project_data))

        self.projects_updated.emit()


    def _on_get_project_files_reply_finished(self, reply: QNetworkReply, project_id: str = None) -> None:
        assert project_id

        cloud_project = self.find_project(project_id)

        if not cloud_project:
            return

        try:
            payload = self.network_manager.json_array(reply)
        except Exception as err:
            payload = None
            self.project_files_error.emit(project_id, str(err))

        cloud_project.update_data({'cloud_files': payload})

        self.project_files_updated.emit(project_id)


    def _on_token_changed(self) -> None:
        self._projects = None
        self.projects_updated.emit()

        if self.network_manager.has_token():
            self.refresh()

    def _on_projects_updated(self) -> None:
        self.refresh_filesystem_watchers()

    def _on_directory_changed(self, dirpath: str) -> None:
        if not self._projects:
            return

        self.refresh_filesystem_watchers(dirpath)

        for project in self._projects:
            if dirpath == project.local_dir:
                project.refresh_files()
