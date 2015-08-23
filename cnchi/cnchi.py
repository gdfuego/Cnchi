#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  cnchi.py
#
#  Copyright © 2013-2015 Antergos
#
#  This file is part of Cnchi.
#
#  Cnchi is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  Cnchi is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  The following additional terms are in effect as per Section 7 of the license:
#
#  The preservation of all legal notices and author attributions in
#  the material or in the Appropriate Legal Notices displayed
#  by works containing it is required.
#
#  You should have received a copy of the GNU General Public License
#  along with Cnchi; If not, see <http://www.gnu.org/licenses/>.

""" Main Cnchi (Antergos Installer) module """

# Useful vars for gettext (translations)
APP_NAME = "cnchi"
LOCALE_DIR = "/usr/share/locale"

import os
import sys
import logging
import logging.handlers
import gettext
import locale
import uuid
import gi
import requests
import json
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, Gtk, GObject

import misc.misc as misc
import info
import updater

try:
    from bugsnag.handlers import BugsnagHandler
    import bugsnag
    BUGSNAG_AVAILABLE = True
except ImportError:
    BUGSNAG_AVAILABLE = False

# Command line options
cmd_line = None

# At least this GTK version is needed
GTK_VERSION_NEEDED = "3.16.0"


# TODO: Find a proper place for these classes
class Singleton(logging.Filter):
    """

    :param args:
    :param kwargs:
    """

    def __init__(self, *args, **kwargs):
        super(Singleton, self).__init__()
        globals()[self.__class__.__name__] = self

    def __call__(self):
        return self


class ContextFilter(Singleton):
    id = None
    install = None

    def __init__(self):
        super().__init__()
        if not self.install:
            info = self.get_install_id()
            try:
                self.id = info['ip']
                self.install = info['id']
            except TypeError:
                pass

    def filter(self, record):
        uid = str(uuid.uuid1()).split("-")
        record.uuid = uid[3] + "-" + uid[1] + "-" + uid[2] + "-" + uid[4]
        record.id = self.id
        record.install = self.install
        return True

    @staticmethod
    def get_install_id():
        url = 'http://build.antergos.com/hook?cnchi=bKjW8GU48cQw'
        install_info = None
        try:
            r = requests.get(url)
            install_info = json.loads(r.json())
            logging.debug(install_info)
        except ValueError as err:
            logging.warning(err)

        return install_info


