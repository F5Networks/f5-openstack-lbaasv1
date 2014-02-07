import netaddr


def icontrol_folder(method):
    """Decorator to put the right folder on iControl object."""
    def wrapper(*args, **kwargs):
        instance = args[0]
        if ('name' in kwargs) and ('folder' in kwargs):
            kwargs['name'] = instance.bigip.set_folder(kwargs['name'],
                                                       kwargs['folder'])
        return method(*args, **kwargs)
    return wrapper


def domain_address(method):
    """Decorator to put the right route domain decoration an address."""
    def wrapper(*args, **kwargs):
        instance = args[0]
        if instance.bigip.route_domain_required:
            if 'folder' in kwargs:
                folder = kwargs['folder']
                for name in kwargs:
                    if name.find('netmask') > 0:
                        netaddr.IPAddress(kwargs[name])
                    if name.find('ip_address') > 0:
                        if kwargs[name]:
                            # validate IP address format or raise exception
                            netaddr.IPAddress(kwargs[name])
                            # add the route domain to address by folder
                            if not str(kwargs[name]).find('%'):
                                rid = instance.bigip.get_domain_index(folder)
                                # Don't decorate /Common
                                if rid > 0:
                                    kwargs[name] = \
                                        kwargs[name] + "%" + str(rid)
        return method(*args, **kwargs)
    return wrapper
