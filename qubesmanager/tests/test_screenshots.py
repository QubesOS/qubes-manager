# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2026 Frédéric Pierret <frederic@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

import os

import pytest
from PyQt6 import QtWidgets

from qubesmanager.tests.test_vm_settings import check_errors, settings_fixture

SCREENSHOT_DIR = os.environ.get("SCREENSHOT_DIR")


@pytest.mark.skipif(not SCREENSHOT_DIR, reason="SCREENSHOT_DIR is not set")
@check_errors
@pytest.mark.parametrize("settings_fixture", ["test-vm-set"], indirect=True)
def test_settings_screenshots(settings_fixture):
    assert SCREENSHOT_DIR
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    settings_window, _, _ = settings_fixture
    settings_window.show()

    tabs = settings_window.tabWidget
    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        QtWidgets.QApplication.processEvents()
        name = tabs.widget(index).objectName().removesuffix("_tab")
        path = os.path.join(SCREENSHOT_DIR, f"qube-settings-{name}.png")
        assert settings_window.grab().save(path)
