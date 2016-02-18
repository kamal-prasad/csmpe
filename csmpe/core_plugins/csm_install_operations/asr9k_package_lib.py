# =============================================================================
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

# from documentation:
# http://www.cisco.com/c/en/us/td/docs/routers/asr9000/software/asr9k_r5-3/sysman/configuration/guide/b-sysman-cg-53xasr9k/b-sysman-cg-53xasr9k_chapter_0100.html#con_57141
platforms = ["asr9k", "hfr", "c12k"]
package_types = "mini mcast mgbl mpls k9sec diags fpd doc bng li optic services services-infa " \
                "infra-test video asr9000v asr901 asr903".split()
version_re = re.compile("(?P<VERSION>\d+\.\d+\.\d+(\.\d+\w+)?)")
smu_re = re.compile("(?P<SMU>CSC[a-z]{2}\d{5})")
sp_re = re.compile("(?P<SP>(sp|fp)\d{0,2})")
subversion_re = re.compile("(CSC|sp|fp).*(?P<SUBVERSION>\d+\.\d+\.\d+?)")


class SoftwarePackage(object):
    def __init__(self, package_name):
        self.package_name = package_name

    @property
    def platform(self):
        for platform in platforms:
            if platform + "-" in self.package_name:
                return platform
        else:
            return None

    @property
    def package_type(self):
        for package_type in package_types:
            if "-" + package_type + "-" in self.package_name:
                return package_type
        else:
            return None

    @property
    def architecture(self):
        if "-px-" in self.package_name:
            return "px"
        elif "-p-" in self.package_name:
            return "p"
        else:
            return None

    @property
    def version(self):
        result = re.search(version_re, self.package_name)
        return result.group("VERSION") if result else None

    @property
    def smu(self):
        result = re.search(smu_re, self.package_name)
        return result.group("SMU") if result else None

    @property
    def sp(self):
        result = re.search(sp_re, self.package_name)
        return result.group("SP") if result else None

    @property
    def subversion(self):
        if self.sp or self.smu:
            result = re.search(subversion_re, self.package_name)
            return result.group("SUBVERSION") if result else None
        return None

    def is_valid(self):
        return self.platform and self.version and self.architecture and (self.package_type or self.smu or self.sp)

    def __eq__(self, other):
        return self.platform == other.platform and \
            self.package_type == other.package_type and \
            self.architecture == other.architecture and \
            self.version == other.version and \
            self.smu == other.smu and \
            self.sp == other.sp and \
            self.subversion == other.subversion

    def __hash__(self):
        return hash("{}{}{}{}{}".format(
            self.platform, self.package_type, self.architecture, self.version, self.smu, self.sp, self.subversion))

    @staticmethod
    def from_show_cmd(cmd):
        software_packages = set()
        data = cmd.split()
        for line in data:
            software_package = SoftwarePackage(line)
            if software_package.is_valid():
                software_packages.add(software_package)
        return software_packages

    @staticmethod
    def from_package_list(pkg_list):
        software_packages = set()
        for pkg in pkg_list:
            software_package = SoftwarePackage(pkg)
            if software_package.is_valid():
                software_packages.add(software_package)
        return software_packages

    def __repr__(self):
        return self.package_name

    def __str__(self):
        return self.__repr__()


# disk0:asr9k-mini-px-4.3.2
# asr9k-px-4.2.3.CSCue60194-1.0.0
# disk0:asr9k-px-5.3.1.06I.CSCub11122-1.0.0
# disk0:asr9k-px-5.3.3.09I.CSCus12345-1.0.0
# disk0:asr9k-px-4.3.2.sp-1.0.0
# disk0:asr9k-px-4.3.2.sp2-1.0.0
#    'asr9k-9000v-nV-p': 'asr9k-asr9000v-nV-px.pie',
#    'asr9k-asr901-nV-p': 'asr9k-asr901-nV-px.pie',
#    'asr9k-asr903-nV-p': 'asr9k-asr903-nV-px.pie',
# asr9k-px-5.3.3.CSCux61372-0.0.5.d.pie - TEST IT!!!!

show_install_active1 = """
RP/0/RSP0/CPU0:R2#show install active summary
Mon Feb 15 04:37:12.485 UTC
Default Profile:
  SDRs:
    Owner
  Active Packages:
    disk0:asr9k-bng-px-5.3.3
    disk0:asr9k-doc-px-5.3.3
    disk0:asr9k-fpd-px-5.3.3
    disk0:asr9k-k9sec-px-5.3.3
    disk0:asr9k-li-px-5.3.3
    disk0:asr9k-mcast-px-5.3.3
    disk0:asr9k-mgbl-px-5.3.3
    disk0:asr9k-mini-px-5.3.3
    disk0:asr9k-mpls-px-5.3.3
    disk0:asr9k-optic-px-5.3.3
    disk0:asr9k-services-px-5.3.3
    disk0:asr9k-video-px-5.3.3
"""

show_install_active2 = """
RP/0/RSP0/CPU0:R2#show install active summary
Mon Feb 15 04:37:12.485 UTC
Default Profile:
  SDRs:
    Owner
  Active Packages:
    disk0:asr9k-fpd-px-5.3.3
    disk0:asr9k-k9sec-px-5.3.3
    disk0:asr9k-li-px-5.3.3
    disk0:asr9k-mcast-px-5.3.3
    disk0:asr9k-mgbl-px-5.3.3
    disk0:asr9k-mini-px-5.3.3
    disk0:asr9k-mpls-px-5.3.3
    disk0:asr9k-optic-px-5.3.3
    disk0:asr9k-services-px-5.3.3
    disk0:asr9k-video-px-5.3.3
"""

if __name__ == '__main__':

    sp = SoftwarePackage("disk0:asr9k-mini-px-4.3.2")
    sp = SoftwarePackage("disk0:asr9k-px-5.3.3.09I.CSCus12345-1.0.0")
    sp = SoftwarePackage("disk0:asr9k-px-4.3.2.sp2-1.0.0")
    sp = SoftwarePackage("asr9k-px-5.3.3.CSCux61372-0.0.5.d.pie")
    print(sp.platform)
    print(sp.package_type)
    print(sp.version)
    print(sp.smu)
    print(sp.subversion)
    print(sp.sp)

    l = ["disk0:asr9k-mini-px-4.3.2", "disk0:asr9k-px-5.3.3.09I.CSCus12345-1.0.0"]
    l = ["disk0:asr9k-mini-px-4.3.2", "asr9k-mini-px-4.3.3.pie", "asr9k-px-5.3.3.CSCux61372-0.0.5.d.pie"]
    pkgs = SoftwarePackage.from_package_list(l)

    print(pkgs)
    exit()

    sps1 = SoftwarePackage.from_show_cmd(show_install_active1)
    sps2 = SoftwarePackage.from_show_cmd(show_install_active2)
    from pprint import pprint
    pprint(sps1)
    print
    pprint(sps2)
    print
    pprint(sps1 - sps2)

    print("dupa")
    a1 = SoftwarePackage("disk0:asr9k-video-px-5.3.3")
    a2 = SoftwarePackage("asr9k-px-4.2.0.CSCtx21795.pie")
    print(a2.platform)
    print(a2.composite_name)
    print(a2.architecture)
    print(a2.version)

    print("dupa")
    print(a1 == a2)
