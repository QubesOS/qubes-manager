# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2024 Marta Marczykowska-Górecka
#                                       <marmarta@invisiblethingslab.com>
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

import unittest
from unittest import mock

from PyQt6 import QtGui  # pylint: disable=import-error
from qubesmanager import utils


class TestPathFromVM(unittest.TestCase):
    def test_00_accepts_ascii_path(self):
        vm = mock.Mock()
        vm.run_service_for_stdio.return_value = (
            b"/home/user/backup-file_01.iso\n",
            None,
        )

        path = utils.get_path_from_vm(vm, "qubes.SelectFile")

        self.assertEqual(path, "/home/user/backup-file_01.iso")

    def test_01_rejects_non_ascii_path(self):
        vm = mock.Mock()
        vm.run_service_for_stdio.return_value = (
            "zażółć.pdf\n".encode("utf-8"),
            None,
        )

        with self.assertRaises(ValueError) as exc:
            utils.get_path_from_vm(vm, "qubes.SelectFile")

        self.assertIn("ASCII", str(exc.exception))

    def test_02_rejects_control_character(self):
        vm = mock.Mock()
        vm.run_service_for_stdio.return_value = (
            b"/home/user/bad\tname.pdf\n",
            None,
        )

        with self.assertRaises(ValueError) as exc:
            utils.get_path_from_vm(vm, "qubes.SelectFile")

        self.assertEqual(
            str(exc.exception), utils.get_path_chars_message()
        )


class TestCaseQImage(unittest.TestCase):
    def setUp(self):
        self.rgba = (
            b"\x00\x00\x00\xff"
            b"\xff\x00\x00\xff"
            b"\x00\xff\x00\xff"
            b"\x00\x00\x00\xff"
        )
        self.width = 2
        self.height = 2

    def test_00_empty_image(self):
        empty_image = QtGui.QImage()
        tinted_image = utils.tint_qimage(empty_image, "0x0000ff")
        self.assertIsInstance(
            tinted_image,
            QtGui.QImage,
            "Tint of empty QImage failed",
        )

    def test_01_tint(self):
        source = QtGui.QImage(
            self.rgba,
            self.width,
            self.height,
            QtGui.QImage.Format.Format_RGBA8888,
        )
        tinted_image = utils.tint_qimage(source, "0x0000ff")
        self.assertIsInstance(
            tinted_image,
            QtGui.QImage,
            "Tinting of a 2x2 RGBA QImage did not return a QImage",
        )
        internal_data = tinted_image.constBits()
        internal_data.setsize(self.width * self.height * 4)
        raw_data = bytes(internal_data)
        self.assertEqual(
            raw_data,
            b"\x00\x00\x3f\xff"
            b"\x00\x00\xff\xff"
            b"\x00\x00\xff\xff"
            b"\x00\x00\x3f\xff",
            "Tinting of refrence image returned wrong results",
        )


if __name__ == "__main__":
    unittest.main()
