# =============================================================================
# Copyright (c) 2016, Cisco Systems, Inc
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
import os
import ftplib
import shutil

from csmpe.core_plugins.csm_install_operations.utils import ServerType
from csmpe.core_plugins.csm_install_operations.utils import import_module
from csmpe.core_plugins.csm_install_operations.utils import concatenate_dirs


def get_server_impl(server):
    if server.server_type == ServerType.TFTP_SERVER:
        return TFTPServer(server)
    elif server.server_type == ServerType.FTP_SERVER:
        return FTPServer(server)
    elif server.server_type == ServerType.SFTP_SERVER:
        return SFTPServer(server)
    else:
        return None


class ServerImpl(object):
    def __init__(self, server):
        self.server = server

    """
    Upload file to the designated server repository.
    source_file_path - complete path to the source file
    dest_filename - filename on the server repository
    sub_directory - sub-directory under the server repository
    """
    def upload_file(self, source_file_path, dest_filename, sub_directory=None, callback=None):
        raise NotImplementedError("Children must override upload_file")


class TFTPServer(ServerImpl):
    def __init__(self, server):
        ServerImpl.__init__(self, server)

    def upload_file(self, source_file_path, dest_filename, sub_directory=None, callback=None):
        if sub_directory is None:
            path = self.server.server_directory
        else:
            path = (self.server.server_directory + os.sep + sub_directory)

        shutil.copy(source_file_path, path + os.sep + dest_filename)


class FTPServer(ServerImpl):
    def __init__(self, server):
        ServerImpl.__init__(self, server)

    def upload_file(self, source_file_path, dest_filename, sub_directory=None, callback=None):
        try:
            file = open(source_file_path, 'rb')

            ftp = ftplib.FTP(self.server.server_url, user=self.server.username, passwd=self.server.password)

            remote_directory = concatenate_dirs(self.server.server_directory, sub_directory)
            if len(remote_directory) > 0:
                ftp.cwd(remote_directory)

            # default block size is 8912
            if callback:
                ftp.storbinary('STOR ' + dest_filename, file, callback=callback)
            else:
                ftp.storbinary('STOR ' + dest_filename, file)
            ftp.quit()
            file.close()

        finally:
            if file is not None:
                file.close()


class SFTPServer(ServerImpl):
    def __init__(self, server):
        ServerImpl.__init__(self, server)

    def upload_file(self, source_file_path, dest_filename, sub_directory=None, callback=None):
        sftp_module = import_module('pysftp')

        with sftp_module.Connection(self.server.server_url, username=self.server.username, password=self.server.password) as sftp:
            remote_directory = concatenate_dirs(self.server.server_directory, sub_directory)
            if len(remote_directory) > 0:
                sftp.chdir(remote_directory)
            if callback:
                sftp.put(source_file_path, remotepath=remote_directory + '/' + dest_filename, callback=callback)
            else:
                sftp.put(source_file_path, remotepath=remote_directory + '/' + dest_filename)
