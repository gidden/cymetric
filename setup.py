#!/usr/bin/env python
"""Welcome to cymetric's setup.py script. This is a little non-standard because pyne
is a multilanguage project.  Still, this script follows a predicatable ordering:

1. Parse command line arguments
2. Call cmake from the 'build' directory
3. Call make from the 'build' directory
4. Use distuitls/setuptools from the 'build' directory

This gives us the best of both worlds. Compiled code is installed with cmake/make
and Cython/Python code is installed with normal Python tools. The only trick here is
how the various command line arguments are handed off to the three sub-processes.

To accomplish this we use argparser groups to group command line arguments based on
whether they go to:

1. the setup() function,
2. cmake,
3. make, or
4. other - typically used for args that apply to multiple other groups or
   modify the environment in some way.

To add a new command line argument, first add it to the appropriate group in the
``parse_args()`` function.  Then, modify the logic in the cooresponding
``parse_setup()``, ``parse_cmake()``, ``parse_make()``, or ``parse_others()``
functions to consume your new command line argument.  It is OK for more than
one of the parser functions to consume the argument. Where appropriate,
ensure the that argument is appended to the argument list that is returned by these
functions.
"""
from __future__ import print_function

import os
import sys
import imp
import argparse
import platform
import warnings
import subprocess
from glob import glob
from distutils import core, dir_util

import genapi

VERSION = '0.0-dev'
IS_NT = os.name == 'nt'

CMAKE_BUILD_TYPES = {
    'none': 'None',
    'debug': 'Debug',
    'release': 'Release',
    'relwithdebinfo': 'RelWithDebInfo',
    'minsizerel': 'MinSizeRel',
    }

def safe_call(cmd, shell=False, *args, **kwargs):
    """Checks that a command successfully runs with/without shell=True. 
    Returns the process return code
    """
    try:
        rtn = subprocess.call(cmd, shell=False, *args, **kwargs)
    except (subprocess.CalledProcessError, OSError):
        cmd = ' '.join(cmd)
        rtn = subprocess.check_call(cmd, shell=True, *args, **kwargs)
    return rtn     


def parse_setup(ns):
    a = [sys.argv[0], ns.cmd]
    if ns.user:
        a.append('--user')
    if ns.prefix is not None:
        a.append('--prefix=' + ns.prefix)
    if ns.egg_base is not None:
        local_path = os.path.dirname(os.path.abspath(sys.argv[0]))
        a.append('--egg-base=' + os.path.join(local_path, ns.egg_base))
    if ns.cmd == 'clean':
        if os.path.exists('build'):
            dir_util.remove_tree('build')
        print('build directory cleaned ... exiting')
        sys.exit()
    if ns.clean:
        if os.path.exists('build'):
            dir_util.remove_tree('build')
    return a


def parse_cmake(ns):
    a = []
    if ns.D is not None:
        a += ['-D' + x for x in ns.D]
    if ns.build_type is not None:
        a.append('-DCMAKE_BUILD_TYPE=' + CMAKE_BUILD_TYPES[ns.build_type.lower()])
    if ns.prefix is not None:
        a.append('-DCMAKE_INSTALL_PREFIX=' + ns.prefix)
    return a


def parse_make(ns):
    a = []
    if ns.j is not None:
        a.append('-j' + ns.j)
    return a


def parse_others(ns):
    if ns.hdf5 is not None:
        os.environ['HDF5_ROOT'] = ns.hdf5
    if ns.moab is not None:
        os.environ['MOAB_ROOT'] = ns.moab


def parse_args():
    argv = [a for a in sys.argv[1:] if a != '--']  # needed for backwards compat.
    parser = argparse.ArgumentParser()

    setup = parser.add_argument_group('setup', 'Group for normal setup.py arguments')
    setup.add_argument('cmd', help="command to send to normal setup, e.g. "
                       "install or build.")
    parser.add_argument('--clean', nargs='?', const=True, default=False)
    parser.add_argument('--user', nargs='?', const=True, default=False)
    parser.add_argument('--egg-base')

    cmake = parser.add_argument_group('cmake', 'Group for CMake arguments.')
    cmake.add_argument('-D', metavar='VAR', action='append',
                       help='Set enviornment variable.')
    cmake.add_argument('--build-type', metavar='BT',
                       help='Set build type via CMAKE_BUILD_TYPE, '
                            'e.g. Release or Debug.')

    make = parser.add_argument_group('make', 'Group for make arguments.')
    make.add_argument('-j', help='Degree of parallelism for build.')

    other = parser.add_argument_group('other', 'Group for miscellaneous arguments.')
    other.add_argument('--hdf5', help='Path to HDF5 root directory.')
    other.add_argument('--moab', help='Path to MOAB root directory.')
    other.add_argument('--prefix', help='Prefix for install location.')

    ns = parser.parse_args(argv)
    sys.argv = parse_setup(ns)
    cmake_args = parse_cmake(ns)
    make_args = parse_make(ns)
    parse_others(ns)

    return cmake_args, make_args


