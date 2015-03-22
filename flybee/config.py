import os, sys
import argparse
import textwrap
import six
import inspect
import pwd
import grp

from flybee import __version_info__, __software_name__


setting_classes = []


def make_settings(ignores=()):
    settings = {}
    for SettingClass in setting_classes:
        if SettingClass.name not in ignores:
            settings[SettingClass.name] = SettingClass().copy()
    return settings


class Config(object):
    def __init__(self, usage=None, prog=None):
        self.settings = make_settings()
        self.usage = usage
        self.prog = prog or os.path.basename(sys.argv[0])

    def parser(self):
        parser = argparse.ArgumentParser(prog=self.prog, usage=self.usage,
                                         formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        parser.add_argument('-v', '--version', action='version', default=argparse.SUPPRESS,
                            version='%(prog)s (version ' + __version_info__ + ')\n',
                            help='show the %(prog) version and exit')
        parser.add_argument('args', nargs='*', help=argparse.SUPPRESS)



class SettingMeta(type):
    def __new__(mcs, name, bases, cls_dict):
        super_new = super(SettingMeta, mcs).__new__
        if not filter(lambda b: isinstance(b, SettingMeta), bases):
            return super_new(mcs, name, bases, cls_dict)

        cls_dict['order'] = len(setting_classes)

        new_class = super_new(mcs, name, bases, cls_dict)
        new_class.fmt_desc(cls_dict.get('desc', ''))
        setting_classes.append(new_class)
        return new_class

    def fmt_desc(cls, desc):
        desc = textwrap.dedent(desc).strip()
        cls.desc = desc
        cls.short = desc.splitlines()[0]


class Setting(object):
    __metaclass__ = SettingMeta

    name = None
    value = None
    section = None
    cli = None
    validator = None

    action = None
    type = None
    nargs = None
    const = None
    metavar = None
    default = None
    short = None
    desc = None

    def __init__(self):
        if self.default is not None:
            self.set(self.default)

    def add_option(self, parser):
        if not self.cli:
            return

        kwargs = {
            'dest': self.name,
            'action': self.action or 'store',
            'default': None,
            'help': self.short
        }

        if self.action == 'store':
            kwargs['type'] = self.type or str

        if self.metavar is not None:
            kwargs['metavar'] = self.metavar

        if self.nargs is not None:
            kwargs['nargs'] = self.nargs

        if self.const is not None:
            kwargs['const'] = self.const

        parser.add_argument(*tuple(self.cli), **kwargs)

    def get(self):
        return self.value

    def set(self, value):
        self.value = self.validator(value)


def validate_bool(val):
    if isinstance(val, bool):
        return val
    if val in (0, 1):
        return bool(val)
    if not isinstance(val, six.string_types):
        raise TypeError('invalid boolean: %s' % val)
    if val.lower().strip() == 'true':
        return True
    elif val.lower().strip() == 'false':
        return False
    else:
        raise ValueError('invalid boolean: %s' % val)


def validate_dict(val):
    if not isinstance(val, dict):
        raise TypeError('invalid dictionary: %s ' % val)
    return val


def validate_positive_int(val):
    if not isinstance(val, six.integer_types):
        val = int(val, 0)
    else:
        val = int(val)
    if val < 0:
        raise ValueError('not a positive integer: %s' % val)
    return val


def validate_string(val):
    if val is None:
        return None
    if not isinstance(val, six.string_types):
        raise TypeError('not a string: %s' % val)
    return val.strip()


def validate_string_list(val):
    if not val:
        return []

    if isinstance(val, six.string_types):
        return [v.strip() for v in val.split(',') if v]

    return [validate_string(v) for v in val]


def validate_class(val):
    if inspect.isfunction(val) or inspect.ismethod(val):
        val = val()
    if inspect.isclass(val):
        return val
    return validate_string(val)


def validate_callable(arity=None):
    """
    :param arity: number of explicit argument names
    :return: validate function that checks a specified callable
    """
    def _validate_callable(val):
        if isinstance(val, six.string_types):
            try:
                mod_name, obj_name = val.rsplit('.', 1)
            except ValueError:
                raise TypeError('"%s" is not an import string in the format: module[.submodules...].object' % val)
            mod = __import__(mod_name, fromlist=[obj_name])
            val = getattr(mod, obj_name)
        if not six.callable(val):
            raise TypeError('not a six.callable: %s' % val)
        if arity is not None and arity != len(inspect.getargspec(val)[0]):
            raise TypeError('must have an arity of: %s' % arity)
        return val
    return _validate_callable


def validate_user(val):
    if val is None:
        return os.geteuid()
    if isinstance(val, int):
        return val
    elif val.isdigit():
        return int(val)
    else:
        try:
            return pwd.getpwnam(val).pw_uid
        except KeyError:
            raise ValueError('no such user: %s' % val)


def validate_group(val):
    if val is None:
        return os.getegid()
    if isinstance(val, int):
        return val
    elif val.isdigit():
        return int(val)
    else:
        try:
            return grp.getgrnam(val).gr_gid
        except KeyError:
            raise ValueError('no such group: %s' % val)


def validate_post_request(val):
    val = validate_callable()(val)

    largs = len(inspect.getargspec(val)[0])
    if largs == 4:
        return val
    elif largs == 3:
        return lambda worker, req, env, _r: val(worker, req, env)
    elif largs == 2:
        return lambda worker, req, _e, _r: val(worker, req)
    else:
        raise TypeError('must have an arity of 4')


def validate_path(val):
    if val is None:
        return None

    val = validate_string(val)

    path = os.path.abspath(os.path.normpath(val))

    if not os.path.exists(path):
        raise ValueError('%r not found' % val)

    return path


def validate_hostport(val):
    val = validate_string(val)
    if val is None:
        return None
    host, port = val.split(':')
    return host, int(port)
