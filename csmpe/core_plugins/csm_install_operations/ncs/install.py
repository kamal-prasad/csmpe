# =============================================================================
#
# Copyright (c) 2016, Cisco Systems
# All rights reserved.
#
# # Author: Klaudiusz Staniek
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
import itertools

install_error_pattern = re.compile("Error:    (.*)$", re.MULTILINE)


def log_install_errors(ctx, output):
        errors = re.findall(install_error_pattern, output)
        for line in errors:
            ctx.warning(line)


def watch_operation(ctx, op_id=0):
        """
        RP/0/RP0/CPU0:Deploy#show install request
        The install operation 17 is 30% complete

        or

        RP/0/RP0/CPU0:Deploy#show install request
        No install operation in progress

        When install is completed, the following message will be displayed
        RP/0/RP0/CPU0:Deploy#May 24 22:25:43 Install operation 17 finished successfully
        """
        no_install = r"No install operation in progress"
        op_progress = r"The install operation {} is (\d+)% complete".format(op_id)
        success = "Install operation {} finished successfully".format(op_id)

        cmd_show_install_request = "show install request"
        ctx.info("Watching the operation {} to complete".format(op_id))

        last_status = None
        finish = False
        while not finish:
            try:
                # this is to catch the successful operation as soon as possible
                ctx.send("", wait_for_string=success, timeout=20)
                finish = True
            except ctx.CommandTimeoutError:
                pass

            message = ""
            output = ctx.send(cmd_show_install_request)
            if op_id in output:
                result = re.search(op_progress, output)
                if result:
                    status = result.group(0)
                    message = "{}".format(status)

                if message != last_status:
                    ctx.post_status(message)
                    last_status = message

            if no_install in output:
                break

        return output


def parse_xr_show_platform(output):
    inventory = {}
    lines = output.split('\n')

    for line in lines:
        line = line.strip()
        if len(line) > 0 and line[0].isdigit():
            node = line[:15].strip()
            entry = {
                'type': line[16:41].strip(),
                'state': line[42:58].strip(),
                'config_state': line[59:].strip()
            }
            inventory[node] = entry
    return inventory


def validate_xr_node_state(inventory):
    valid_state = [
        'IOS XR RUN',
        'PRESENT',
        'UNPOWERED',
        'READY',
        'UNPOWERED',
        'FAILED',
        'OK',
        'ADMIN DOWN',
        'DISABLED'
    ]
    for key, value in inventory.items():
        if 'CPU' in key:
            if value['state'] not in valid_state:
                break
    else:
        return True
    return False


def wait_for_reload(ctx):
    """
     Wait for system to come up with max timeout as 25 Minutes

    """
    ctx.disconnect()
    time.sleep(60)

    ctx.reconnect(max_timeout=1500)  # 25 * 60 = 1500
    timeout = 3600
    poll_time = 30
    time_waited = 0
    xr_run = "IOS XR RUN"

    cmd = "admin show platform"
    ctx.info("Waiting for all nodes to come up")
    ctx.post_status("Waiting for all nodes to come up")
    time.sleep(100)
    while 1:
        # Wait till all nodes are in XR run state
        time_waited += poll_time
        if time_waited >= timeout:
            break
        time.sleep(poll_time)
        output = ctx.send(cmd)
        if xr_run in output:
            inventory = parse_xr_show_platform(output)
            if validate_xr_node_state(inventory):
                ctx.info("All nodes in desired state")
                return True

    # Some nodes did not come to run state
    ctx.error("Not all nodes have came up: {}".format(output))
    # this will never be executed
    return False


def watch_install(ctx, oper_id, cmd):
    # FIXME: Add description

    """

    """
    success_oper = r'Install operation (\d+) completed successfully'
    completed_with_failure = 'Install operation (\d+) completed with failure'
    failed_oper = r'Install operation (\d+) failed'
    failed_incr = r'incremental.*parallel'
    # restart = r'Parallel Process Restart'
    install_method = r'Install [M|m]ethod: (.*)'
    op_success = "The install operation will continue asynchronously"

    watch_operation(ctx, oper_id)

    output = ctx.send("admin show install log {} detail".format(oper_id))
    if re.search(failed_oper, output):
        if re.search(failed_incr, output):
            ctx.info("Retrying with parallel reload option")
            cmd += " parallel-reload"
            output = ctx.send(cmd)
            if op_success in output:
                result = re.search('Install operation (\d+) \'', output)
                if result:
                    op_id = result.group(1)
                    watch_operation(ctx, op_id)
                    output = ctx.send("admin show install log {} detail".format(oper_id))
                else:
                    log_install_errors(ctx, output)
                    ctx.error("Operation ID not found")
                    return
        else:
            log_install_errors(ctx, output)
            ctx.error(output)
            return

    result = re.search(install_method, output)
    if result:
        restart_type = result.group(1).strip()
        ctx.info("{} Pending".format(restart_type))
        if restart_type == "Parallel Reload":
            if re.search(completed_with_failure, output):
                ctx.info("Install completed with failure, going for reload")
            elif re.search(success_oper, output):
                ctx.info("Install completed successfully, going for reload")
            return wait_for_reload(ctx)
        elif restart_type == "Parallel Process Restart":
            return True

    log_install_errors(ctx, output)
    return False


