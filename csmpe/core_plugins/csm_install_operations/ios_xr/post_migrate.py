# =============================================================================
# migrate_system.py - plugin for migrating classic XR to eXR/fleXR
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
import time

from csmpe.plugins import CSMPlugin
from csmpe.context import PluginError
from migration_lib import wait_for_final_band, log_and_post_status
from csmpe.core_plugins.csm_custom_commands_capture.plugin import Plugin as CmdCapturePlugin
from csmpe.core_plugins.csm_get_software_packages.exr.plugin import get_package
from pre_migrate import FINAL_CAL_CONFIG

TIMEOUT_FOR_COPY_CONFIG = 3600


class Plugin(CSMPlugin):
    """
    A plugin for loading configurations and upgrading FPD's
    after the system migrated to ASR9K IOS-XR 64 bit(eXR).
    If any FPD needs reloads after upgrade, the device
    will be reloaded after the upgrade.
    Console access is needed.
    """
    name = "Post-Migrate Plugin"
    platforms = {'ASR9K'}
    phases = {'Post-Migrate'}

    def _copy_file_from_eusb_to_harddisk(self, filename):
        """
        Copy file from eUSB partition(/eusbb/backup_config/ in eXR) to /harddisk:.

        :param filename: the string name of the file you want to copy from /eusbb/backup_config/
        :return: True if no error occurred.
        """

        self.ctx.send("run", wait_for_string="\]\$")

        output = self.ctx.send("ls /eusbb/backup_config/{}".format(filename), wait_for_string="\]\$")

        if "No such file" in output:
            self.ctx.error("{} is missing in /eusbb/backup_config/ on device after migration.".format(filename))

        self.ctx.send("cp /eusbb/backup_config/{0} /harddisk:/{0}".format(filename),
                      timeout=300,
                      wait_for_string="\]\$")

        self.ctx.send("exit")

        return True

    def _quit_config(self):
        """Quit the config mode without committing any changes."""
        def send_no(ctx):
            ctx.ctrl.sendline("no")
            return True

        def timeout(ctx):
            ctx.message = "Timeout upgrading FPD."
            return False

        UNCOMMITTED_CHANGES = re.compile("Uncommitted changes found, commit them\? \[yes/no/CANCEL\]")
        pat2 = "Uncommitted changes found, commit them before exiting\(yes/no/cancel\)\? \[cancel\]"
        UNCOMMITTED_CHANGES_2 = re.compile(pat2)
        RUN_PROMPT = re.compile("#")

        TIMEOUT = self.ctx.TIMEOUT

        events = [UNCOMMITTED_CHANGES, UNCOMMITTED_CHANGES_2, RUN_PROMPT, TIMEOUT]
        transitions = [
            (UNCOMMITTED_CHANGES, [0], 1, send_no, 20),
            (UNCOMMITTED_CHANGES_2, [0], 1, send_no, 20),
            (RUN_PROMPT, [0], 0, None, 0),
            (RUN_PROMPT, [1], -1, None, 0),
            (TIMEOUT, [0, 1], -1, timeout, 0),

        ]

        if not self.ctx.run_fsm("Quit from config mode", "end", events, transitions, timeout=60):
            self.ctx.error("Failed to exit from the config mode. Please check session.log.")

    def _load_admin_config(self, filename):
        """Load the admin/calvados configuration."""
        self.ctx.send("config", wait_for_string="#")

        output = self.ctx.send("load merge {}".format(filename), timeout=600, wait_for_string="#")

        if "Error" in output or "failed" in output:
            self._quit_config()
            self.ctx.send("exit")
            self.ctx.error("Aborted committing admin Calvados configuration. Please check session.log for errors.")
        else:
            output = self.ctx.send("commit", timeout=600, wait_for_string="#")
            if "failure" in output:
                self._quit_config()
                self.ctx.send("exit")
                self.ctx.error("Failure to commit admin configuration. Please check session.log.")
            self.ctx.send("end")

    def _check_fpds_for_upgrade(self):
        """Check if any FPD's need upgrade, if so, upgrade all FPD's on all locations."""

        self.ctx.send("admin")

        fpdtable = self.ctx.send("show hw-module fpd")

        match = re.search("\d+/\w+.+\d+.\d+\s+[-\w]+\s+(NEED UPGD)", fpdtable)

        if match:
            total_num = len(re.findall("NEED UPGD", fpdtable)) + len(re.findall("CURRENT", fpdtable))
            if not self._upgrade_all_fpds(total_num):
                self.ctx.send("exit")
                self.ctx.error("FPD upgrade in eXR is not finished. Please check session.log.")
                return False
            else:
                return True

        self.ctx.send("exit")
        return True

    def _upgrade_all_fpds(self, num_fpds):
        """
        Upgrade all FPD's on all locations.
        If after all upgrade completes, some show that a reload is required to reflect the changes,
        the device will be reloaded.

        :param num_fpds: the number of FPD's that are in CURRENT and NEED UPGD states before upgrade.
        :return: True if upgraded successfully and reloaded(if necessary).
                 False if some FPD's did not upgrade successfully in 9600 seconds.
        """
        log_and_post_status(self.ctx, "Upgrading all FPD's.")
        self.ctx.send("upgrade hw-module location all fpd all")

        timeout = 9600
        poll_time = 30
        time_waited = 0

        time.sleep(60)
        while 1:
            # Wait till all FPDs finish upgrade
            time_waited += poll_time
            if time_waited >= timeout:
                break
            time.sleep(poll_time)
            output = self.ctx.send("show hw-module fpd")
            num_need_reload = len(re.findall("RLOAD REQ", output))
            if len(re.findall("CURRENT", output)) + num_need_reload >= num_fpds:
                if num_need_reload > 0:
                    log_and_post_status(self.ctx,
                                        "Finished upgrading FPD(s). Now reloading the device to complete the upgrade.")
                    self.ctx.send("exit")
                    return self._reload_all()
                self.ctx.send("exit")
                return True

        # Some FPDs didn't finish upgrade
        return False

    def _reload_all(self):
        """Reload the device with 1 hour maximum timeout"""
        self.ctx.reload(reload_timeout=3600, os=self.ctx.os_type)

        return self._wait_for_reload()

    def _wait_for_reload(self):
        """Wait for all nodes to come up with max timeout as 18 min"""
        # device.disconnect()
        # device.reconnect(max_timeout=300)
        log_and_post_status(self.ctx, "Waiting for all nodes to come to FINAL Band.")
        if wait_for_final_band(self.ctx):
            log_and_post_status(self.ctx, "All nodes are in FINAL Band.")
        else:
            log_and_post_status(self.ctx, "Warning: Not all nodes went to FINAL Band.")

        return True

    def run(self):

        log_and_post_status(self.ctx, "Waiting for all nodes to come to FINAL Band.")
        if not wait_for_final_band(self.ctx):
            log_and_post_status(self.ctx, "Warning: Not all nodes are in FINAL Band after 25 minutes.")

        try:
            self.ctx.custom_commands = ["show running-config"]
            cmd_capture_plugin = CmdCapturePlugin(self.ctx)
            cmd_capture_plugin.run()
        except PluginError as e:
            log_and_post_status(self.ctx,
                                "Failed to capture 'show running-config' - ({}): {}".format(e.errno, e.strerror))

        log_and_post_status(self.ctx, "Loading the migrated Calvados configuration.")
        self.ctx.send("admin")
        self._copy_file_from_eusb_to_harddisk(FINAL_CAL_CONFIG)
        self._load_admin_config(FINAL_CAL_CONFIG)

        try:
            # This is still in admin mode
            output = self.ctx.send("show running-config", timeout=2200)
            file_name = self.ctx.save_to_file("admin show running-config", output)
            if file_name is None:
                log_and_post_status(self.ctx,
                                    "Unable to save '{}' output to file: {}".format("admin show running-config",
                                                                                    file_name))
            else:
                log_and_post_status(self.ctx,
                                    "Output of '{}' command saved to file: {}".format("admin show running-config",
                                                                                      file_name))
        except Exception as e:
            log_and_post_status(self.ctx, str(type(e)) + " when trying to capture 'admin show running-config'.")

        self.ctx.send("exit")

        self._check_fpds_for_upgrade()

        try:
            self.ctx.custom_commands = ["show platform"]
            cmd_capture_plugin = CmdCapturePlugin(self.ctx)
            cmd_capture_plugin.run()
        except PluginError as e:
            log_and_post_status(self.ctx,
                                "Failed to capture 'show platform' - ({}): {}".format(e.errno, e.strerror))

        # Refresh package information
        get_package(self.ctx)