class CnchiApp(Gtk.Application):
    """ Main Cnchi App class """

    def __init__(self):
        """ Constructor. Call base class """
        Gtk.Application.__init__(self,
                                 application_id="com.antergos.cnchi",
                                 flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        """ Override the 'activate' signal of GLib.Application. """
        try:
            import main_window
        except ImportError as err:
            msg = _("Can't create Cnchi main window: {0}").format(err)
            logging.error(msg)
            sys.exit(1)

        window = main_window.MainWindow(self, cmd_line)
        self.add_window(window)
        window.show()

        # This is unnecessary as show_all is called in MainWindow
        # window.show_all()

        # def do_startup(self):
        # """ Override the 'startup' signal of GLib.Application. """
        # Gtk.Application.do_startup(self)

        # Application main menu (we don't need one atm)
        # Leaving this here for future reference
        # menu = Gio.Menu()
        # menu.append("About", "win.about")
        # menu.append("Quit", "app.quit")
        # self.set_app_menu(menu)


def setup_logging():
    """ Configure our logger """
    logger = logging.getLogger()

    logger.handlers = []

    if cmd_line.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logger.setLevel(log_level)

    context_filter = ContextFilter()
    logger.addFilter(context_filter)

    # Log format
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] - %(filename)s : %(lineno)d : %(funcName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")

    # File logger
    try:
        file_handler = logging.FileHandler('/tmp/cnchi.log', mode='w')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except PermissionError as permission_error:
        print("Can't open /tmp/cnchi.log : ", permission_error)

    # Stdout logger
    if cmd_line.verbose:
        # Show log messages to stdout
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    if cmd_line.log_server:
        log_server = cmd_line.log_server

        if BUGSNAG_AVAILABLE and log_server == 'bugsnag':
            # Bugsnag logger
            bugsnag_api = get_bugsnag_api()
            if bugsnag_api:
                bugsnag.configure(
                    api_key=bugsnag_api,
                    app_version=info.CNCHI_VERSION,
                    project_root='/usr/share/cnchi/cnchi',
                    release_stage=info.CNCHI_RELEASE_STAGE)
                bugsnag_handler = BugsnagHandler(api_key=bugsnag_api,
                                                 extra_fields={'user': ['id', 'install']})
                bugsnag_handler.setLevel(logging.WARNING)
                bugsnag_handler.setFormatter(formatter)
                bugsnag_handler.addFilter(context_filter)
                logger.addHandler(bugsnag_handler)
                logging.info(_("Also sending Cnchi log messages to bugsnag server (using python-bugsnag)."))
            else:
                logging.warning(
                    "%s %s",
                    _("Cannot read the bugsnag api key."),
                    _("Logging to bugsnag is not possible."))
        else:
            # Socket logger
            socket_handler = logging.handlers.SocketHandler(
                log_server,
                logging.handlers.DEFAULT_TCP_LOGGING_PORT)
            socket_formatter = logging.Formatter(
                fmt="[%(uuid)s] [%(asctime)s] [%(module)s] %(levelname)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S")
            socket_handler.setFormatter(socket_formatter)
            logger.addHandler(socket_handler)

            # Also add uuid filter to requests logs
            logger_requests = logging.getLogger("requests.packages.urllib3.connectionpool")
            logger_requests.addFilter(context_filter)

            uid = str(uuid.uuid1()).split("-")
            myuid = uid[3] + "-" + uid[1] + "-" + uid[2] + "-" + uid[4]
            logging.info(_("Sending Cnchi logs to {0} with id '{1}'").format(log_server, myuid))


def get_bugsnag_api():
    config_path = '/etc/raven.conf'
    bugsnag_api = None
    if os.path.exists(config_path):
        with open(config_path) as bugsnag_conf:
            bugsnag_api = bugsnag_conf.readline().strip()
    return bugsnag_api


def check_gtk_version():
    """ Check GTK version """
    # Check desired GTK Version
    major_needed = int(GTK_VERSION_NEEDED.split(".")[0])
    minor_needed = int(GTK_VERSION_NEEDED.split(".")[1])
    micro_needed = int(GTK_VERSION_NEEDED.split(".")[2])

    # Check system GTK Version
    major = Gtk.get_major_version()
    minor = Gtk.get_minor_version()
    micro = Gtk.get_micro_version()

    # Cnchi will be called from our liveCD that already
    # has the latest GTK version. This is here just to
    # help testing Cnchi in our environment.
    wrong_gtk_version = False
    if major_needed > major:
        wrong_gtk_version = True
    if major_needed == major and minor_needed > minor:
        wrong_gtk_version = True
    if major_needed == major and minor_needed == minor and micro_needed > micro:
        wrong_gtk_version = True

    if wrong_gtk_version:
        text = "Detected GTK version {0}.{1}.{2} but version >= {3} is needed."
        text = text.format(major, minor, micro, GTK_VERSION_NEEDED)
        try:
            import show_message as show
            show.error(None, text)
        except ImportError as import_error:
            logging.info(text)
        return False
    else:
        logging.info("Using GTK v{0}.{1}.{2}".format(major, minor, micro))

    return True


def check_pyalpm_version():
    """ Checks python alpm binding and alpm library versions """
    try:
        import pyalpm

        txt = _("Using pyalpm v{0} as interface to libalpm v{1}")
        txt = txt.format(pyalpm.version(), pyalpm.alpmversion())
        logging.info(txt)
    except (NameError, ImportError) as err:
        logging.error(err)
        sys.exit(1)

    return True


def parse_options():
    """ argparse http://docs.python.org/3/howto/argparse.html """

    import argparse

    desc = _("Cnchi v{0} - Antergos Installer").format(info.CNCHI_VERSION)
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument(
        "-c", "--cache",
        help=_("Use pre-downloaded xz packages when possible"),
        nargs='?')
    parser.add_argument(
        "-d", "--debug",
        help=_("Sets Cnchi log level to 'debug'"),
        action="store_true")
    parser.add_argument(
        "-e", "--environment",
        help=_("Sets the Desktop Environment that will be installed"),
        nargs='?')
    parser.add_argument(
        "-f", "--force",
        help=_("Runs cnchi even if it detects that another instance is running"),
        action="store_true")
    parser.add_argument(
        "-i", "--disable-tryit",
        help=_("Disables first screen's 'try it' option"),
        action="store_true")
    parser.add_argument(
        "-l", "--library",
        help=_("Choose which library to use when downloading packages."
               " Possible options are 'requests' (default), 'urllib' and 'aria2'"),
        nargs='?')
    parser.add_argument(
        "-n", "--no-check",
        help=_("Makes checks optional in check screen"),
        action="store_true")
    parser.add_argument(
        "-p", "--packagelist",
        help=_("Install the packages referenced by a local xml instead of the default ones"),
        nargs='?')
    parser.add_argument(
        "-s", "--log-server",
        help=_("Choose to which log server send Cnchi logs."
               " Expects a hostname or an IP address"),
        nargs='?')
    parser.add_argument(
        "-t", "--testing",
        help=_("Do not perform any changes (useful for developers)"),
        action="store_true")
    parser.add_argument(
        "-u", "--update",
        help=_("Upgrade/downgrade Cnchi to the web version"),
        action="store_true")
    parser.add_argument(
        "--disable-update",
        help=_("Do not search for new Cnchi versions online"),
        action="store_true")
    parser.add_argument(
        "-v", "--verbose",
        help=_("Show logging messages to stdout"),
        action="store_true")
    parser.add_argument(
        "-z", "--z_hidden",
        help=_("Show options in development (for developers only, do not use this!)"),
        action="store_true")

    return parser.parse_args()


def threads_init():
    """
    For applications that wish to use Python threads to interact with the GNOME platform,
    GObject.threads_init() must be called prior to running or creating threads and starting
    main loops (see notes below for PyGObject 3.10 and greater). Generally, this should be done
    in the first stages of an applications main entry point or right after importing GObject.
    For multi-threaded GUI applications Gdk.threads_init() must also be called prior to running
    Gtk.main() or Gio/Gtk.Application.run().
    """
    minor = Gtk.get_minor_version()
    micro = Gtk.get_micro_version()

    if minor == 10 and micro < 2:
        # Unfortunately these versions of PyGObject suffer a bug
        # which require a workaround to get threading working properly.
        # Workaround: Force GIL creation
        import threading
        threading.Thread(target=lambda: None).start()

    # Since version 3.10.2, calling threads_init is no longer needed.
    # See: https://wiki.gnome.org/PyGObject/Threading
    if minor < 10 or (minor == 10 and micro < 2):
        GObject.threads_init()
        # Gdk.threads_init()


def update_cnchi():
    """ Runs updater function to update cnchi to the latest version if necessary """
    upd = updater.Updater(
        force_update=cmd_line.update,
        local_cnchi_version=info.CNCHI_VERSION)

    if upd.update():
        logging.info(_("Program updated! Restarting..."))
        misc.remove_temp_files()
        if cmd_line.update:
            # Remove -u and --update options from new call
            new_argv = []
            for argv in sys.argv:
                if argv != "-u" and argv != "--update":
                    new_argv.append(argv)
        else:
            new_argv = sys.argv

        # Do not try to update again now
        new_argv.append("--disable-update")

        # Run another instance of Cnchi (which will be the new version)
        with misc.raised_privileges():
            os.execl(sys.executable, *([sys.executable] + new_argv))
        sys.exit(0)


def setup_gettext():
    """ This allows to translate all py texts (not the glade ones) """

    gettext.textdomain(APP_NAME)
    gettext.bindtextdomain(APP_NAME, LOCALE_DIR)

    locale_code, encoding = locale.getdefaultlocale()
    lang = gettext.translation(APP_NAME, LOCALE_DIR, [locale_code], None, True)
    lang.install()


def check_for_files():
    """ Check for some necessary files. Cnchi can't run without them """
    paths = [
        "/usr/share/cnchi",
        "/usr/share/cnchi/ui",
        "/usr/share/cnchi/data"]

    for path in paths:
        if not os.path.exists(path):
            print(_("Cnchi files not found. Please, install Cnchi using pacman"))
            return False

    return True


def init_cnchi():
    """ This function initialises Cnchi """

    # Sets SIGTERM handler, so Cnchi can clean up before exiting
    # signal.signal(signal.SIGTERM, sigterm_handler)

    # Configures gettext to be able to translate messages, using _()
    setup_gettext()

    # Command line options
    global cmd_line
    cmd_line = parse_options()

    if cmd_line.force:
        misc.remove_temp_files()

    # Drop root privileges
    misc.drop_privileges()

    # Setup our logging framework
    setup_logging()

    # Check Cnchi is correctly installed
    if not check_for_files():
        sys.exit(1)

    # Check installed GTK version
    if not check_gtk_version():
        sys.exit(1)

    # Check installed pyalpm and libalpm versions
    if not check_pyalpm_version():
        sys.exit(1)

    # if not cmd_line.disable_update:
        # update_cnchi()

    # Init PyObject Threads
    threads_init()


if __name__ == '__main__':
    init_cnchi()

    # Create Gtk Application
    app = CnchiApp()
    exit_status = app.run(None)
    sys.exit(exit_status)
