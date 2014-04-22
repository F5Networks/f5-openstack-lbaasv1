##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
# 
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
################################################################################

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
