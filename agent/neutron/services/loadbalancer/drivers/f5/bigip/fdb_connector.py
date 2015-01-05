""" Classes and functions for interfacing with an external
    L2 forwarding database """


class FDBConnector(object):
    """ Abstract base class for interfacing with an
        external forwarding database """

    def __init__(self, conf):
        self.conf = conf

    def notify_vtep_added(self, network, vtep_ip_address):
        """ A client calls this when it has a local VTEP ip address
            that needs to be advertised into the fdb.
        """
        pass

    def notify_vtep_removed(self, network, vtep_ip_address):
        """ A client calls this when it has a local VTEP ip address
            that needs to be removed from the fdb.
        """
        pass

    def advertise_tunnel_ips(self, tunnel_ips):
        """ A client calls this periodically to advertise
            local VTEP ip addresses.
        """
        pass
