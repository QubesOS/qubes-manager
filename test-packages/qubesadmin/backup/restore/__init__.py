# SPDX-FileCopyrightText: 2015 Michael Carbone, <michael@qubes-os.org> et al.
#
# SPDX-License-Identifier: GPL-2.0-only


class BackupRestore(object):

    options = object()
    canceled = None

    def get_restore_info(self, *args):
        pass

    def restore_do(self, *args):
        pass

    def get_restore_info(self, *args):
        pass

    def restore_info_verify(self, *args):
        return 'test'

    def get_restore_summary(self, *args):
        return 'test'
