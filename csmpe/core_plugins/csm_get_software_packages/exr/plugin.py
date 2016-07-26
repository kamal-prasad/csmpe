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


class Plugin(CSMPlugin):
    """This plugin retrieves software information from the device."""
    name = "Get Software Packages Plugin"
    platforms = {'ASR9K', 'NCS1K', 'NCS5K', 'NCS5500', 'NCS6K'}
    phases = {'Get-Software-Packages'}
    os = {'eXR'}

    def run(self):
        get_package(self.ctx)


def get_package(ctx):
    """
    Convenient method, it may be called by outside of the plugin
    """

    # Get the admin packages
    ctx.save_data("cli_admin_show_install_inactive", get_admin_package(ctx, "show install inactive"))
    ctx.save_data("cli_admin_show_install_active", get_admin_package(ctx, "show install active"))
    ctx.save_data("cli_admin_show_install_committed", get_admin_package(ctx, "show install committed"))

    # Get the non-admin packages
    ctx.save_data("cli_show_install_inactive", ctx.send("show install inactive"))
    ctx.save_data("cli_show_install_active", ctx.send("show install active"))
    ctx.save_data("cli_show_install_committed", ctx.send("show install committed"))


def get_admin_package(ctx, cmd):
    ctx.send("admin")
    output = ctx.send(cmd)
    ctx.send("exit")

    return output
