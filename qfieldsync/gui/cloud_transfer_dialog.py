# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QFieldCloudDialog
                                 A QGIS plugin
 Sync your projects to QField on android
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
from typing import Dict, List
import os
from enum import Enum

from qgis.PyQt.QtCore import Qt, QObject
from qgis.PyQt.QtGui import QShowEvent
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QTreeWidgetItem, QWidget, QCheckBox, QHBoxLayout, QHeaderView, QLabel
from qgis.PyQt.uic import loadUiType

from qfieldsync.core.cloud_transferrer import CloudTransferrer
from qfieldsync.core.cloud_project import ProjectFile, ProjectFileCheckout

from ..utils.qt_utils import make_icon, make_pixmap


CloudTransferDialogUi, _ = loadUiType(os.path.join(os.path.dirname(__file__), '../ui/cloud_transfer_dialog.ui'))


class ProjectFileAction(Enum):
    NoAction = 0
    DeleteCloud = 1
    DeleteLocal = 2
    UploadAndCreate = 3
    UploadAndReplace = 4
    DownloadAndCreate = 5
    DownloadAndReplace = 6

class CloudTransferDialog(QDialog, CloudTransferDialogUi):

    def __init__(self, project_transfer: CloudTransferrer, parent: QObject = None) -> None:
        """Constructor.
        """
        super(CloudTransferDialog, self).__init__(parent=parent)
        self.setupUi(self)
        self.project_transfer = project_transfer

        self.project_transfer.error.connect(self.on_error)
        self.project_transfer.upload_progress.connect(self.on_upload_transfer_progress)
        self.project_transfer.download_progress.connect(self.on_download_transfer_progress)
        self.project_transfer.finished.connect(self.on_transfer_finished)

        self.filesTree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.filesTree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.filesTree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.filesTree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.filesTree.header().setSectionResizeMode(4, QHeaderView.Stretch)
        self.filesTree.expandAll()

        self.filesTree.model().setHeaderData(1, Qt.Horizontal, make_icon('computer.svg'), Qt.DecorationRole)
        self.filesTree.model().setHeaderData(3, Qt.Horizontal, make_icon('cloud.svg'), Qt.DecorationRole)

        self.setWindowTitle(self.tr('Synchronizing project "{}"').format(self.project_transfer.cloud_project.name))
        self.buttonBox.button(QDialogButtonBox.Ok).setVisible(False)
        self.buttonBox.button(QDialogButtonBox.Abort).setVisible(False)
        self.buttonBox.button(QDialogButtonBox.Cancel).setVisible(False)
        self.buttonBox.button(QDialogButtonBox.Apply).setVisible(False)
        self.buttonBox.button(QDialogButtonBox.Apply).setText(self.tr('Sync!'))
        self.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.on_project_apply_clicked)

        self.preferNoneButton.clicked.connect(self._on_prefer_none_button_clicked)
        self.preferLocalButton.clicked.connect(self._on_prefer_local_button_clicked)
        self.preferCloudButton.clicked.connect(self._on_prefer_cloud_button_clicked)

    def showEvent(self, event: QShowEvent) -> None:
        self.buttonBox.button(QDialogButtonBox.Cancel).setVisible(True)

        super().showEvent(event)

        self.build_files_tree()
        self.stackedWidget.setCurrentWidget(self.filesPage)
        self.buttonBox.button(QDialogButtonBox.Apply).setVisible(True)


    def build_files_tree(self):
        # NOTE algorithmic part
        # ##########
        # The "cloud_files" objects are assumed to be sorted alphabetically by name.
        # First split filenames into parts. For example: '/home/ninja.file' will result into ['home', 'ninja.file'] parts.
        # Then store pairs of the part and the corresponding QTreeWidgetItem in a stack. 
        # Pop and push to the stack when the current filename part does not match the previous one.
        # ##########
        stack = []

        for project_file in self.project_transfer.cloud_project.files_to_sync:
            parts = tuple(project_file.path.parts)
            for part_idx, part in enumerate(parts):
                if len(stack) > part_idx and stack[part_idx][0] == part:
                    continue
                else:
                    stack = stack[0:part_idx]

                item = QTreeWidgetItem()
                item.setText(0, part)
                item.setExpanded(True)

                stack.append((part, item))

                if len(stack) == 1:
                    self.filesTree.addTopLevelItem(item)
                else:
                    stack[-2][1].addChild(stack[-1][1])

                # the length of the stack and the parts is equal for file entries
                if len(stack) == len(parts):
                    item.setData(0, Qt.UserRole, project_file)
                    self.add_file_checkbox_buttons(item, project_file)
                else:
                    # TODO make a fancy button that marks all the child items as checked or not
                    pass
        # NOTE END algorithmic part


    def on_project_apply_clicked(self) -> None:
        self.buttonBox.button(QDialogButtonBox.Ok).setVisible(True)
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(False)
        self.buttonBox.button(QDialogButtonBox.Abort).setVisible(True)
        self.buttonBox.button(QDialogButtonBox.Apply).setVisible(False)
        self.buttonBox.button(QDialogButtonBox.Cancel).setVisible(False)

        files: Dict[str, List[ProjectFile]] = {'to_upload': [], 'to_download': [], 'to_delete': []}

        for item_idx in range(self.filesTree.topLevelItemCount()):
            item = self.filesTree.topLevelItem(item_idx)

            self.traverse_tree_item(item, files)

        self.show_progress_page(files)

        self.project_transfer.sync(files['to_upload'], files['to_download'], files['to_delete'])


    def traverse_tree_item(self, item: QTreeWidgetItem, files: Dict[str, List[ProjectFile]]) -> None:
        project_file = item.data(0, Qt.UserRole)

        if project_file:
            assert item.childCount() == 0

            project_file_action = self.project_file_action(item)

            if project_file_action == ProjectFileAction.DeleteLocal or project_file_action == ProjectFileAction.DeleteCloud:
                files['to_delete'].append(project_file)
            elif project_file_action == ProjectFileAction.DownloadAndCreate or project_file_action == ProjectFileAction.DownloadAndReplace:
                files['to_download'].append(project_file)
            elif project_file_action == ProjectFileAction.UploadAndCreate or project_file_action == ProjectFileAction.UploadAndReplace:
                files['to_upload'].append(project_file)
            elif project_file_action == ProjectFileAction.NoAction:
                pass
            else:
                raise Exception(f'Unknown project file action {project_file_action}')

            return

        for child_idx in range(item.childCount()):
            self.traverse_tree_item(item.child(child_idx), files)


    def add_file_checkbox_buttons(self, item: QTreeWidgetItem, project_file: ProjectFile) -> None:
        is_local_enabled = project_file.local_path_exists
        is_cloud_enabled = project_file.checkout & ProjectFileCheckout.Cloud
        is_local_checked = is_local_enabled

        local_checkbox = QCheckBox()
        local_checkbox.setChecked(is_local_checked)
        local_checkbox.toggled.connect(lambda _is_checked: self.on_local_checkbox_toggled(item))
        local_checkbox_widget = QWidget()
        local_checkbox_layout = QHBoxLayout()
        local_checkbox_layout.setAlignment(Qt.AlignCenter)
        local_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        local_checkbox_layout.addWidget(local_checkbox)
        local_checkbox_widget.setLayout(local_checkbox_layout)

        cloud_checkbox = QCheckBox()
        cloud_checkbox.setChecked(is_cloud_enabled and not is_local_checked)
        cloud_checkbox.toggled.connect(lambda _is_checked: self.on_cloud_checkbox_toggled(item))
        cloud_checkbox_widget = QWidget()
        cloud_checkbox_layout = QHBoxLayout()
        cloud_checkbox_layout.setAlignment(Qt.AlignCenter)
        cloud_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        cloud_checkbox_layout.addWidget(cloud_checkbox)
        cloud_checkbox_widget.setLayout(cloud_checkbox_layout)

        arrow_widget = QWidget()
        arrow_layout = QHBoxLayout()
        arrow_layout.setAlignment(Qt.AlignCenter)
        arrow_layout.setContentsMargins(0, 0, 0, 0)
        localLabel, arrowLabel, cloudLabel = QLabel(), QLabel(), QLabel()
        localLabel.setObjectName('local')
        arrowLabel.setObjectName('arrow')
        cloudLabel.setObjectName('cloud')
        arrow_layout.addWidget(localLabel)
        arrow_layout.addWidget(arrowLabel)
        arrow_layout.addWidget(cloudLabel)
        arrow_widget.setLayout(arrow_layout)

        self.filesTree.setItemWidget(item, 1, local_checkbox_widget)
        self.filesTree.setItemWidget(item, 2, arrow_widget)
        self.filesTree.setItemWidget(item, 3, cloud_checkbox_widget)

        self.update_detail(item)


    def on_error(self, descr: str, error: Exception = None) -> None:
        self.errorLabel.setText(self.errorLabel.text() + '\n' + descr)

    
    def on_upload_transfer_progress(self, fraction: float) -> None:
        self.uploadProgressBar.setValue(int(fraction * 100))


    def on_download_transfer_progress(self, fraction: float) -> None:
        self.downloadProgressBar.setValue(int(fraction * 100))


    def on_transfer_finished(self) -> None:
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(True)
        self.buttonBox.button(QDialogButtonBox.Abort).setEnabled(False)


    def on_local_checkbox_toggled(self, item: QTreeWidgetItem) -> None:
        project_file = item.data(0, Qt.UserRole)
        is_cloud_enabled = project_file.checkout & ProjectFileCheckout.Cloud

        local_checkbox = self.filesTree.itemWidget(item, 1).children()[1]
        cloud_checkbox = self.filesTree.itemWidget(item, 3).children()[1]

        if local_checkbox.isChecked():
            cloud_checkbox.setChecked(False)

        self.update_detail(item)


    def on_cloud_checkbox_toggled(self, item: QTreeWidgetItem) -> None:
        project_file = item.data(0, Qt.UserRole)
        is_local_enabled = project_file.local_path_exists

        local_checkbox = self.filesTree.itemWidget(item, 1).children()[1]
        cloud_checkbox = self.filesTree.itemWidget(item, 3).children()[1]

        if cloud_checkbox.isChecked():
            local_checkbox.setChecked(False)

        self.update_detail(item)


    def project_file_action(self, item: QTreeWidgetItem) -> ProjectFileAction:
        project_file = item.data(0, Qt.UserRole)
        is_local_enabled = project_file.local_path_exists
        is_cloud_enabled = project_file.checkout & ProjectFileCheckout.Cloud
        local_checkbox = self.filesTree.itemWidget(item, 1).children()[1]
        cloud_checkbox = self.filesTree.itemWidget(item, 3).children()[1]

        if local_checkbox.isChecked():
            if is_cloud_enabled:
                if is_local_enabled:
                    return ProjectFileAction.UploadAndReplace
                else:
                    return ProjectFileAction.DeleteCloud
            else:
                return ProjectFileAction.UploadAndCreate
        elif cloud_checkbox.isChecked():
            if is_local_enabled:
                if is_cloud_enabled:
                    return ProjectFileAction.DownloadAndReplace
                else:
                    return ProjectFileAction.DeleteLocal
            else:
                return ProjectFileAction.DownloadAndCreate

        return ProjectFileAction.NoAction


    def update_detail(self, item: QTreeWidgetItem) -> None:
        project_file_action = self.project_file_action(item)

        project_file = item.data(0, Qt.UserRole)
        has_local = project_file.local_path_exists
        has_cloud = project_file.checkout & ProjectFileCheckout.Cloud

        local_icon = 'file.svg' if has_local else 'missing.svg'
        cloud_icon = 'file.svg' if has_cloud else 'missing.svg'

        if project_file_action == ProjectFileAction.NoAction:
            detail = self.tr('No action')
            arrow_icon = 'sync_disabled'
        elif project_file_action == ProjectFileAction.UploadAndCreate:
            detail = self.tr('Create file on the cloud')
            cloud_icon = 'file_add-green.svg'
            arrow_icon = 'arrow_forward-green'
        elif project_file_action == ProjectFileAction.UploadAndReplace:
            detail = self.tr('Upload (will replace file on the cloud)')
            cloud_icon = 'file_refresh-orange.svg'
            arrow_icon = 'arrow_forward-orange'
        elif project_file_action == ProjectFileAction.DownloadAndCreate:
            detail = self.tr('Download file from the cloud')
            local_icon = 'file_add-green.svg'
            arrow_icon = 'arrow_back-green.svg'
        elif project_file_action == ProjectFileAction.DownloadAndReplace:
            detail = self.tr('Download (will replace local file)')
            local_icon = 'file_refresh-orange.svg'
            arrow_icon = 'arrow_back-orange.svg'
        elif project_file_action == ProjectFileAction.DeleteCloud:
            detail = detail = self.tr('Delete file on the cloud')
            cloud_icon = 'delete-red.svg'
            arrow_icon = 'arrow_forward-red.svg'
        elif project_file_action == ProjectFileAction.DeleteLocal:
            detail = detail = self.tr('Delete local file')
            local_icon = 'delete-red.svg'
            arrow_icon = 'arrow_back-red.svg'
        else:
            raise Exception(f'Unknown project file action {project_file_action}')

        arrow_widget = self.filesTree.itemWidget(item, 2)
        arrow_widget.findChild(QLabel, 'local').setPixmap(make_pixmap(local_icon))
        arrow_widget.findChild(QLabel, 'arrow').setPixmap(make_pixmap(arrow_icon))
        arrow_widget.findChild(QLabel, 'cloud').setPixmap(make_pixmap(cloud_icon))
        item.setText(4, detail)


    def _on_offline_converter_total_progress_updated(self, current: int, total: int, message: str) -> None:
        self.totalProgressBar.setMaximum(total)
        self.totalProgressBar.setValue(current)
        self.statusLabel.setText(message)


    def _on_offline_converter_task_progress_updated(self, progress: int, total: int) -> None:
        self.layerProgressBar.setMaximum(total)
        self.layerProgressBar.setValue(progress)


    def on_offline_editing_progress_stopped(self) -> None:
        self.offline_editing_done = True


    def on_offline_editing_layer_progress_updated(self, progress: int, total: int) -> None:
        self.totalProgressBar.setMaximum(total)
        self.totalProgressBar.setValue(progress)


    def on_offline_editing_progress_mode_set(self, _, total: int) -> None:
        self.layerProgressBar.setMaximum(total)
        self.layerProgressBar.setValue(0)


    def on_offline_editing_progress_updated(self, progress: int) -> None:
        self.layerProgressBar.setValue(progress)


    def _on_prefer_none_button_clicked(self) -> None:
        # NOTE: LocalAndCloud is used to make neither checkbox checked. Don't use Deleted, as it might be added as a checkbox later.
        self._file_tree_set_checkboxes(ProjectFileCheckout.LocalAndCloud)


    def _on_prefer_local_button_clicked(self) -> None:
        self._file_tree_set_checkboxes(ProjectFileCheckout.Local)


    def _on_prefer_cloud_button_clicked(self) -> None:
        self._file_tree_set_checkboxes(ProjectFileCheckout.Cloud)


    def _file_tree_set_checkboxes(self, checkout: ProjectFileCheckout) -> None:
        for item_idx in range(self.filesTree.topLevelItemCount()):
            self._file_tree_set_checkboxes_recursive(self.filesTree.topLevelItem(item_idx), checkout)


    def _file_tree_set_checkboxes_recursive(self, item: QTreeWidgetItem, checkout: ProjectFileCheckout) -> None:
        project_file = item.data(0, Qt.UserRole)

        if project_file:
            assert item.childCount() == 0
        else:
            for child_idx in range(item.childCount()):
                self._file_tree_set_checkboxes_recursive(item.child(child_idx), checkout)
            return

        local_checkbox = self.filesTree.itemWidget(item, 1).children()[1]
        cloud_checkbox = self.filesTree.itemWidget(item, 3).children()[1]

        if checkout == ProjectFileCheckout.Local and local_checkbox.isEnabled():
            local_checkbox.setChecked(True)
        elif checkout == ProjectFileCheckout.Cloud and cloud_checkbox.isEnabled():
            cloud_checkbox.setChecked(True)
        elif checkout == ProjectFileCheckout.LocalAndCloud:
            local_checkbox.setChecked(False)
            cloud_checkbox.setChecked(False)
        elif checkout == ProjectFileCheckout.Deleted:
            # Reserved for a better future
            pass

    def show_progress_page(self, files: Dict[str, List[ProjectFile]]) -> None:
        total_delete_count = 0
        local_delete_count = 0
        cloud_delete_count = 0
        download_count = len(files['to_download'])
        upload_count = len(files['to_upload'])

        for f in files['to_delete']:
            total_delete_count += 1

            if f.checkout & ProjectFileCheckout.Local:
                local_delete_count += 1
            elif f.checkout & ProjectFileCheckout.Local:
                cloud_delete_count += 1

        upload_message = ''
        if upload_count or cloud_delete_count:
            if upload_count:
                upload_message += self.tr('{} file(s) to overwrite on the cloud.'.format(upload_count))
            if cloud_delete_count:
                upload_message += self.tr('{} file(s) to delete on QFieldCloud.'.format(cloud_delete_count))

            self.uploadProgressBar.setValue(0)
            self.uploadProgressBar.setEnabled(True)
        else:
            self.uploadProgressBar.setValue(100)
            self.uploadProgressBar.setEnabled(False)
            upload_message = self.tr('Nothing to do on the cloud.')
        self.uploadProgressFeedbackLabel.setText(upload_message)

        download_message = ''
        if download_count or local_delete_count:
            if download_count:
                download_message += self.tr('{} file(s) to overwrite locally.'.format(download_count))
            if local_delete_count:
                download_message += self.tr('{} file(s) to delete locally.'.format(local_delete_count))

            self.downloadProgressBar.setValue(0)
            self.downloadProgressBar.setEnabled(True)
        else:
            self.downloadProgressBar.setValue(100)
            self.downloadProgressBar.setEnabled(False)
            download_message = self.tr('Nothing to do locally.')
        self.downloadProgressFeedbackLabel.setText(download_message)

        self.stackedWidget.setCurrentWidget(self.progressPage)
