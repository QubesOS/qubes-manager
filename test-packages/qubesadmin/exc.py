# SPDX-FileCopyrightText: 2015 Michael Carbone, <michael@qubes-os.org> et al.
#
# SPDX-License-Identifier: GPL-2.0-only



### mock qubesadmin.exc module
# pylint: disable=unused-variable


class QubesException(BaseException):
    pass


class QubesVMNotFoundError(BaseException):
    pass


class QubesVMNotStartedError(BaseException):
    pass


class QubesPropertyAccessError(BaseException):
    pass


class QubesDaemonAccessError(BaseException):
    pass


class QubesNoSuchPropertyError(BaseException):
    pass


class QubesDaemonNoResponseError(BaseException):
    pass


class BackupCancelledError(BaseException):
    pass


class BackupAlreadyRunningError(BaseException):
    pass


class QubesDaemonCommunicationError(BaseException):
    pass

class QubesValueError(BaseException):
    pass
