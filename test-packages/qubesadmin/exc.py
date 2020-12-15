### mock qubesadmin.exc module
# pylint: disable=unused-variable


class QubesException(BaseException):
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
