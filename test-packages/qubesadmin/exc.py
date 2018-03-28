### mock qubesadmin.exc module
# pylint: disable=unused-variable


class QubesException(BaseException):
    pass

class QubesVMNotStartedError(BaseException):
    pass