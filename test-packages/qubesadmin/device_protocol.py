### mock qubesadmin.devices module

class DeviceAssignment(object):

    @classmethod
    def new(
        cls,
        backend_domain,
        port_id: str,
        devclass: str,
        device_id: Optional[str] = None,
        *,
        frontend_domain = None,
        options=None,
        mode = "manual",
    ) -> "DeviceAssignment":
        pass
