import logging
import urllib2

LOG = logging.getLogger(__name__)


class BigIQ(object):
    """Represents a single BIG-IQ"""

    def __init__(self, hostname, username, password):
        """Creates an instance of a BIG-IQ

        :param string hostname: The hostname of the BIG-IQ
        :param string username: The Administrator user name
        :param string password: The Administrator password
        """

        self.hostname = hostname
        self.username = username
        self.password = password

        # Create the basic auth handler for all requests to the BIG-IQ
        passMgr = urllib2.HTTPPasswordMgr()
        passMgr.add_password('REST Framework', self.hostname,
                             self.username, self.password)

        # Create the handler for all authentication requests
        authHandler = urllib2.HTTPBasicAuthHandler(passMgr)

        # Create and install the URL opener as the default one for all requests
        urllib2.install_opener(urllib2.build_opener(authHandler))

        # If we are able to successfully query the echo worker
        # we consider ourselves connected
        request = urllib2.Request('https://' + hostname + '/mgmt/shared/echo')
        response = urllib2.urlopen(request)

        # requests lib

        # The '_' looks to have a global def of gettext.gettext(message)
        # gettext is used for internationalization and localization
        LOG.debug(_('Echo worker response: %s' % response.read()))
