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
from condoor.exceptions import CommandSyntaxError
from csmpe.context import PluginError
from migration_lib import wait_for_final_band, log_and_post_status
from csmpe.core_plugins.csm_custom_commands_capture.plugin import Plugin as CmdCapturePlugin
from csmpe.core_plugins.csm_get_software_packages.exr.plugin import get_package
from pre_migrate import XR_CONFIG_ON_DEVICE, ADMIN_CAL_CONFIG_ON_DEVICE, ADMIN_XR_CONFIG_ON_DEVICE

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

    def _copy_file_from_eusb_to_harddisk(self, filename, optional=False):
        """
        Copy file from eUSB partition(/eusbb/ in eXR) to /harddisk:.

        :param filename: the string name of the file you want to copy from /eusbb
        :param optional: boolean value. If set to True, it's okay if the given filename
                         is not found in /eusbb/. If False, error out if the given filename
                         is missing from /eusbb/.
        :return: True if no error occurred.
        """

        self.ctx.send("run", wait_for_string="\]\$")

        output = self.ctx.send("ls /eusbb/{}".format(filename), wait_for_string="\]\$")

        if "No such file" in output:
            if not optional:
                self.ctx.error("{} is missing in /eusbb/ on device after migration.".format(filename))
            else:
                self.ctx.send("exit")
                return False

        self.ctx.send("cp /eusbb/{0} /harddisk:/{0}".format(filename), wait_for_string="\]\$")

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

        output = self.ctx.send("load replace {}".format(filename), wait_for_string="#")

        if "Error" in output or "failed" in output:
            self._quit_config()
            self.ctx.send("exit")
            self.ctx.error("Aborted committing admin Calvados configuration. Please check session.log for errors.")
        else:
            output = self.ctx.send("commit", wait_for_string="#")
            if "failure" in output:
                self._quit_config()
                self.ctx.send("exit")
                self.ctx.error("Failure to commit admin configuration. Please check session.log.")
            self.ctx.send("end")

    def _load_nonadmin_config(self, filename, commit_with_best_effort):
        """Load the XR configuration."""
        self.ctx.send("config")

        output = self.ctx.send("load harddisk:/{}".format(filename))

        if "error" in output or "failed" in output:
            return self._handle_failed_commit(output, commit_with_best_effort, filename)

        output = self.ctx.send("commit")
        if "Failed" in output:
            return self._handle_failed_commit(output, commit_with_best_effort, filename)

        if "No configuration changes to commit" in output:
            log_and_post_status(self.ctx, "No configuration changes in /eusbb/{} were committed. ".format(filename) +
                                "Please check session.log.")
        if "Abort" in output:
            self._quit_config()
            self.ctx.error("Failure to commit configuration. Please check session.log for errors.")
        self.ctx.send("end")
        return True

    def _handle_failed_commit(self, output, commit_with_best_effort, filename):
        """
        Display which line of config failed to load for which reason.
        If when scheduling Post-Migrate, user chooses to commit the migrated or
        self-selected custom XR config with best effort, we will commit the
        configs with best effort upon failure to load some configs, else, the loading
        will be aborted upon failure with some configs, the process errors out.

        :param output: output after CLI "commit"
        :param commit_with_best_effort: 1 or -1. 1 for commiting with best effort.
                                        -1 for aborting commit upon error.
        :param filename: the string config filename in /eusbb/ that we are
                         trying to commit
        :return: True if no error occurred.
        """
        cmd = ""
        if "show configuration failed load [detail]" in output:
            cmd = "show configuration failed load detail"
        elif "show configuration failed [inheritance]" in output:
            cmd = "show configuration failed inheritance"

        if cmd:
            try:
                self.ctx.send(cmd)
            except CommandSyntaxError:
                pass

        if commit_with_best_effort == -1:
            self._quit_config()

            self.ctx.error("Errors when loading configuration. Please check session.log.")

        elif commit_with_best_effort == 1:
            output = self.ctx.send("commit best-effort force")
            log_and_post_status(self.ctx,
                                "Committed configurations with best-effort. Please check session.log for result.")
            if "No configuration changes to commit" in output:
                log_and_post_status(self.ctx,
                                    "No configuration changes in /eusbb/{} were committed. ".format(filename) +
                                    "Please check session.log for errors.")
            self.ctx.send("end")

        return True

    def _check_fpds_for_upgrade(self):
        """Check if any FPD's need upgrade, if so, upgrade all FPD's on all locations."""

        self.ctx.send("admin")

        fpdtable = self.ctx.send("show hw-module fpd")

        match = re.search("\d+/\w+.+\d+.\d+\s+[-\w]+\s+(NEED UPGD)", fpdtable)

        if match:
            total_num = len(re.findall("NEED UPGD", fpdtable)) + len(re.findall("CURRENT", fpdtable))
            if not self._upgrade_all_fpds(total_num):
                self.ctx.error("FPD upgrade in eXR is not finished. Please check session.log.")
                return False

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

        try:
            best_effort_config = self.ctx.post_migrate_config_handling_option
        except AttributeError:
            self.ctx.error("No configuration handling option selected when scheduling post-migrate.")

        log_and_post_status(self.ctx, "Waiting for all nodes to come to FINAL Band.")
        if not wait_for_final_band(self.ctx):
            log_and_post_status(self.ctx, "Warning: Not all nodes are in FINAL Band after 20 minutes.")

        log_and_post_status(self.ctx, "Loading the migrated Calvados configuration first.")
        self.ctx.send("admin")
        self._copy_file_from_eusb_to_harddisk(ADMIN_CAL_CONFIG_ON_DEVICE)
        self._load_admin_config(ADMIN_CAL_CONFIG_ON_DEVICE)

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

        log_and_post_status(self.ctx, "Loading the admin IOS-XR configuration on device.")
        file_exists = self._copy_file_from_eusb_to_harddisk(ADMIN_XR_CONFIG_ON_DEVICE, optional=True)
        if file_exists:
            self._load_nonadmin_config(ADMIN_XR_CONFIG_ON_DEVICE, best_effort_config)

        log_and_post_status(self.ctx, "Loading the IOS-XR configuration on device.")
        file_exists = self._copy_file_from_eusb_to_harddisk(XR_CONFIG_ON_DEVICE)
        if file_exists:
            self._load_nonadmin_config(XR_CONFIG_ON_DEVICE, best_effort_config)

        try:
            self.ctx.custom_commands = ["show running-config"]
            cmd_capture_plugin = CmdCapturePlugin(self.ctx)
            cmd_capture_plugin.run()
        except PluginError as e:
            log_and_post_status(self.ctx,
                                "Failed to capture 'show running-config' - ({}): {}".format(e.errno, e.strerror))

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
