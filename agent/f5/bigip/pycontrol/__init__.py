##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

import re
import suds
from xml.sax import SAXParseException

# Project info


class F5Error(Exception):
    def __init__(self, e):
        self.exception = e
        self.msg = str(e)

        if isinstance(e, suds.WebFault):
            try:
                parts = e.fault.faultstring.split('\n')
                e_source = parts[0].replace("Exception caught in ", "")
                e_type = parts[1].replace("Exception: ", "")
                e_msg = re.sub("\serror_string\s*:\s*", "", parts[4])
                self.msg = "%s: %s" % (e_type, e_msg)
            except IndexError:
                self.msg = e.fault.faultstring
        if isinstance(e, SAXParseException):
            self.msg = "Unexpected server response. %s" % e.message

    def __str__(self):
        return self.msg
