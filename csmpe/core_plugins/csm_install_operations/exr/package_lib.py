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

"""
NCS6K

Production Packages

External Names                                Internal Names
ncs6k-doc.pkg-5.2.4                           ncs6k-doc-5.2.4
ncs6k-li.pkg-5.2.4                            ncs6k-li-5.2.4
ncs6k-mcast.pkg-5.2.4                         ncs6k-mcast-5.2.4
ncs6k-mgbl.pkg-5.2.4                          ncs6k-mgbl-5.2.4
ncs6k-mini-x.iso-5.2.4                        ncs6k-xr-5.2.5
ncs6k-mpls.pkg-5.2.4                          ncs6k-mpls-5.2.4
ncs6k-sysadmin.iso-5.2.4                      ncs6k-sysadmin-5.2.4
ncs6k-full-x.iso-5.2.4
ncs6k-5.2.5.CSCuy47880.smu                    ncs6k-5.2.5.CSCuy47880-1.0.0

Engineering Packages

External Names                                Internal Names
ncs6k-mcast.pkg-5.2.5.47I.DT_IMAGE            ncs6k-mcast-5.2.5.47I
ncs6k-mini-x.iso-6.1.0.07I.DT_IMAGE           ncs6k-xr-5.2.5.47I
ncs6k-5.2.5.47I.CSCuy47880-0.0.4.i.smu        ncs6k-5.2.5.47I.CSCuy47880-0.0.4.i

ASR9K

Production Packages - not finalized yet

External Names                                Internal Names
asr9k-mcast-x64-2.0.0.0-r61116I.x86_64.rpm    asr9k-mcast-x64-2.0.0.0-r61117I
asr9k-bgp-x64-1.0.0.0-r61116I.x86_64.rpm      asr9k-bgp-x64-1.0.0.0-r61116I
asr9k-mgbl-x64-3.0.0.0-r61116I.x86_64.rpm     asr9k-mgbl-x64-3.0.0.0-r61117I
asr9k-full-x64.iso-6.1.1.16I                  asr9k-xr-6.1.1.17I
asr9k-mini-x64.iso-6.1.1.16I                  asr9k-xr-6.1.1.17I

Engineering Packages

External Names                                                          Internal Names
asr9k-mcast-x64-2.0.0.0-r61116I.x86_64.rpm-6.1.1.16I.DT_IMAGE           asr9k-mcast-x64-2.0.0.0-r61117I
asr9k-bgp-x64-1.0.0.0-r61116I.x86_64.rpm-6.1.1.16I.DT_IMAGE             asr9k-bgp-x64-1.0.0.0-r61116I
asr9k-mgbl-x64-3.0.0.0-r61116I.x86_64.rpm-6.1.1.16I.DT_IMAGE            asr9k-mgbl-x64-3.0.0.0-r61117I
asr9k-full-x64.iso-6.1.1.16I.DT_IMAGE                                   asr9k-xr-6.1.1.17I
asr9k-mini-x64.iso-6.1.1.16I.DT_IMAGE                                   asr9k-xr-6.1.1.17I

"""

platforms = ["ncs6k", "asr9k"]
package_types = {"ncs6k": "sysadmin full mini mcast mgbl mpls k9sec doc li xr".split(),
                 "asr9k": "bgp eigrp full isis k9sec li m2m mcast mgbl mini xr mpls-te-rsvp mpls optic ospf parser".split()
                 }
version_regexs = {"ncs6k": re.compile("(?P<VERSION>\d+\.\d+\.\d+(\.\d+\w+)?)"),   # 5.2.4 or 5.2.4.47I
                  # 61117I or 611 or 6.1.1.17I or 6.1.1
                  "asr9k": re.compile("(?P<VERSION>(\d+\d+\d+(\d+\w+)?)|(\d+\.\d+\.\d+(\.\d+\w+)?)(?!\.\d)(?!-))")
                  }
smu_re = re.compile("(?P<SMU>CSC[a-z]{2}\d{5})")
subversion_regexs = {"ncs6k": re.compile("CSC.*(?P<SUBVERSION>\d+\.\d+\.\d+?)"),  # 0.0.4
                     "asr9k": re.compile("-(?P<SUBVERSION>\d+\.\d+\.\d+\.\d+)-")   # 2.0.0.0
                     }


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
        if not self.platform or not package_types.get(self.platform):
            return None
        for package_type in package_types.get(self.platform):
            if "-" + package_type + "-" in self.package_name:
                return package_type
        else:
            return None

    @property
    def version(self):
        if not self.platform or not version_regexs.get(self.platform):
            return None
        result = re.search(version_regexs.get(self.platform), self.package_name)

        return result.group("VERSION") if result else None

    @property
    def smu(self):
        result = re.search(smu_re, self.package_name)
        return result.group("SMU") if result else None

    @property
    def subversion(self):
        if not self.platform or not subversion_regexs.get(self.platform):
            return None
        if self.platform == "asr9k" or self.smu:
            result = re.search(subversion_regexs.get(self.platform), self.package_name)
            return result.group("SUBVERSION") if result else None
        return None

    def is_valid(self):
        return self.platform and self.version and (self.package_type or self.smu)

    def __eq__(self, other):
        package_type_same = False
        if (self.package_type == "xr" or self.package_type == "mini" or self.package_type == "full") and \
           (other.package_type == "xr" or other.package_type == "mini" or other.package_type == "full"):
            package_type_same = True

        result = self.platform == other.platform and \
            (package_type_same or self.package_type == other.package_type) and \
            self.version == other.version and \
            self.smu == other.smu and \
            (self.subversion == other.subversion if self.subversion and other.subversion else True)

        return result

    def __hash__(self):
        return hash("{}{}{}{}{}".format(
            self.platform, self.package_type, self.version, self.smu, self.subversion))

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
