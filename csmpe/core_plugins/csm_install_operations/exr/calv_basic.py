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
import re
from csmpe.plugins import CSMPlugin
from install import watch_operation
from install import check_ncs6k_release


class Plugin(CSMPlugin):
    """This plugin tests basic install operations on calvados prompt."""
    name = "Install Calvados basic Plugin"
    platforms = {'ASR9K', 'NCS1K', 'NCS5K', 'NCS5500', 'NCS6K'}
    phases = {'Add'}
    os = {'eXR'}
    op_id = 0

    def execute_cmd(self, cmd):
        output = self.ctx.send(cmd, timeout=7200)
	result = re.search('Install operation (\d+)', output)
	if result:
	    self.op_id = result.group(1)
	else:
	    self.ctx.error("Operation failed")
	    self.ctx.error(output)
	    return  False # for sake of clarity

	op_success = "Install operation will continue in the background"
        if op_success in output:
            watch_operation(self.ctx, self.op_id)
	    return True
	else:
	    return False

    def run(self):
	self.ctx.info("exr test2 called")
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
	self.ctx.send("admin")
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
	     return
	self.ctx.info("Add package(s) passed")
	self.ctx.post_status("Add package(s) passed")

	cmd = "install prepare id {} ".format(pkg_id)
	result = self.execute_cmd(cmd)
	if result:
	     self.ctx.info("Package(s) Prepared Successfully")
	else:
	     self.ctx.info("Failed to prepared packages")
	     return
	
	self.ctx.info("prepare package(s) passed")
	self.ctx.post_status("prepare package(s) passed")
	cmd = "install activate "
	result = self.execute_cmd(cmd)
	if result:
	     self.ctx.info("Package(s) Activated Successfully")
	else:
	     self.ctx.info("Failed to activate packages")
	     return
	
	self.ctx.info("Activate package(s) passed")
	self.ctx.post_status("Activate package(s) passed")
	cmd = "install deactivate id {} ".format(pkg_id)
	result = self.execute_cmd(cmd)
	if result:
	     self.ctx.info("Package(s) deactivated Successfully")
	else:
	     self.ctx.info("Failed to deactivate packages")
	     return

	self.ctx.info("Deactivate package(s) passed")
	self.ctx.post_status("Deactivate package(s) passed")
	cmd = "install remove id {} ".format(pkg_id)
	result = self.execute_cmd(cmd)
	if result:
	     self.ctx.info("Package(s) remove Successfully")
	else:
	     self.ctx.info("Failed to remove packages")
	     return
	self.ctx.info("Remove package(s) passed")
	self.ctx.post_status("Remove package(s) passed")
