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
from install import watch_operation
from install import check_ncs6k_release
from install import wait_for_reload
from time import sleep
import re


class Plugin(CSMPlugin):
    "This module tests OIR which is sync-up on standby calvados VM"
    name = "Install oir Plugin"
    platforms = {'ASR9K', 'NCS1K', 'NCS5K', 'NCS5500', 'NCS6K', 'XRV9K'}
    phases = {'Add'}
    os = {'eXR'}
    op_id = 0
    fsm_result = False

    def get_op_id(self, output):
        result = re.search('Install operation (\d+)', output)
        if result:
            return result.group(1)
        return -1

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

    def no_impact_warning(self, fsm_ctx):
        self.ctx.warning("This was a NO IMPACT OPERATION. Packages are already active on device.")
        self.fsm_result = True
        return True

    def handle_hw_modify_cmd(self, fsm_ctx):
        self.op_id = self.get_op_id(fsm_ctx.ctrl.before)
        self.ctx.info("handle_hw_modify_cmd() called for")
        self.ctx.info(self.op_id)
        self.ctx.send("yes\r\n", timeout=30)
        # give hw 5 mins to stabilize
        sleep(300)

        self.ctx.info("Operation {} finished successfully".format(self.op_id))
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
            return

        self.ctx.info("Operation {} finished successfully".format(self.op_id))
        self.fsm_result = True
        return True

    def execute_cmd(self, cmd):
        ABORTED = re.compile("aborted")
        CONTINUE_IN_BACKGROUND = re.compile("Install operation will continue in the background")
        REBOOT_PROMPT = re.compile("This install operation will (?:reboot|reload) the sdr, continue")
        RUN_PROMPT = re.compile("#")
        NO_IMPACT = re.compile("NO IMPACT OPERATION")
        HW_PROMPT = re.compile("hardware module ?")

        events = [CONTINUE_IN_BACKGROUND, REBOOT_PROMPT, ABORTED, NO_IMPACT, RUN_PROMPT, HW_PROMPT]
        transitions = [
            (CONTINUE_IN_BACKGROUND, [0], -1, self.handle_non_reload_cmd, 100),
            (REBOOT_PROMPT, [0], -1, self.handle_reload_cmd, 100),
            (NO_IMPACT, [0], -1, self.no_impact_warning, 20),
            (RUN_PROMPT, [0], -1, self.handle_non_reload_cmd, 100),
            (HW_PROMPT, [0], -1, self.handle_hw_modify_cmd, 100),
            (ABORTED, [0], -1, self.handle_aborted, 100),
        ]

        if not self.ctx.run_fsm("OIR cmd", cmd, events, transitions, timeout=100):
            self.ctx.error("Failed: {}".format(cmd))
        return self.fsm_result

    def show_cmd(self, cmd):
        result = self.ctx.send(cmd, timeout=120)
        if not result:
            self.ctx.info("show cmd failed")

    def generic_show(self):
        self.show_cmd("show install active")
        self.show_cmd("show install inactive")
        self.show_cmd("show install repository all")

    def verify_pkgs(self):
        cmd = "install verify packages"
        result = self.execute_cmd(cmd)
        if result:
            return True
        self.ctx.error("install verification failed")
        return False

    def commit_verify(self):
        num_active = 0
        num_committed = 0
        result = self.ctx.send("show install active", timeout=120)
        for line in result:
            if re.search(r"  Active Packages: ", line):
                num_active = line[20:]
        result = self.execute_cmd("install commit")
        if not result:
            return False
        result = self.ctx.send("show install committed", timeout=120)
        for line in result:
            if re.search(r"  Commmitted Packages: ", line):
                num_committed = line[22:]
        if num_active != num_committed:
            return False
        return True

    def disable_standby(self):
        self.execute_cmd("hw-module location 0/RP1 shutdown")

    def enable_standby(self):
        self.execute_cmd("hw-module location 0/RP1 reload")

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
        # OIR facility is available only for calvados package installations
        self.ctx.send("admin", timeout=30)
        self.disable_standby()
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

        cmd = "install activate id {} ".format(pkg_id)
        result = self.execute_cmd(cmd)
        if result:
            self.ctx.info("Package(s) Activated Successfully")
        else:
            self.ctx.info("Failed to activate packages")
            return
        self.ctx.info("Activate package(s) passed")
        self.ctx.post_status("Activate package(s) passed")
        if not self.verify_pkgs():
            return False
        if not self.commit_verify():
            return False
        self.enable_standby()
        # give the standby sufficient time to sync i.e do the OIR
        sleep(600)
        cmd = "install deactivate id {} ".format(pkg_id)
        result = self.execute_cmd(cmd)
        if result:
            self.ctx.info("Package(s) deactivated Successfully")
        else:
            self.ctx.info("Failed to deactivate packages")
            return

        self.ctx.info("Deactivate package(s) passed")
        self.ctx.post_status("Deactivate package(s) passed")
        if not self.commit_verify():
            return False
        cmd = "install remove id {} ".format(pkg_id)
        result = self.execute_cmd(cmd)
        if result:
            self.ctx.info("Package(s) remove Successfully")
        else:
            self.ctx.info("Failed to remove packages")
            return
        self.ctx.info("Remove package(s) passed")
        self.ctx.post_status("Remove package(s) passed")
        if not self.commit_verify():
            return False
        self.ctx.send("exit", timeout=30)
        return True
