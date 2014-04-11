

class MinorVersionValidateFailed(Exception):
    pass


class MajorVersionValidateFailed(Exception):
    pass


class BigIPDeviceLockAcquireFailed(Exception):
    pass


class BigIPClusterSyncFailure(Exception):
    pass


class BigIPClusterPeerAddFailure(Exception):
    pass


class UnknownMonitorType(Exception):
    pass


class MissingVTEPAddress(Exception):
    pass


class InvalidNetworkType(Exception):
    pass
