# =============================================================================
# migrate.py - plugin for migrating classic XR to eXR/fleXR
#
# Copyright (c)  2013, Cisco Systems
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

import re

from csmpe.plugins import CSMPlugin
from csmpe.context import PluginError
from csmpe.core_plugins.csm_custom_commands_capture.plugin import Plugin as CmdCapturePlugin
from condoor.controllers.protocols.base import PASSWORD_PROMPT, USERNAME_PROMPT, PERMISSION_DENIED, \
    AUTH_FAILED, RESET_BY_PEER, SET_USERNAME, SET_PASSWORD, \
    PASSWORD_OK, PRESS_RETURN, UNABLE_TO_CONNECT
from condoor.controllers.protocols.telnet import ESCAPE_CHAR, CONNECTION_REFUSED
from condoor.exceptions import ConnectionError, ConnectionAuthenticationError
from migration_lib import wait_for_final_band, log_and_post_status
from csmpe.core_plugins.csm_get_software_packages.exr.plugin import get_package
from csmpe.core_plugins.csm_install_operations.utils import update_device_info_udi


XR_PROMPT = re.compile('(\w+/\w+/\w+/\w+:.*?)(\([^()]*\))?#')

SCRIPT_BACKUP_CONFIG = "harddiskb:/classic.cfg"
SCRIPT_BACKUP_ADMIN_CONFIG = "harddiskb:/admin.cfg"

MIGRATION_TIME_OUT = 3600
NODES_COME_UP_TIME_OUT = 3600


