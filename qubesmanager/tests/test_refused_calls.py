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

from unittest import mock

import pytest
from .. import settings as vm_settings


@pytest.fixture
def settings_for(qapp):
    def make(app, name="test-red", page="basic"):
        with mock.patch("subprocess.check_output", return_value=b""):
            for qube in (name, "dom0"):
                app.expected_calls[
                    (qube, "admin.vm.feature.Get", "preload-dispvm-max", None)
                ] = b"0\x00"
            app.expected_calls[(name, "admin.vm.notes.Get", None, None)] = b"0\x00"
            return vm_settings.VMSettingsWindow(name, page, qapp, app)

    return make


@mock.patch("PyQt6.QtWidgets.QMessageBox.warning")
def test_refused_kernels(warning, settings_for, test_qubes_app):
    app = test_qubes_app
    app.expected_calls[("dom0", "admin.pool.volume.List", "linux-kernel", None)] = b""
    dialog = settings_for(app)
    assert not dialog.kernel.isEnabled()
    assert not dialog.bootmode.isEnabled()
    with mock.patch("subprocess.check_output", return_value=b""):
        dialog.apply()
    warning.assert_not_called()
    assert not [call for call in app.actual_calls if call[1] == "admin.vm.property.Set"]


def test_refused_notes(settings_for, test_qubes_app):
    app = test_qubes_app
    dialog = settings_for(app)
    dialog.notes.setPlainText("new")
    app.expected_calls[("test-red", "admin.vm.notes.Set", None, b"new")] = b""
    errors = dialog.__save_changes__()
    assert errors[0] == "Notes tab:"
    assert "TypeError" not in "".join(errors)
