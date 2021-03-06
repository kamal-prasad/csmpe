# =============================================================================
#
# Copyright (c) 2016, Cisco Systems
# All rights reserved.
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

from csmpe.plugins import CSMPlugin
from install import observe_install_add_remove
from install import check_ncs6k_release
from csmpe.core_plugins.csm_get_inventory.exr.plugin import get_package, get_inventory


class Plugin(CSMPlugin):
    """This plugin adds packages from repository to the device."""
    name = "Install Add Plugin"
    platforms = {'ASR9K', 'NCS1K', 'NCS5K', 'NCS5500', 'NCS6K'}
    phases = {'Add'}
    os = {'eXR'}

    def install_add(self, server_repository_url, s_packages, has_tar=False):
        """
        Success Condition:
        ADD for tftp/local:
        install add source tftp://223.255.254.254/auto/tftpboot-users/alextang/ ncs6k-mpls.pkg-6.1.0.07I.DT_IMAGE
        May 24 18:54:12 Install operation will continue in the background
        RP/0/RP0/CPU0:Deploy#May 24 18:54:30 Install operation 12 finished successfully

        ADD for sftp/ftp
        RP/0/RP0/CPU0:Deploy-2#install add source sftp://terastream@172.20.168.195/echami ncs6k-li.pkg-5.2.5-V2

        Jun 20 18:58:08 Install operation 38 started by root:
         install add source sftp://terastream:cisco@172.20.168.195/echami ncs6k-li.pkg-5.2.5-V2
        password:Jun 20 18:58:24 Install operation will continue in the background
        RP/0/RP0/CPU0:Deploy-2#
        """
        if server_repository_url.startswith("sftp://") or server_repository_url.startswith("ftp://"):

            if server_repository_url.count(":") != 2 or server_repository_url.count("@") != 1:
                self.ctx.error("The server repository url provided - {} - ".format(server_repository_url) +
                               "does not conform to <protocol>://<username>:<password>@<ip>/<directory>." +
                               "Special characters ':' and '@' are not allowed in username, password or directory.")

            front = server_repository_url.rsplit(":", 1)

            end = front[1].split("@", 1)
            url_without_password = front[0] + "@" + end[1]

            cmd = "install add source {} {}".format(url_without_password, s_packages)
            output1 = self.ctx.send(cmd, wait_for_string="[Pp]assword:", timeout=60)
            output2 = self.ctx.send(end[0], timeout=100)
            output = output1 + output2
        else:
            cmd = "install add source {} {}".format(server_repository_url, s_packages)
            output = self.ctx.send(cmd, timeout=100)

        observe_install_add_remove(self.ctx, output, has_tar=has_tar)

    def run(self):
        check_ncs6k_release(self.ctx)

        server_repository_url = self.ctx.server_repository_url
        if server_repository_url is None:
            self.ctx.error("No repository provided")
            return

        packages = self.ctx.software_packages
        if packages is None:
            self.ctx.error("No package list provided")
            return

        has_tar = False

        if self.ctx.family == 'NCS6K':
            s_packages = " ".join([package for package in packages
                                   if ('iso' in package or 'pkg' in package or 'smu' in package or 'tar' in package)])
        else:
            s_packages = " ".join([package for package in packages
                                   if ('rpm' in package or 'iso' in package or 'tar' in package)])

        if 'tar' in s_packages:
            has_tar = True

        if not s_packages:
            self.ctx.error("None of the selected package(s) has an acceptable file extension.")

        self.ctx.info("Add Package(s) Pending")
        self.ctx.post_status("Add Package(s) Pending")

        self.install_add(server_repository_url, s_packages, has_tar=has_tar)

        self.ctx.info("Package(s) Added Successfully")

        # Refresh package and inventory information
        get_package(self.ctx)
        get_inventory(self.ctx)
