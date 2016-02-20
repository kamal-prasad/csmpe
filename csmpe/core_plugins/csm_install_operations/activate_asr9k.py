# =============================================================================
#
# Copyright (c) 2016, Cisco Systems
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


from asr9k_package_lib import SoftwarePackage
from csmpe.plugins import CSMPlugin
from install import install_activate_deactivate, get_package


class Plugin(CSMPlugin):
    """This plugin Activates packages on the device."""
    name = "Install Activate Plugin"
    platforms = {'ASR9K'}
    phases = {'Activate'}

    def get_tobe_activated_pkg_list(self):
        """
        Produces a list of packaged to be deactivated
        """
        packages = self.ctx.software_packages

        pkgs = SoftwarePackage.from_package_list(packages)
        installed_inact = SoftwarePackage.from_show_cmd(self.ctx.send("admin show install inactive summary"))
        installed_act = SoftwarePackage.from_show_cmd(self.ctx.send("admin show install active summary"))

        # Packages to activate but not already active
        packages_to_activate = pkgs - installed_act

        if packages_to_activate:
            packages_to_activate = pkgs & installed_inact  # packages to be deactivated and installed active packages
            if not packages_to_activate:
                to_deactivate = " ".join(map(str, pkgs))

                state_of_packages = "\nTo deactivate :{} \nInactive: {} \nActive: {}".format(
                    to_deactivate, installed_inact, installed_act
                )
                self.ctx.info(state_of_packages)
                self.ctx.error('To be deactivated packages not in inactive packages list.')
                return None
            else:
                return " ".join(map(str, packages_to_activate))

    def run(self):
        """
        Performs install activate operation
        """
        operation_id = None
        if hasattr(self.ctx, 'operation_id'):
            self.ctx.log("Using the operation ID: {}".format(self.ctx.operation_id))
            operation_id = self.ctx.operation_id

        if operation_id is None or operation_id == -1:
            tobe_activated = self.get_tobe_activated_pkg_list()
            if not tobe_activated:
                self.ctx.info("Nothing to be activated.")
                return True

        if operation_id is not None and operation_id != -1:
            cmd = 'admin install activate id {} prompt-level none async'.format(operation_id)
        else:
            cmd = 'admin install activate {} prompt-level none async'.format(tobe_activated)

        self.ctx.info("Activate package(s) pending")
        self.ctx.post_status("Activate Package(s) Pending")
        install_activate_deactivate(self.ctx, cmd)
        get_package(self.ctx)
        self.ctx.info("Activate package(s) done")
