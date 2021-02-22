# -*- coding: utf-8 -*-
"""
/***************************************************************************
 CloudProjectsDialog
                                 A QGIS plugin
 Sync your projects to QField on android
                             -------------------
        begin                : 2020-07-28
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
import functools
from pathlib import Path
from enum import Enum
from typing import Optional, Tuple

from qgis.PyQt.QtCore import pyqtSignal, Qt, QItemSelectionModel, QDateTime, QRegularExpression
from qgis.PyQt.QtWidgets import (
    QDialog,
    QToolButton,
    QTableWidgetItem,
    QWidget,
    QCheckBox,
    QHBoxLayout,
    QTreeWidgetItem,
    QFileDialog,
    QMessageBox,
    QMenu,
    QAction,
    QPushButton,
    QHeaderView,
)
from qgis.PyQt.QtGui import QIcon, QFont, QPalette, QColor, QValidator, QRegularExpressionValidator
from qgis.PyQt.QtNetwork import QNetworkReply
from qgis.PyQt.uic import loadUiType

from qgis.core import QgsProject
from qgis.utils import iface

from qfieldsync.gui.cloud_transfer_dialog import CloudTransferDialog
from qfieldsync.gui.cloud_login_dialog import CloudLoginDialog
from qfieldsync.core import Preferences
from qfieldsync.core.cloud_project import CloudProject, ProjectFile, ProjectFileCheckout
from qfieldsync.core.cloud_api import CloudException, CloudNetworkAccessManager
from qfieldsync.core.cloud_transferrer import CloudTransferrer
from qfieldsync.utils.cloud_utils import closure, to_cloud_title


CloudProjectsDialogUi, _ = loadUiType(str(Path(__file__).parent.joinpath('../ui/cloud_projects_dialog.ui')))

class LocalDirFeedback(Enum):
    Error = 'error'
    Warning = 'warning'
    Success = 'success'


def select_table_row(func):
    @functools.wraps(func)
    def closure(self, table_widget, row_idx):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            index = table_widget.model().index(row_idx, 0)
            table_widget.setCurrentIndex(index)
            table_widget.selectionModel().select(index, QItemSelectionModel.ClearAndSelect|QItemSelectionModel.Rows)
            return func(self, *args, **kwargs)
        return wrapper

    return closure


class CloudProjectsDialog(QDialog, CloudProjectsDialogUi):
    projects_refreshed = pyqtSignal()

    def __init__(self, network_manager: CloudNetworkAccessManager, parent: QWidget = None, project: CloudProject = None) -> None:
        """Constructor."""
        super(CloudProjectsDialog, self).__init__(parent=parent)
        self.setupUi(self)
        self.setWindowModality(Qt.WindowModal)
        self.preferences = Preferences()
        self.network_manager = network_manager
        self.current_cloud_project = project
        self.transfer_dialog = None
        self.project_transfer = None
        self.default_local_dir = '~/qfieldsync/cloudprojects/'

        if not self.network_manager.has_token():
            login_dlg = CloudLoginDialog(self.network_manager, self)
            login_dlg.authenticate()
            login_dlg.accepted.connect(lambda: self.welcomeLabelValue.setText(self.network_manager.auth().config('username')))
            login_dlg.accepted.connect(lambda: self.network_manager.projects_cache.refresh())
            login_dlg.rejected.connect(lambda: self.close())
        else:
            self.welcomeLabelValue.setText(self.network_manager.auth().config('username'))

        if self.network_manager.url == self.network_manager.server_urls()[0]:
            self.welcomeLabelValue.setToolTip(self.tr(f'You are logged in with the following username'))
        else:
            self.welcomeLabelValue.setToolTip(self.tr(f'You are logged in with the following username at {self.network_manager.url}'))

        if self.network_manager.has_token():
            self.show_projects()

        self.use_current_project_directory_action = QAction(QIcon(), self.tr('Use Current Project Directory'))
        self.use_current_project_directory_action.triggered.connect(self.on_use_current_project_directory_action_triggered)

        self.projectNameLineEdit.setValidator(QRegularExpressionValidator(QRegularExpression('^[a-zA-Z][-a-zA-Z0-9_]{2,}$')))

        self.createButton.clicked.connect(lambda: self.on_create_button_clicked())
        self.refreshButton.clicked.connect(lambda: self.on_refresh_button_clicked())
        self.backButton.clicked.connect(lambda: self.on_back_button_clicked())
        self.submitButton.clicked.connect(lambda: self.on_submit_button_clicked())
        self.logoutButton.clicked.connect(lambda: self.on_logout_button_clicked())
        self.projectsTable.cellDoubleClicked.connect(lambda: self.on_projects_table_cell_double_clicked())
        self.buttonBox.clicked.connect(lambda: self.on_button_box_clicked())
        self.projectsTable.selectionModel().selectionChanged.connect(lambda: self.on_projects_table_selection_changed())
        self.localDirLineEdit.textChanged.connect(lambda: self.on_local_dir_line_edit_text_changed())
        self.localDirButton.clicked.connect(lambda: self.on_local_dir_button_clicked())
        self.localDirButton.setMenu(QMenu())
        self.localDirButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.localDirButton.menu().addAction(self.use_current_project_directory_action)

        self.network_manager.logout_success.connect(lambda: self._on_logout_success())
        self.network_manager.logout_failed.connect(lambda err: self._on_logout_failed(err))
        self.network_manager.projects_cache.projects_started.connect(lambda: self.on_projects_cached_projects_started())
        self.network_manager.projects_cache.projects_error.connect(lambda err: self.on_projects_cached_projects_error(err))
        self.network_manager.projects_cache.projects_updated.connect(lambda: self.on_projects_cached_projects_updated())
        self.network_manager.projects_cache.project_files_started.connect(lambda project_id: self.on_projects_cached_project_files_started(project_id))
        self.network_manager.projects_cache.project_files_error.connect(lambda project_id, error: self.on_projects_cached_project_files_error(project_id, error))
        self.network_manager.projects_cache.project_files_updated.connect(lambda project_id: self.on_projects_cached_project_files_updated(project_id))

        self.projectFilesTree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.projectFilesTree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.projectFilesTree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.projectFilesTree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)

    def on_projects_cached_projects_started(self) -> None:
        self.projectsStack.setEnabled(False)
        self.feedbackLabel.setVisible(False)
        self.feedbackLabel.setText('')

    def on_projects_cached_projects_error(self, error: str) -> None:
        self.projectsStack.setEnabled(True)
        self.feedbackLabel.setVisible(True)
        self.feedbackLabel.setText(error)

    def on_projects_cached_projects_updated(self) -> None:
        self.projectsStack.setEnabled(True)
        self.projects_refreshed.emit()
        self.show_projects()

    def on_projects_cached_project_files_started(self, project_id: str) -> None:
        self.projectFilesTab.setEnabled(False)
        self.feedbackLabel.setVisible(False)
        self.feedbackLabel.setText('')

    def on_projects_cached_project_files_error(self, project_id: str, error: str) -> None:
        self.projectFilesTab.setEnabled(True)

        if self.current_cloud_project and self.current_cloud_project.id != project_id:
            return

        self.feedbackLabel.setText('Obtaining project files list failed: {}'.format(error))
        self.feedbackLabel.setVisible(True)

    def on_project_files_toggle_expand_button_clicked(self) -> None:
        should_expand = not self.projectFilesTree.topLevelItem(0).data(1, Qt.UserRole)
        self.projectFilesTree.topLevelItem(0).setData(1, Qt.UserRole, should_expand)

        for idx in range(self.projectFilesTree.topLevelItemCount()):
            self.expand_state(self.projectFilesTree.topLevelItem(idx), should_expand)


    def expand_state(self, item: QTreeWidgetItem, should_expand: bool) -> None:
        item.setExpanded(should_expand)

        for idx in range(item.childCount()):
            child = item.child(idx)

            if child.childCount() == 0:
                continue

            self.expand_state(child, should_expand)


    def on_projects_cached_project_files_updated(self, project_id: str) -> None:
        if not self.current_cloud_project or self.current_cloud_project.id != project_id:
            return

        self.projectFilesTab.setEnabled(True)


        # NOTE algorithmic part
        # ##########
        # The "cloud_files" objects are assumed to be sorted alphabetically by name.
        # First split filenames into parts. For example: '/home/ninja.file' will result into ['home', 'ninja.file'] parts.
        # Then store pairs of the part and the corresponding QTreeWidgetItem in a stack. 
        # Pop and push to the stack when the current filename part does not match the previous one.
        # ##########
        stack = []

        for project_file in self.current_cloud_project.get_files(ProjectFileCheckout.Cloud):
            assert isinstance(project_file.versions, list)

            parts = tuple(project_file.path.parts)
            for part_idx, part in enumerate(parts):
                if len(stack) > part_idx and stack[part_idx][0] == part:
                    continue
                else:
                    stack = stack[0:part_idx]

                item = QTreeWidgetItem()
                item.setText(0, part)

                stack.append((part, item))

                if len(stack) == 1:
                    self.projectFilesTree.addTopLevelItem(item)
                else:
                    stack[-2][1].addChild(stack[-1][1])

                # the length of the stack and the parts is equal for file entries
                if len(stack) == len(parts):
                    item.setToolTip(0, project_file.name)
                    item.setData(0, Qt.UserRole, project_file)
                    
                    item.setText(1, str(project_file.size))
                    item.setTextAlignment(1, Qt.AlignRight)
                    item.setText(2, project_file.created_at)

                    for version_idx, version_obj in enumerate(project_file.versions):
                        version_item = QTreeWidgetItem()

                        version_item.setData(0, Qt.UserRole, version_obj)
                        version_item.setText(0, 'Version {}'.format(version_idx + 1))
                        version_item.setText(1, str(version_obj['size']))
                        version_item.setTextAlignment(1, Qt.AlignRight)
                        version_item.setText(2, version_obj['last_modified'])
                        
                        save_as_btn = QPushButton()
                        save_as_btn.setIcon(QIcon(str(Path(__file__).parent.joinpath('../resources/cloud_download.svg'))))
                        save_as_btn.clicked.connect(self.on_save_as_btn_version_clicked(project_file, version_idx))
                        save_as_widget = QWidget()
                        save_as_layout = QHBoxLayout()
                        save_as_layout.setAlignment(Qt.AlignCenter)
                        save_as_layout.setContentsMargins(0, 0, 0, 0)
                        save_as_layout.addWidget(save_as_btn)
                        save_as_widget.setLayout(save_as_layout)

                        item.addChild(version_item)

                        self.projectFilesTree.setItemWidget(version_item, 3, save_as_widget)
                else:
                    item.setExpanded(True)

                    # TODO make a fancy button that marks all the child items as checked or not
        # NOTE END algorithmic part


    @closure
    def on_save_as_btn_version_clicked(self, project_file: ProjectFile, version_idx: int, _is_checked: bool):
        assert project_file.versions
        assert version_idx < len(project_file.versions)

        basename = '{}_{}{}'.format(project_file.path.stem, str(version_idx + 1), project_file.path.suffix)

        if project_file.local_path:
            default_path = project_file.local_path.parent.joinpath(basename)
        else:
            default_path = Path(QgsProject().instance().homePath()).joinpath(project_file.path.parent, basename)

        version_dest_filename, _ = QFileDialog.getSaveFileName(self, self.tr('Select version file name…'), str(default_path))

        if not version_dest_filename:
            return

        reply = self.network_manager.get_file(
            self.current_cloud_project.id + '/' + str(project_file.name) + '/', 
            str(version_dest_filename), 
            project_file.versions[version_idx]['version_id'])
        reply.downloadProgress.connect(lambda r, t: self.on_download_file_progress(reply, r, t, project_file=project_file))
        reply.finished.connect(lambda: self.on_download_file_finished(reply, project_file=project_file))


    def on_download_file_progress(self, _reply: QNetworkReply, bytes_received: int, bytes_total: int, project_file: ProjectFile) -> None:
        self.feedbackLabel.setVisible(True)
        self.feedbackLabel.setText(self.tr('Downloading file "{}" at {}%…').format(project_file.name, int((bytes_total / bytes_received) * 100)))


    def on_download_file_finished(self, reply: QNetworkReply, project_file: ProjectFile) -> None:
        try:
            self.network_manager.handle_response(reply, False)
        except CloudException as err:
            self.feedbackLabel.setText(self.tr('Downloading file "{}" failed: {}'.format(project_file.name, str(err))))
            self.feedbackLabel.setVisible(True)
            return

        self.feedbackLabel.setVisible(False)
        self.feedbackLabel.setText('')


    def on_use_current_project_directory_action_triggered(self, _toggled: bool) -> None:
        self.localDirLineEdit.setText(QgsProject.instance().homePath())


    def on_button_box_clicked(self) -> None:
        self.close()

    def on_local_dir_line_edit_text_changed(self) -> None:
        local_dir = self.localDirLineEdit.text()
        self.submitButton.setEnabled(False)

        feedback, feedback_msg = self.local_dir_feedback(local_dir)
        self.localDirFeedbackLabel.setText(feedback_msg)

        if feedback == LocalDirFeedback.Error:
            self.localDirFeedbackLabel.setStyleSheet('color: red;')
        elif feedback == LocalDirFeedback.Warning:
            self.localDirFeedbackLabel.setStyleSheet('color: orange;')
        else:
            self.localDirFeedbackLabel.setStyleSheet('color: green;')

        self.submitButton.setEnabled(True)

        if self.current_cloud_project:
            self.current_cloud_project.update_data({'local_dir': local_dir})


    def on_local_dir_button_clicked(self) -> None:
        self.localDirLineEdit.setText(self.select_local_dir())


    def on_logout_button_clicked(self) -> None:
        self.logoutButton.setEnabled(False)
        self.feedbackLabel.setVisible(False)
        self.network_manager.logout()


    def on_refresh_button_clicked(self) -> None:
        self.network_manager.projects_cache.refresh()

    def local_dir_feedback(self, local_dir, empty_ok=True, exiting_ok=True) -> Tuple[LocalDirFeedback, str]:
        if not local_dir:
            return LocalDirFeedback.Error, self.tr('Please select local directory where the project to be stored.')
        elif not Path(local_dir).is_dir():
            return LocalDirFeedback.Warning, self.tr('The entered path is not an existing directory. It will be created after you submit this form.')
        elif len(CloudProject.project_files(local_dir)) == 0:
            message = self.tr('The entered path does not contain a QGIS project file yet.')
            status = LocalDirFeedback.Warning

            if empty_ok:
                status = LocalDirFeedback.Success
                message += ' '
                message += self.tr('You can always add one later.')

            return status, message
        elif len(CloudProject.project_files(local_dir)) == 1:
            message = self.tr('The entered path contains one QGIS project file.')
            status = LocalDirFeedback.Warning

            if exiting_ok:
                status = LocalDirFeedback.Success
                message += ' '
                message += self.tr('Exactly as it should be.')

            return status, message
        else:
            return LocalDirFeedback.Error, self.tr('Multiple project files have been found in the directory. Please leave exactly one QGIS project in the root directory.')

    def show_projects(self) -> None:
        self.feedbackLabel.setText('')
        self.feedbackLabel.setVisible(False)

        self.projectsTable.setRowCount(0)
        self.projectsTable.setSortingEnabled(False)

        if self.network_manager.projects_cache.projects is None:
            self.network_manager.projects_cache.refresh()
            return

        for cloud_project in self.network_manager.projects_cache.projects:
            count = self.projectsTable.rowCount()
            self.projectsTable.insertRow(count)
            
            item = QTableWidgetItem(cloud_project.name)
            item.setData(Qt.UserRole, cloud_project)
            item.setData(Qt.EditRole, cloud_project.name)

            cbx_private = QCheckBox()
            cbx_private.setEnabled(False)
            cbx_private.setChecked(cloud_project.is_private)
            # # it's more UI friendly when the checkbox is centered, an ugly workaround to achieve it
            cbx_private_widget = QWidget()
            cbx_private_layout = QHBoxLayout()
            cbx_private_layout.setAlignment(Qt.AlignCenter)
            cbx_private_layout.setContentsMargins(0, 0, 0, 0)
            cbx_private_layout.addWidget(cbx_private)
            cbx_private_widget.setLayout(cbx_private_layout)
            # NOTE the margin is not updated when the table column is resized, so better rely on the code above
            # cbx_private.setStyleSheet("margin-left:50%; margin-right:50%;")

            cbx_local = QCheckBox()
            cbx_local.setEnabled(False)
            cbx_local.setChecked(bool(cloud_project.local_dir))
            # # it's more UI friendly when the checkbox is centered, an ugly workaround to achieve it
            cbx_local_widget = QWidget()
            cbx_local_layout = QHBoxLayout()
            cbx_local_layout.setAlignment(Qt.AlignCenter)
            cbx_local_layout.setContentsMargins(0, 0, 0, 0)
            cbx_local_layout.addWidget(cbx_local)
            cbx_local_widget.setLayout(cbx_local_layout)
            if bool(cloud_project.local_dir):
                cbx_local_widget.setToolTip(str(cloud_project.local_dir))
            else:
                cbx_local_widget.setToolTip(self.tr('No local dir configured'))
            # NOTE the margin is not updated when the table column is resized, so better rely on the code above
            # cbx_local.setStyleSheet("margin-left:50%; margin-right:50%;")

            btn_sync = QToolButton()
            btn_sync.setIcon(QIcon(str(Path(__file__).parent.joinpath('../resources/cloud.svg'))))
            btn_sync.setToolTip(self.tr('Synchronize with QFieldCloud'))
            btn_edit = QToolButton()
            btn_edit.setIcon(QIcon(str(Path(__file__).parent.joinpath('../resources/edit.svg'))))
            btn_edit.setToolTip(self.tr('Edit project details'))
            btn_launch = QToolButton()
            btn_launch.setIcon(QIcon(str(Path(__file__).parent.joinpath('../resources/launch.svg'))))
            btn_delete = QToolButton()
            btn_delete.setPalette(QPalette(QColor('red')))
            btn_delete.setIcon(QIcon(str(Path(__file__).parent.joinpath('../resources/delete.svg'))))
            btn_delete.setToolTip(self.tr('Delete QFieldCloud project'))
            btn_widget = QWidget()
            btn_layout = QHBoxLayout()
            btn_layout.setAlignment(Qt.AlignCenter)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.addWidget(btn_sync)
            btn_layout.addWidget(btn_edit)
            btn_layout.addWidget(btn_launch)
            btn_layout.addWidget(btn_delete)
            btn_widget.setLayout(btn_layout)

            root_project_files = cloud_project.root_project_files
            if len(root_project_files) == 1:
                btn_launch.setToolTip(self.tr('Open project "{}"').format(root_project_files[0]))
            elif len(root_project_files) == 0:
                btn_launch.setToolTip(self.tr('Cannot open project since no local .qgs or .qgz project file found'))
                btn_launch.setEnabled(False)
            else:
                btn_launch.setToolTip(self.tr('Multiple .qgs or .qgz project files found in the project directory'))
                btn_launch.setEnabled(False)

            btn_sync.clicked.connect(self.on_project_sync_button_clicked(self.projectsTable, count)) # pylint: disable=too-many-function-args
            btn_edit.clicked.connect(self.on_project_edit_button_clicked(self.projectsTable, count)) # pylint: disable=too-many-function-args
            btn_launch.clicked.connect(self.on_project_launch_button_clicked(self.projectsTable, count)) # pylint: disable=too-many-function-args
            btn_delete.clicked.connect(self.on_project_delete_button_clicked(self.projectsTable, count)) # pylint: disable=too-many-function-args

            self.projectsTable.setItem(count, 0, item)
            self.projectsTable.setItem(count, 1, QTableWidgetItem(cloud_project.owner))
            self.projectsTable.setCellWidget(count, 2, cbx_private_widget)
            self.projectsTable.setCellWidget(count, 3, cbx_local_widget)
            self.projectsTable.setCellWidget(count, 4, btn_widget)

            font = QFont()

            if cloud_project.is_current_qgis_project:
                font.setBold(True)

            self.projectsTable.item(count, 0).setFont(font)
            self.projectsTable.item(count, 1).setFont(font)

        self.projectsTable.resizeColumnsToContents()
        self.projectsTable.sortByColumn(2, Qt.AscendingOrder)
        self.projectsTable.setSortingEnabled(True)


    def sync(self) -> None:
        assert self.current_cloud_project is not None

        # keep this to make it work, explain it later…
        self.current_cloud_project.name

        if self.current_cloud_project.cloud_files is not None:
            if not self.current_cloud_project.local_dir:
                self.current_cloud_project.update_data({'local_dir': self.select_local_dir()})

            if not self.current_cloud_project.local_dir:
                return

            if len(list(self.current_cloud_project.files_to_sync)) == 0:
                iface.messageBar().pushInfo(f'QFieldSync "{self.current_cloud_project.name}":', self.tr('Everything is already in sync!'))
                return

            self.show_sync_popup()
            return

        reply = self.network_manager.projects_cache.get_project_files(self.current_cloud_project.id)
        reply.finished.connect(lambda: self.sync())


    def launch(self) -> None:
        assert self.current_cloud_project is not None

        if self.current_cloud_project.cloud_files is not None:
            project_filename = self.current_cloud_project.local_project_file

            # no local project name found
            if not project_filename:
                iface.messageBar().pushInfo(f'QFieldSync "{self.current_cloud_project.name}":', self.tr('Cannot find local project file. Please first synchronize.'))
                return

            # it is the current project, no need to reload
            if str(project_filename.local_path) == QgsProject().instance().fileName():
                iface.messageBar().pushInfo(f'QFieldSync "{self.current_cloud_project.name}":', self.tr('Already loaded the selected project.'))
                return

            if QgsProject.instance().read(str(project_filename.local_path)):
                for row_idx in range(self.projectsTable.rowCount()):
                    cloud_project = self.projectsTable.item(row_idx, 0).data(Qt.UserRole)
                    font = QFont()

                    if cloud_project == self.current_cloud_project:
                        font.setBold(True)

                    self.projectsTable.item(row_idx, 0).setFont(font)
                    self.projectsTable.item(row_idx, 1).setFont(font)

            return

        reply = self.network_manager.projects_cache.get_project_files(self.current_cloud_project.id)
        reply.finished.connect(lambda: self.launch())


    def select_local_dir(self) -> Optional[str]:
        """
        ```
            if there is saved location for this project id #
                upload all the files (or the missing on the cloud only)
                download all the files (or the missing on the local only) #
                if project is the current one: #
                    reload the project #
            else
                if the cloud project is not empty
                    ask for path that is empty dir
                    download the project there
                else
                    ask for path #
                
                    if path contains .qgs file: #
                        assert single .qgs file #
                        upload all the files #
            
                save the project location #
            
            ask should that project be opened
        ```
        """

        local_dir = None
        initial_path = self.localDirLineEdit.text() or str(Path(QgsProject.instance().homePath()).parent) or self.default_local_dir

        # cloud project is empty, you can upload a local project into it
        if self.current_cloud_project is None or (self.current_cloud_project.cloud_files is not None and len(self.current_cloud_project.cloud_files) == 0):
            while local_dir is None:
                local_dir = QFileDialog.getExistingDirectory(self, self.tr('Upload local project to QFieldCloud…'), initial_path)

                if local_dir == '':
                    return

                feedback, feedback_msg = self.local_dir_feedback(local_dir, empty_ok=False)
                title = self.tr('Cannot upload local QFieldSync directory')

                # all is good, we can continue
                if feedback == LocalDirFeedback.Success:
                    break

                if feedback == LocalDirFeedback.Error:
                    QMessageBox.critical(self, title, feedback_msg)
                elif feedback == LocalDirFeedback.Warning:
                    QMessageBox.warning(self, title, feedback_msg)

                local_dir = None
                continue

            return local_dir

        # cloud project exists and has files in it, so checkout in an empty dir
        else:
            assert self.current_cloud_project
            assert self.current_cloud_project.cloud_files is not None

            while local_dir is None:
                local_dir = QFileDialog.getExistingDirectory(self, self.tr('Save QFieldCloud project to…'), initial_path)

                if local_dir == '':
                    return

                # when the dir is empty, all is good. But if not there are some file, we need to ask the user to confirm what to do
                if list(Path(local_dir).iterdir()):
                    buttons = QMessageBox.Ok | QMessageBox.Abort
                    feedback, feedback_msg = self.local_dir_feedback(local_dir, exiting_ok=False)
                    title = self.tr('QFieldSync checkout prefers an empty directory')
                    answer = None

                    if feedback == LocalDirFeedback.Error:
                        answer = QMessageBox.critical(self, title, feedback_msg, buttons)
                    elif feedback == LocalDirFeedback.Warning:
                        answer = QMessageBox.warning(self, title, feedback_msg, buttons)

                    if answer == QMessageBox.Abort:
                        local_dir = None
                        continue

                break

        return local_dir

    @select_table_row
    def on_project_sync_button_clicked(self, is_toggled: bool) -> None:
        self.sync()


    @select_table_row
    def on_project_delete_button_clicked(self, is_toggled: bool) -> None:
        button_pressed = QMessageBox.question(
            self, 
            self.tr('Delete QFieldCloud project'), 
            self.tr('Are you sure you want to delete the QFieldCloud project "{}"? Nevertheless, your local files will remain.').format(self.current_cloud_project.name))

        if button_pressed != QMessageBox.Yes:
            return

        self.projectsStack.setEnabled(False)

        reply = self.network_manager.delete_project(self.current_cloud_project.id)
        reply.finished.connect(lambda: self.on_delete_project_reply_finished(reply))


    @select_table_row
    def on_project_launch_button_clicked(self, is_toggled: bool) -> None:
        self.launch()


    @select_table_row
    def on_project_edit_button_clicked(self, is_toggled: bool) -> None:
        self.show_project_form()


    def on_delete_project_reply_finished(self, reply: QNetworkReply) -> None:
        self.projectsStack.setEnabled(True)

        try:
            self.network_manager.handle_response(reply, False)
        except CloudException as err:
            self.feedbackLabel.setText(self.tr('Project delete failed: {}').format(str(err)))
            self.feedbackLabel.setVisible(True)
            return

        self.network_manager.projects_cache.refresh()


    def on_projects_table_cell_double_clicked(self) -> None:
        self.show_project_form()


    def on_create_button_clicked(self) -> None:
        self.projectsTable.clearSelection()
        self.show_project_form()


    def show_project_form(self) -> None:
        self.show()

        self.projectsStack.setCurrentWidget(self.projectsFormPage)
        self.projectTabs.setCurrentWidget(self.projectFormTab)

        username = self.network_manager.auth().config('username')

        self.projectOwnerComboBox.clear()
        self.projectOwnerComboBox.addItem(username, username)
        self.projectFilesTree.clear()

        if self.current_cloud_project is None:
            self.submitButton.setText(self.tr('Create new project'))
            self.projectTabs.setTabEnabled(1, False)
            self.projectTabs.setTabEnabled(2, False)
            self.projectNameLineEdit.setText(to_cloud_title(QgsProject.instance().title()))
            self.projectDescriptionTextEdit.setPlainText('')
            self.projectIsPrivateCheckBox.setChecked(True)

            if CloudProject.get_cloud_project_id(QgsProject.instance().homePath()):
                self.localDirLineEdit.setText('')
            else:
                self.localDirLineEdit.setText(QgsProject().instance().homePath())

        else:
            self.submitButton.setText(self.tr('Update project details'))
            self.projectTabs.setTabEnabled(1, True)
            self.projectTabs.setTabEnabled(2, True)
            # TODO validate project name to match QFieldCloudRequirements
            self.projectNameLineEdit.setText(self.current_cloud_project.name)
            self.projectDescriptionTextEdit.setPlainText(self.current_cloud_project.description)
            self.projectIsPrivateCheckBox.setChecked(self.current_cloud_project.is_private)
            self.localDirLineEdit.setText(self.current_cloud_project.local_dir)
            self.projectUrlLabelValue.setText('<a href="{url}">{url}</a>'.format(url=self.current_cloud_project.url))
            self.createdAtLabelValue.setText(QDateTime.fromString(self.current_cloud_project.created_at, Qt.ISODateWithMs).toString())
            self.updatedAtLabelValue.setText(QDateTime.fromString(self.current_cloud_project.updated_at, Qt.ISODateWithMs).toString())
            self.lastSyncedAtLabelValue.setText(QDateTime.fromString(self.current_cloud_project.updated_at, Qt.ISODateWithMs).toString())

            index = self.projectOwnerComboBox.findData(self.current_cloud_project.owner)
            
            if index == -1:
                self.projectOwnerComboBox.insertItem(0, self.current_cloud_project.owner, self.current_cloud_project.owner)
                self.projectOwnerComboBox.setCurrentIndex(0)

            self.network_manager.projects_cache.get_project_files(self.current_cloud_project.id)


    def on_back_button_clicked(self) -> None:
        self.projectsStack.setCurrentWidget(self.projectsListPage)


    def on_submit_button_clicked(self) -> None:
        cloud_project_data = {
            'name': self.projectNameLineEdit.text(),
            'description': self.projectDescriptionTextEdit.toPlainText(),
            'owner': self.projectOwnerComboBox.currentData(),
            'private': self.projectIsPrivateCheckBox.isChecked(),
            'local_dir': self.localDirLineEdit.text()
        }

        if self.projectNameLineEdit.validator().validate(cloud_project_data['name'], 0)[0] != QValidator.Acceptable:
            QMessageBox.warning(None, self.tr('Invalid project name'), self.tr('You cannot create a new project without setting a valid name first.'))
            return

        self.projectsFormPage.setEnabled(False)
        self.feedbackLabel.setVisible(True)

        if self.current_cloud_project is None:
            self.feedbackLabel.setText(self.tr('Creating project…'))
            reply = self.network_manager.create_project(
                cloud_project_data['name'], 
                cloud_project_data['owner'], 
                cloud_project_data['description'], 
                cloud_project_data['private'])
            reply.finished.connect(lambda: self.on_create_project_finished(reply, local_dir=cloud_project_data['local_dir']))
        else:
            self.current_cloud_project.update_data(cloud_project_data)
            self.feedbackLabel.setText(self.tr('Updating project…'))

            reply = self.network_manager.update_project(
                self.current_cloud_project.id, 
                self.current_cloud_project.name, 
                self.current_cloud_project.owner, 
                self.current_cloud_project.description, 
                self.current_cloud_project.is_private)
            reply.finished.connect(lambda: self.on_update_project_finished(reply))


    def on_create_project_finished(self, reply: QNetworkReply, local_dir: str = None) -> None:
        self.projectsFormPage.setEnabled(True)

        try:
            payload = self.network_manager.json_object(reply)
        except CloudException as err:
            self.feedbackLabel.setText('Project create failed: {}'.format(str(err)))
            self.feedbackLabel.setVisible(True)
            return

        # save `local_dir` configuration permanently, `CloudProject` constructor does this for free
        project = CloudProject({
            **payload,
            'local_dir': local_dir,
        })

        self.projectsStack.setCurrentWidget(self.projectsListPage)
        self.feedbackLabel.setVisible(False)

        reply = self.network_manager.projects_cache.refresh()
        reply.finished.connect(lambda: self.on_create_project_finished_projects_refreshed(project.id))


    def on_create_project_finished_projects_refreshed(self, project_id: str) -> None:
        self.current_cloud_project = self.network_manager.projects_cache.find_project(project_id)

        self.launch()
        self.sync()


    def on_update_project_finished(self, reply: QNetworkReply) -> None:
        self.projectsFormPage.setEnabled(True)

        try:
            self.network_manager.json_object(reply)
        except CloudException as err:
            self.feedbackLabel.setText('Project update failed: {}'.format(str(err)))
            self.feedbackLabel.setVisible(True)
            return

        self.projectsStack.setCurrentWidget(self.projectsListPage)
        self.feedbackLabel.setVisible(False)

        self.network_manager.projects_cache.refresh()


    def on_projects_table_selection_changed(self) -> None:
        if self.projectsTable.selectionModel().hasSelection():
            row_idx = self.projectsTable.currentRow()
            self.current_cloud_project = self.projectsTable.item(row_idx, 0).data(Qt.UserRole)
        else:
            self.current_cloud_project = None


    def show_sync_popup(self) -> None:
        assert self.current_cloud_project is not None, 'No project to download selected'
        assert self.current_cloud_project.local_dir, 'Cannot download a project without `local_dir` properly set'

        self.project_transfer = CloudTransferrer(self.network_manager, self.current_cloud_project)
        self.transfer_dialog = CloudTransferDialog(self.project_transfer, self)
        self.transfer_dialog.rejected.connect(self.on_transfer_dialog_rejected)
        self.transfer_dialog.accepted.connect(self.on_transfer_dialog_accepted)
        self.transfer_dialog.show()


    def on_transfer_dialog_rejected(self) -> None:
        if self.project_transfer:
            self.project_transfer.abort_requests()

        if self.transfer_dialog:
            self.transfer_dialog.close()

        self.project_transfer = None
        self.transfer_dialog = None


    def on_transfer_dialog_accepted(self) -> None:
        QgsProject().instance().reloadAllLayers()

        self.transfer_dialog.close()
        self.project_transfer = None
        self.transfer_dialog = None


    def _on_logout_success(self) -> None:
        self.projectsTable.setRowCount(0)

        self.close()


    def _on_logout_failed(self, err: str) -> None:
        self.feedbackLabel.setText('Logout failed: {}'.format(str(err)))
        self.feedbackLabel.setVisible(True)
        self.logoutButton.setEnabled(True)
