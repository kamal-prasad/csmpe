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
from csmpe.context import PluginError
from install import watch_operation
from install import wait_for_reload
import re


class Plugin(CSMPlugin):
    """This plugin tests ISSU operation on ios prompt."""
    name = "Install issu Plugin"
    platforms = {'ASR9K', 'CRS'}
    phases = {'Add'}
    os = {'XR'}
    op_id = 0
    fsm_result = False

    def get_op_id(self, output):
        result = re.search('Install operation (\d+)', output)
        if result:
            return result.group(1)
        return -1

    def get_pkg_name(self, pkg_id):
        """This routine assumes only 1 pkg was installed and returns name"""
        cmd = "show install log {} ".format(pkg_id)
        output = self.ctx.send(cmd, timeout=120)
        lines = output.split('\n')
        idx = 0
        for idx, line in enumerate(lines):
            if re.search('install add action finished successfully', line):
                words = lines[idx - 1].split()
                self.ctx.info("package to be parsed:")
                self.ctx.info(words)
                return words[len(words) - 1]
        return -1

    def get_extracted_pkg(self, op_id, admin_mode):
        cmd = "show install log {} ".format(op_id)
        output = self.ctx.send(cmd, timeout=120)
        lines = output.split('\n')
        self.ctx.info(lines)
        if admin_mode:
            pattern = 'Extracted package :'
        else:
            pattern = 'Extracted Package:'
        result = []
        for line in lines:
            if re.search(pattern, line):
                words = line.split(':')
                result.append(words[len(words) - 1])
        return ' '.join(result)

    def handle_non_reload_cmd(self, fsm_ctx):
        self.op_id = self.get_op_id(fsm_ctx.ctrl.before)
        if self.op_id == -1:
            self.fsm_result = False
            return False
        watch_operation(self.ctx, self.op_id)
        self.fsm_result = True
        return True

    def handle_aborted(self, fsm_ctx):
        self.fsm_result = False
        return False

    def handle_confirm(self, fsm_ctx):
        self.ctx.send("yes", timeout=30)
        self.op_id = self.get_op_id(fsm_ctx.ctrl.before)
        watch_operation(self.ctx, self.op_id)
        self.fsm_result = True
        return True

    def no_impact_warning(self, fsm_ctx):
        self.ctx.warning("This was a NO IMPACT OPERATION. Packages are already active on device.")
        self.fsm_result = True
        return True

    def handle_reload_cmd(self, fsm_ctx):

        self.op_id = self.get_op_id(fsm_ctx.ctrl.before)
        if self.op_id == -1:
            self.fsm_result = False
            return False

        try:
            watch_operation(self.ctx, self.op_id)
        except self.ctx.CommandTimeoutError:
            # The device already started the reload
            pass

        success = wait_for_reload(self.ctx)
        if not success:
            self.ctx.error("Reload or boot failure")
            self.fsm_result = False
            return self.fsm_result

        self.ctx.info("Operation {} finished successfully".format(self.op_id))
        self.fsm_result = True
        return True

    def execute_cmd(self, cmd):
        ABORTED = re.compile("aborted")
        CONTINUE_IN_BACKGROUND = re.compile("Install operation will continue in the background")
        REBOOT_PROMPT = re.compile("This install operation will (?:reboot|reload) the sdr, continue")
        RUN_PROMPT = re.compile("#")
        ACTIVATE_PROMPT = re.compile("will clean the prepared packages, continue")
        PROCEED_PROMPT = re.compile("Do you want to proceed")
        CONFIRM_PROMPT = re.compile("to continue")
        NO_IMPACT = re.compile("NO IMPACT OPERATION")
        ISSU_PROMPT = re.compile("start the issu, continue")
        events = [CONTINUE_IN_BACKGROUND, REBOOT_PROMPT, ABORTED, NO_IMPACT, RUN_PROMPT, CONFIRM_PROMPT, ACTIVATE_PROMPT, ISSU_PROMPT]
        transitions = [
            (CONTINUE_IN_BACKGROUND, [0], -1, self.handle_non_reload_cmd, 100),
            (REBOOT_PROMPT, [0], -1, self.handle_reload_cmd, 100),
            (NO_IMPACT, [0], -1, self.no_impact_warning, 20),
            (RUN_PROMPT, [0], -1, self.handle_non_reload_cmd, 100),
            (ACTIVATE_PROMPT, [0], -1, self.handle_confirm, 100),
            (CONFIRM_PROMPT, [0], -1, self.handle_confirm, 100),
            (PROCEED_PROMPT, [0], -1, self.handle_confirm, 100),
            (ISSU_PROMPT, [0], -1, self.handle_confirm, 100),
            (ABORTED, [0], -1, self.handle_aborted, 100),
        ]

        if not self.ctx.run_fsm("issu cmd", cmd, events, transitions, timeout=100):
            self.ctx.error("Failed: {}".format(cmd))
        return self.fsm_result

    def check_prepare(self, pkg_name):
        cmd = "install prepare issu  {} ".format(pkg_name)
        self.ctx.info(cmd)
        result = self.execute_cmd(cmd)
        if result:
            self.ctx.info("Package(s) Prepared Successfully")
        else:
            self.ctx.info("Failed to prepared packages")
            return
        result = self.execute_cmd("install prepare clean")
        return result

    def perform_activate(self, pkg_name):
        cmd = "install activate issu load " + pkg_name
        try:
            result = self.execute_cmd(cmd)
        except PluginError:
            self.ctx._connection.reconnect()
        if result:
            self.ctx.info("Package(s) activated Successfully")
        else:
            self.ctx.info("Failed to activate packages")
            return
        return result

    def run(self):
        server_repository_url = self.ctx.server_repository_url
        if server_repository_url is None:
            self.ctx.error("No repository provided")
            return

        packages = self.ctx.software_packages
        if packages is None:
            self.ctx.error("No package list provided")
            return

        has_tar = False
        is_iso = False
        if self.ctx.family == 'NCS6K':
            s_packages = " ".join([package for package in packages
                                   if ('iso' in package or 'pkg' in package or 'smu' in package or 'tar' in package)])
        else:
            s_packages = " ".join([package for package in packages
                                   if ('rpm' in package or 'iso' in package or 'tar' in package)])

        if 'tar' in s_packages:
            has_tar = True

        if 'iso' in s_packages:
            is_iso = True

        if not s_packages:
            self.ctx.error("None of the selected package(s) has an acceptable file extension.")
        cmd = "install add source {} {} ".format(server_repository_url, s_packages)
        result = self.execute_cmd(cmd)
        if result:
            pkg_id = self.op_id
            if has_tar is True:
                self.ctx.operation_id = self.op_id
                self.ctx.info("The operation {} stored".format(self.op_id))
            self.ctx.info("Package(s) Added Successfully")
        else:
            self.ctx.info("Failed to add packages")
            self.ctx.error(result)
            return
        self.ctx.info("Add package(s) passed")
        self.ctx.post_status("Add package(s) passed")
        pkg_name = self.get_pkg_name(pkg_id)
        self.ctx.info("pkg_name = ")
        self.ctx.info(pkg_name)
        admin_mode = self.ctx.admin_mode
        if admin_mode:
            self.ctx.send("admin", timeout=30)
        if is_iso:
            cmd = "install extract  {} ".format(pkg_name)
            result = self.execute_cmd(cmd)
            if result:
                self.ctx.info("Package extracted Successfully")
            else:
                self.ctx.info("Failed to extract package")
                return
            extracted_pkg_name = self.get_extracted_pkg(self.op_id, admin_mode)
            result = self.check_prepare(extracted_pkg_name)
            if result:
                self.ctx.info("Validated issu prepare operation")
            else:
                self.ctx.info("Failed validation of issu prepare operation")
                return
            result = self.perform_activate(extracted_pkg_name)
            if result:
                result = self.execute_cmd("install activate issu abort cleanup")
                if result:
                    self.ctx.info("Validated install activate issu")
                else:
                    self.ctx.info("Failed  install activate issu abort cleanup")
                    return
            else:
                self.ctx.info("Failed install activate issu")
                return
        else:
            result = self.check_prepare(pkg_name)
            if result:
                self.ctx.info("Validated issu prepare operation")
            else:
                self.ctx.info("Failed validation of issu prepare operation")
                return
            result = self.perform_activate(pkg_name)
            if result:
                try:
                    result = self.execute_cmd("install activate issu run")
                except PluginError:
                    self.ctx._connection.reconnect()
                    pass
                if result:
                    self.ctx.info("Validated install activate issu run")
                    cmd = "install deactivate  {} ".format(pkg_name)
                    result = self.execute_cmd(cmd)
                    if result:
                        self.ctx.info("Validated deactivate issu")
                    else:
                        self.ctx.info("Failed deactivate issu")
                else:
                    self.ctx.info("Failed  install activate issu run")
                    return
            else:
                self.ctx.info("Failed install activate issu load")
        if admin_mode:
            self.ctx.send("exit", timeout=30)
        return True
