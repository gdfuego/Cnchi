#!/usr/bin/env python
#  -*- coding: utf-8 -*-
#
#  _html_page.py
#
#  Copyright © 2016 Antergos
#
#  This file is part of The Antergos Build Server, (AntBS).
#
#  AntBS is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  AntBS is distributed in the hope that it will be useful,
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
#  along with AntBS; If not, see <http://www.gnu.org/licenses/>.

from gettext import gettext

from jinja2 import Environment, FileSystemLoader

from ui.base_widgets import SharedData, Page, Gtk

env = Environment(loader=FileSystemLoader(os.path.join(CURRENT_DIR, 'templates')))
env.globals['_'] = gettext


class HTMLPage(Page):
    """
    Base class for HTML UI pages.

    Class Attributes:
        _tpl (SharedData): Descriptor object that handles access to Jinja2 template environment.
        Also see `Page.__doc__`

    """

    _tpl = SharedData('_tpl')

    def __init__(self, name='HTMLPage', tpl_engine='jinja', *args, **kwargs):
        """
        Attributes:
            _tpl (Environment): The Jinja2 template environment.
            Also see `Page.__doc__`.

        Args:
            name (str): A name for this widget.

        """

        super().__init__(name=name, tpl_engine=tpl_engine, *args, **kwargs)

        if self._tpl is None:
            self._tpl = env

    def emit_js(self, name, *args):
        """ See `Controller.emit_js.__doc__` """
        self._controller.emit_js(name, *args)

    def prepare(self):
        """ This must be implemented by subclasses """
        raise NotImplementedError

    def render_template(self, name, tpl_vars):
        return self._tpl.render_template(name, tpl_vars)

    def store_values(self):
        """ This must be implemented by subclasses """
        raise NotImplementedError
