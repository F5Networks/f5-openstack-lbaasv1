import netaddr
import os

OBJ_PREFIX = 'uuid_'


def icontrol_folder(method):
    """Decorator to put the right folder on iControl object."""
    def wrapper(*args, **kwargs):
        instance = args[0]
        if 'folder' in kwargs:
            kwargs['folder'] = os.path.basename(kwargs['folder'])
            if not kwargs['folder'] == 'Common':
                if not kwargs['folder'].startswith(OBJ_PREFIX):
                    kwargs['folder'] = OBJ_PREFIX + kwargs['folder']
            if ('name' in kwargs):
                if kwargs['name'].startswith('/Common/'):
                    kwargs['name'] = os.path.basename(kwargs['name'])
                    if not kwargs['name'].startswith(OBJ_PREFIX):
                        kwargs['name'] = OBJ_PREFIX + kwargs['name']
                    kwargs['name'] = '/Common/' + kwargs['name']
                else:
                    kwargs['name'] = os.path.basename(kwargs['name'])
                    if not kwargs['name'].startswith(OBJ_PREFIX):
                        kwargs['name'] = OBJ_PREFIX + kwargs['name']
                    kwargs['name'] = instance.bigip.set_folder(kwargs['name'],
                                                           kwargs['folder'])
            for name in kwargs:
                if name.find('_name') > 0:
                    if kwargs[name].startswith('/Common/'):
                        kwargs[name] = os.path.basename(kwargs[name])
                        if not kwargs[name].startswith(OBJ_PREFIX):
                            kwargs[name] = OBJ_PREFIX + kwargs[name]
                        kwargs[name] = '/Common/' + kwargs[name]
                    else:
                        kwargs[name] = os.path.basename(kwargs[name])
                        if not kwargs[name].startswith(OBJ_PREFIX):
                            kwargs[name] = OBJ_PREFIX + kwargs[name]
                        kwargs[name] = instance.bigip.set_folder(kwargs[name],
                                                             kwargs['folder'])
        return method(*args, **kwargs)
    return wrapper


def domain_address(method):
    """Decorator to put the right route domain decoration an address."""
    def wrapper(*args, **kwargs):
        instance = args[0]
        folder = 'Common'
        if 'folder' in kwargs:
            folder = os.path.basename(kwargs['folder'])
            if not folder == 'Common':
                if not folder.startswith(OBJ_PREFIX):
                    folder = OBJ_PREFIX + folder
        for name in kwargs:
            if name.find('mask') > -1:
                if kwargs[name]:
                    netaddr.IPAddress(kwargs[name])
            if name.find('ip_address') > -1:
                if kwargs[name]:
                    if instance.bigip.route_domain_required:
                        decorator_index = kwargs[name].find('%')
                        if decorator_index < 0:
                            netaddr.IPAddress(kwargs[name])
                            rid = instance.bigip.get_domain_index(folder)
                            if rid > 0:
                                kwargs[name] = kwargs[name] + "%" + str(rid)
                        else:
                            netaddr.IPAddress(kwargs[name][:decorator_index])
                    else:
                        netaddr.IPAddress(kwargs[name])
        return method(*args, **kwargs)
    return wrapper
