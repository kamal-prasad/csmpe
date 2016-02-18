# =============================================================================
# CSMPluginManager
#
# Copyright (c)  2016, Cisco Systems
# All rights reserved.
#
# # Author: Klaudiusz Staniek
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF
# THE POSSIBILITY OF SUCH DAMAGE.
# =============================================================================

import pkginfo
from stevedore.dispatch import DispatchExtensionManager


install_phases = ['Pre-Upgrade', 'Pre-Add', 'Add', 'Pre-Activate', 'Activate', 'Pre-Deactivate',
                  'Deactivate', 'Pre-Remove', 'Remove', 'Commit']

auto_pre_phases = ["Add", "Activate", "Deactivate"]


class CSMPluginManager(object):

    def __init__(self, ctx, invoke_on_load=True):
        self._ctx = ctx
        self._platform = ctx.family
        self._phase = ctx.phase
        self._name = None
        self._manager = DispatchExtensionManager(
            "csm.plugin",
            self._check_plugin,
            invoke_on_load=invoke_on_load,
            invoke_args=(ctx,),
            propagate_map_exceptions=True,
            on_load_failure_callback=self._on_load_failure,
        )
        self._build_plugin_list()

    def __getitem__(self, item):
        return self._manager.__getitem__(item)

    def _build_plugin_list(self):
        self.plugins = {}
        for ext in self._manager:
            self.plugins[ext.name] = {
                'package_name': ext.entry_point.dist.project_name,
                'name': ext.plugin.name,
                'description': ext.plugin.__doc__,
                'phases': ext.plugin.phases,
                'platforms': ext.plugin.platforms,
            }

    def _filter_func(self, ext, *args, **kwargs):
        if self._platform and self._platform not in ext.plugin.platforms:
            return False
        if self._phase and self._phase not in ext.plugin.phases:
            return False
        if self._name and ext.plugin.name not in self._name:
            return False

        self._ctx.current_plugin = None
        self._ctx.info("Dispatching: '{}'".format(ext.plugin.name))
        self._ctx.current_plugin = ext.plugin.name
        return True

    def _on_load_failure(self, manager, entry_point, exc):
        self._ctx.warning("Plugin load error: {}".format(entry_point))
        self._ctx.warning("Exception: {}".format(exc))

    def _check_plugin(self, ext, *args, **kwargs):
        attributes = ['name', 'phases', 'platforms']
        plugin = ext.plugin
        for attribute in attributes:
            if not hasattr(plugin, attribute):
                self._ctx.warning("Attribute '{}' missing in plugin class".format(attribute))
        return True

    def _find_plugin_packages(self):
        packages = set()
        for ext in self._manager:
            dist = ext.entry_point.dist
            print(dist.__dict__)
        return list(packages)

    def get_package_metadata(self, name):
        try:
            meta = pkginfo.Installed(name)
        except ValueError as e:
            print(e)
            return None
        return meta

    def get_package_names(self):
        return self.get_package_metadata().keys()

    def dispatch(self, func):
        self._ctx.connect()

        results = []
        if self._phase in auto_pre_phases:
            current_phase = self._phase
            phase = "Pre-{}".format(self._phase)
            self.set_phase_filter(phase)
            results = self._manager.map_method(self._filter_func, func)
            self._ctx.current_plugin = None
            self.set_phase_filter(current_phase)

        results += self._manager.map_method(self._filter_func, func)
        self._ctx.current_plugin = None

        return results

    def set_platform_filter(self, platform):
        self._platform = platform

    def set_phase_filter(self, phase):
        self._ctx.info("Phase: {}".format(phase))
        self._phase = phase

    def set_name_filter(self, name):
        if isinstance(name, str) or isinstance(name, unicode):
            self._name = set((name,))
        elif isinstance(name, list):
            self._name = set(name)
        elif isinstance(name, set):
            self._name = name
        else:
            self._name = None