def setup():
    scripts = [os.path.join('scripts', f) for f in os.listdir('scripts')]
    scripts = [s for s in scripts if (os.name == 'nt' and s.endswith('.bat'))
                                     or (os.name != 'nt' and
                                         not s.endswith('.bat'))]
    packages = ['cymetric']
    pack_dir = {'cymetric': 'cymetric'}
    extpttn = ['*.dll', '*.so', '*.dylib', '*.pyd', '*.pyo']
    pack_data = {
        'lib': extpttn,
        'cymetric': ['*.pxd', 'include/*.h', 'include/*.pxi', 'include/*/*.h',
                     '*.inp', 'include/*/*/*.h', 'include/*/*/*/*.h', '*.json',
                     '_includes/*.txt', '_includes/*.pxd', '_includes/*/*',
                     '_includes/*/*/*'] + extpttn,
        }
    libs = set()
    for ext in extpttn:
        libs |= set(glob('src/' + ext))
    data_files = [
        ('lib', libs),
        ('include/cymetric', glob('../src/*.h')),
        ]
    setup_kwargs = {
        "name": "cymetric",
        "version": VERSION,
        "description": 'Cyclus Metric Calculator',
        "author": 'Cyclus Development Team',
        "author_email": 'cyclus-dev@googlegroups.com',
        "url": 'http://fuelcycle.org/',
        "packages": packages,
        "package_dir": pack_dir,
        "package_data": pack_data,
        "data_files": data_files,
        "scripts": scripts,
        }
    rtn = core.setup(**setup_kwargs)


def cmake_cli(cmake_args):
    if not IS_NT:
        rtn = safe_call(['which', 'cmake'])
        if rtn != 0:
            sys.exit('CMake is not installed, aborting build.')
    cmake_cmd = ['cmake', '..'] + cmake_args
    cmake_cmd += ['-DPYTHON_EXECUTABLE=' + sys.executable]
    if IS_NT:
        files_on_path = set()
        for p in os.environ['PATH'].split(';')[::-1]:
            if os.path.exists(p):
                files_on_path.update(os.listdir(p))
        if 'cl.exe' in files_on_path:
            pass
        elif 'sh.exe' in files_on_path:
            cmake_cmd += ['-G "MSYS Makefiles"']
        elif 'gcc.exe' in files_on_path:
            cmake_cmd += ['-G "MinGW Makefiles"']
        cmake_cmd = ' '.join(cmake_cmd)
    cmake_cmdstr = cmake_cmd if isinstance(cmake_cmd, str) else ' '.join(cmake_cmd)
    print("CMake command is\n", cmake_cmdstr, sep="")
    return cmake_cmd


def main_body(cmake_args, make_args):
    if not os.path.exists('build'):
        os.mkdir('build')
    print('Generating API Bindings...')
    genapi.main([])

    # cmake_cmd = cmake_cli(cmake_args)
    # rtn = safe_call(cmake_cmd, cwd='build')

    # rtn = safe_call(['make'] + make_args, cwd='build')

    # cwd = os.getcwd()
    # os.chdir('build')
    # setup()
    # os.chdir(cwd)


def final_message(success=True):
    if success:
        return
    msg = ("\n\nIf you are having issues building cymetric, please report your problem "
           "to cyclus-dev@googlegroups.com or look for help at http://fuelcycle.org\n\n"
           )
    print('\n' + '-'*20 + msg + '-'*20)


def main():
    success = False
    cmake_args, make_args = parse_args()
    try:
        main_body(cmake_args, make_args)
        success = True
    finally:
        final_message(success)
    # trick to get install path
    abspath = os.path.abspath
    joinpath = os.path.join
    cwd = abspath(os.getcwd())
    cympath = [p for p in sys.path if len(p) > 0 and cwd != abspath(p)]
    try:
        _, cympath, _ = imp.find_module('cymetric', cympath)
    except ImportError:
        pynepath = "${HOME}/.local/python2.7/site-packages"
    libpath = abspath(joinpath(cympath, '..', '..', '..'))
    binpath = abspath(joinpath(libpath, '..', 'bin'))
    msg = ("\nNOTE: If you have not done so already, please be sure that your PATH and "
           "LD_LIBRARY_PATH (or DYLD_FALLBACK_LIBRARY_PATH on Mac OSX) has been "
           "appropriately set to the install prefix of cymetric. For this install of "
           "cymetric you may add the following lines to your '~/.bashrc' file or "
           "equivalent:\n\n"
           "# Cymetric Environment Settings\n"
           'export PATH="{binpath}:${{PATH}}"\n'
           'export LD_LIBRARY_PATH="{libpath}:${{LD_LIBRARY_PATH}}"'
           ).format(binpath=binpath, libpath=libpath)

    print(msg, file=sys.stderr)


if __name__ == "__main__":
    main()