def install_add_remove(ctx, cmd, has_tar=False):
    """
    Success Condition:
    ADD:
    install add source tftp://223.255.254.254/auto/tftpboot-users/alextang/ ncs6k-mpls.pkg-6.1.0.07I.DT_IMAGE
    May 24 18:54:12 Install operation will continue in the background
    RP/0/RP0/CPU0:Deploy#May 24 18:54:30 Install operation 12 finished successfully

    REMOVE:
    RP/0/RP0/CPU0:Deploy#install remove ncs6k-5.2.5.47I.CSCux97367-0.0.15.i
    May 23 21:20:28 Install operation 2 started by root:
      install remove ncs6k-5.2.5.47I.CSCux97367-0.0.15.i
    May 23 21:20:28 Package list:
    May 23 21:20:28     ncs6k-5.2.5.47I.CSCux97367-0.0.15.i
    May 23 21:20:29 Install operation will continue in the background
    RP/0/RP0/CPU0:Deploy#May 23 21:20:29 Install operation 2 finished successfully

    Failed Condition:
    RP/0/RSP0/CPU0:CORFU#install remove ncs6k-5.2.5.47I.CSCux97367-0.0.15.i
    Mon May 23 22:57:45.078 UTC
    May 23 22:57:46 Install operation 28 started by iox:
      install remove ncs6k-5.2.5.47I.CSCux97367-0.0.15.i
    May 23 22:57:46 Package list:
    May 23 22:57:46     ncs6k-5.2.5.47I.CSCux97367-0.0.15.i
    May 23 22:57:47 Install operation will continue in the background
    RP/0/RSP0/CPU0:CORFU#May 23 22:57:48 Install operation 28 aborted
    """

    # message = "Waiting the operation to continue asynchronously"
    # ctx.info(message)
    # ctx.post_status(message)

    output = ctx.send(cmd, timeout=7200)
    result = re.search('Install operation (\d+)', output)
    if result:
        op_id = result.group(1)
        if has_tar is True:
            ctx.operation_id = op_id
            ctx.info("The operation {} stored".format(op_id))
    else:
        ctx.log_install_errors(output)
        ctx.error("Operation failed")
        return  # for sake of clarity

    op_success = "Install operation will continue in the background"
    failed_oper = r'Install operation {} aborted'.format(op_id)

    if op_success in output:
        watch_operation(ctx, op_id=op_id)
        output = ctx.send("show install log {} detail".format(op_id))
        if re.search(failed_oper, output):
            log_install_errors(ctx, output)
            ctx.error("Operation {} failed".format(op_id))
            return  # for same of clarity

        ctx.info("Operation {} finished successfully".format(op_id))
        return  # for sake of clarity
    else:
        log_install_errors(ctx, output)
        ctx.error("Operation {} failed".format(op_id))


def install_activate_deactivate(ctx, cmd):
    message = "Waiting the operation to continue asynchronously"
    ctx.info(message)
    ctx.post_status(message)

    op_success = "The install operation will continue asynchronously"
    output = ctx.send(cmd, timeout=7200)
    result = re.search('Install operation (\d+) \'', output)
    if result:
        op_id = result.group(1)
    else:
        log_install_errors(ctx, output)
        ctx.error("Operation failed")
        return

    if op_success in output:
        success = watch_install(ctx, op_id, cmd)
        if not success:
            ctx.error("Reload or boot failure")
            return

        ctx.info("Operation {} finished successfully".format(op_id))
        return
    else:
        ctx.log_install_errors(output)
        ctx.error("Operation {} failed".format(op_id))
        return