class Plugin(CSMPlugin):
    """
    A plugin for migrating a ASR9K IOS-XR(XR) system to
    ASR9K IOS-XR 64 bit(eXR/fleXR).
    This plugin calls the migration script on device and reload
    device to boot eXR image.
    Console access is needed.
    """
    name = "Migrate Plugin"
    platforms = {'ASR9K'}
    phases = {'Migrate'}

    def _run_migration_script(self):
        """
        Run the migration script in /pkg/bin/migrate_to_eXR on device to set
        internal variables for booting eXR image.
        Check that no error occurred.
        :return: True if no error occurred.
        """

        self.ctx.send("run", wait_for_string="#")

        output = self.ctx.send("ksh /pkg/bin/migrate_to_eXR -m eusb", wait_for_string="#", timeout=600)

        self.ctx.send("exit")

        self._check_migration_script_output(output)

        return True

    def _check_migration_script_output(self, output):
        """Check that the migration script finished without errors, and also, the configs are backed up."""
        lines = output.splitlines()
        for line in lines:
            if "No such file" in line:
                self.ctx.error("Found file missing when running migration script. Please check session.log.")
            if "Error:" in line:
                self.ctx.error("Migration script returned error. Please check session.log.")

        output = self.ctx.send('dir {}'.format(SCRIPT_BACKUP_CONFIG))
        if "No such file" in output:
            self.ctx.error("Migration script failed to back up the running config. Please check session.log.")
        else:
            log_and_post_status(self.ctx, "The running-config is backed up in {}".format(SCRIPT_BACKUP_CONFIG))

        output = self.ctx.send('dir {}'.format(SCRIPT_BACKUP_ADMIN_CONFIG))
        if "No such file" in output:
            self.ctx.error("Migration script failed to back up the admin running config. Please check session.log.")
        else:
            log_and_post_status(self.ctx, "The admin running-config is backed up in {}".format(SCRIPT_BACKUP_CONFIG))

    def _configure_authentication(self, host):
        """
        After device is reloaded to boot eXR image from eUSB, the image will get baked,
        eventually the device prompts for reconfiguration of username and password to login.
        After that, the device prompts for login and then we will get XR prompt.
        An FSM is created to support that.

        :return: None if no error occurred.
        """

        connection_param = host.connection_param[0]

        def send_return(ctx):
            ctx.ctrl.send("\r\n")
            return True

        def send_username(ctx):
            ctx.ctrl.sendline(connection_param.username)
            return True

        def send_password(ctx):
            ctx.ctrl.sendline(connection_param.password)
            return True

        TIMEOUT = self.ctx.TIMEOUT

        events = [ESCAPE_CHAR, PASSWORD_OK, SET_USERNAME, SET_PASSWORD, USERNAME_PROMPT, PASSWORD_PROMPT,
                  XR_PROMPT, PRESS_RETURN, UNABLE_TO_CONNECT,
                  CONNECTION_REFUSED, RESET_BY_PEER, PERMISSION_DENIED,
                  AUTH_FAILED, TIMEOUT]

        transitions = [
            (ESCAPE_CHAR, [0, 1], 1, None, 20),
            (PASSWORD_OK, [0, 1], 1, send_return, 10),
            (PASSWORD_OK, [6], 6, send_return, 10),
            (PRESS_RETURN, [0, 1], 1, send_return, 10),
            (PRESS_RETURN, [6], 6, send_return, 10),
            (SET_USERNAME, [0, 1, 2, 3], 4, send_username, 20),
            (SET_USERNAME, [4], 4, None, 1),
            (SET_PASSWORD, [4], 5, send_password, 10),
            (SET_PASSWORD, [5], 6, send_password, 10),
            (USERNAME_PROMPT, [0, 1, 6, 7], 8, send_username, 10),
            (USERNAME_PROMPT, [8], 8, None, 10),
            (PASSWORD_PROMPT, [8], 9, send_password, 30),
            (XR_PROMPT, [0, 9, 10], -1, None, 10),

            (UNABLE_TO_CONNECT, [0, 1], 11, ConnectionError("Unable to connect", self.ctx._connection.hostname), 10),
            (CONNECTION_REFUSED, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 11,
             ConnectionError("Connection refused", "i"), 1),

            (RESET_BY_PEER, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 11,
             ConnectionError("Connection reset by peer", self.ctx._connection.hostname), 1),

            (PERMISSION_DENIED, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 11,
             ConnectionAuthenticationError("Permission denied", self.ctx._connection.hostname), 1),

            (AUTH_FAILED, [6, 9], 11, ConnectionAuthenticationError("Authentication failed",
                                                                    self.ctx._connection.hostname), 1),
            (TIMEOUT, [0], 1, None, 20),
            (TIMEOUT, [1], 2, None, 40),
            (TIMEOUT, [2], 3, None, 60),
            (TIMEOUT, [3, 7], 11, ConnectionError("Timeout waiting to connect", self.ctx._connection.hostname), 10),
            (TIMEOUT, [6], 7, None, 20),
            (TIMEOUT, [9], 10, None, 60),
        ]

        if not self.ctx.run_fsm("Reconfiguring authentication", "", events, transitions, timeout=30):
            self.ctx.error("Failed to connect to device after reload.")

    def _reload_all(self, host):
        """Reload all nodes to boot eXR image."""
        self.ctx.reload(reload_timeout=MIGRATION_TIME_OUT)

        return self._wait_for_reload(host)

    def _wait_for_reload(self, host):
        """Wait for all nodes to come up with max timeout as 18 minutes after the first RSP/RP comes up."""
        self._configure_authentication(host)

        log_and_post_status(self.ctx, "Waiting for all nodes to come to FINAL Band.")
        if wait_for_final_band(self.ctx):
            log_and_post_status(self.ctx, "All nodes are in FINAL Band.")
        else:
            log_and_post_status(self.ctx, "Warning: Not all nodes are in FINAL Band after 25 minutes.")

        return True

    def run(self):
        host = None
        try:
            host = self.ctx.get_host
        except AttributeError:
            self.ctx.error("No host selected.")

        if host is None:
            self.ctx.error("No host selected.")

        log_and_post_status(self.ctx,
                            "Run migration script to extract the image and boot files and set boot mode in device")
        self._run_migration_script()

        log_and_post_status(self.ctx, "Reload device to boot eXR")
        self._reload_all(host)

        try:
            self.ctx.custom_commands = ["show platform"]
            cmd_capture_plugin = CmdCapturePlugin(self.ctx)
            cmd_capture_plugin.run()
        except PluginError as e:
            log_and_post_status(self.ctx, "Failed to capture 'show platform' - ({}): {}".format(e.errno, e.strerror))

        # Refresh package information
        get_package(self.ctx)

        update_device_info_udi(self.ctx)

        return True
