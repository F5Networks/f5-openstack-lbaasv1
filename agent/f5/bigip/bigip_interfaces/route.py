from netaddr import ip

# Networking - Routing


class Route(object):
    def __init__(self, bigip):
        self.bigip = bigip
        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interface('Networking.RouteTableV2',
                                          'Networking.RouteDomainV2')
        # iControl helper objects
        self.net_route = self.bigip.icontrol.Networking.RouteTableV2

    def create(self, name, dest_addr, dest_mask, gw):
        if not self.exists(name) and ip(dest_addr) and ip(gw):
            dest = self.net_route.typefactory.create(
                    'Networking.RouteTableV2.RouteDestination')
            dest.address = dest_addr
            dest.netmask = dest_mask
            attr = self.net_route.typefactory.create(
                    'Networking.RouteTableV2.RouteAttribute')
            attr.gateway = gw
            self.net_route2.create_static_route([name], [dest], [attr])

    def delete(self, route_name):
        if self.exists(route_name):
            self.net_route2.delete_static_route([route_name])

    def exists(self, route_name):
        #if route_name in map(os.path.basename,
        #              self.net_route2.get_static_route_list()):
        if route_name in self.net_route2.get_static_route_list():
            return True
