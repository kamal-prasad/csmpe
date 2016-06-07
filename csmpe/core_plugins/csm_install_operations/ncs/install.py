# coding=utf-8
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
import time
import itertools

install_error_pattern = re.compile("Error:    (.*)$", re.MULTILINE)

csm_ctx = None


def log_install_errors(ctx, output):
        errors = re.findall(install_error_pattern, output)
        for line in errors:
            ctx.warning(line)


def watch_operation(ctx, op_id=0):
    """
    Watch for the non-reload situation.  Upon issuing add/activate/commit/remove/deactivate, the install operation
    will be executed in the background.  The following message

    Install operation will continue in the background

    will be displayed.  After some time elapses, a successful or abort message will be displayed.

    The CLI command, 'show install request' is used in the loop to report the progress percentages.  Upon
    completion, 'show install request' returns 'No install operation in progress'.  The watch_operation will be
    done at that point.

    As an example,

    RP/0/RP0/CPU0:Deploy#install deactivate ncs6k-5.2.5.CSCuz65240-1.0.0
    May 31 20:14:14 Install operation 3 started by root:
      install deactivate pkg ncs6k-5.2.5.CSCuz65240-1.0.0
    May 31 20:14:14 Package list:
    May 31 20:14:14     ncs6k-5.2.5.CSCuz65240-1.0.0
    May 31 20:14:20 Install operation will continue in the background

    <--- Time Lapse --->

    RP/0/RP0/CPU0:Deploy#May 31 20:15:10 Install operation 3 finished successfully

    ------------------------------------------------------------------------------------------------------------
    RP/0/RP0/CPU0:Deploy#show install request
    The install operation 17 is 30% complete

    or

    RP/0/RP0/CPU0:Deploy#show install request
    No install operation in progress

    When install is completed, the following message will be displayed

    ------------------------------------------------------------------------------------------------------------
    If the install operation is successful, the following message will be displayed.

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


def parse_show_platform(output):
    """
    Platform: NCS6K
    RP/0/RP0/CPU0:Deploy#show platform
    Node              Type                       State             Config state
    --------------------------------------------------------------------------------
    0/2/CPU0          NC6-10X100G-M-P            IOS XR RUN        NSHUT
    0/RP0/CPU0        NC6-RP(Active)             IOS XR RUN        NSHUT
    0/RP1/CPU0        NC6-RP(Standby)            IOS XR RUN        NSHUT

    Platform: ASR9K-X64

    """
    inventory = {}
    lines = output.split('\n')
    for line in lines:
        line = line.strip()
        if len(line) > 0 and line[0].isdigit():
            states = re.split('\s\s+', line)

            if not re.search('CPU\d+$', states[0]):
                continue

            node, node_type, state, config_state = states

            entry = {
                'type': node_type,
                'state': state,
                'config_state': config_state
            }
            inventory[node] = entry

    return inventory


def validate_node_state(inventory):
    valid_state = [
        'IOS XR RUN',
        'PRESENT',
        'READY',
        'FAILED',
        'OK',
        'DISABLED',
        'UNPOWERED',
        'ADMIN DOWN',
        'OPERATIONAL',
        'NOT ALLOW ONLIN',  # This is not spelling error
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

    cmd = "show platform"
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
            inventory = parse_show_platform(output)
            if validate_node_state(inventory):
                ctx.info("All nodes in desired state")
                return True

    # Some nodes did not come to run state
    ctx.error("Not all nodes have came up: {}".format(output))
    # this will never be executed
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

    if op_success in output:
        watch_operation(ctx, op_id)
        report_install_status(ctx, op_id)
    else:
        log_install_errors(ctx, output)
        ctx.error("Operation {} failed".format(op_id))


def get_op_id(output):
    """
    :param output: Output from the install command
    :return: the operational ID
    """
    result = re.search('Install operation (\d+)', output)
    if result:
        return result.group(1)
    return -1


def report_install_status(ctx, op_id):
    """
    :param ctx: CSM Context object
    :param op_id: operational ID
    Peeks into the install log to see if the install operation is successful or not
    """
    failed_oper = r'Install operation {} aborted'.format(op_id)
    output = ctx.send("show install log {} detail".format(op_id))
    if re.search(failed_oper, output):
        log_install_errors(ctx, output)
        ctx.error("Operation {} failed".format(op_id))

    ctx.info("Operation {} finished successfully".format(op_id))


def handle_aborted(fsm_ctx):
    """
    :param ctx: FSM Context
    :return: True if successful other False
    """
    global csm_ctx

    report_install_status(ctx=csm_ctx, op_id=get_op_id(fsm_ctx.ctrl.before))

    # Indicates the failure
    return False


def handle_non_reload_activate_deactivate(fsm_ctx):
    """
    :param ctx: FSM Context
    :return: True if successful other False
    """
    global csm_ctx

    op_id = get_op_id(fsm_ctx.ctrl.before)
    if op_id == -1:
        return False

    watch_operation(csm_ctx, op_id)
    report_install_status(csm_ctx, op_id)

    return True


def handle_reload_activate_deactivate(fsm_ctx):
    """
    :param ctx: FSM Context
    :return: True if successful other False
    """
    global csm_ctx

    op_id = get_op_id(fsm_ctx.ctrl.before)
    if op_id == -1:
        return False

    watch_operation(csm_ctx, op_id)
    success = wait_for_reload(csm_ctx)
    if not success:
        csm_ctx.error("Reload or boot failure")
        return

    csm_ctx.info("Operation {} finished successfully".format(op_id))

    return True


def install_activate_deactivate(ctx, cmd):
    """
    Abort Situation:
    RP/0/RP0/CPU0:Deploy#install activate ncs6k-5.2.5.CSCuz65240-1.0.0

    Jun 02 20:19:31 Install operation 8 started by root:
      install activate pkg ncs6k-5.2.5.CSCuz65240-1.0.0
    Jun 02 20:19:31 Package list:
    Jun 02 20:19:31     ncs6k-5.2.5.CSCuz65240-1.0.0
    Jun 02 20:19:31     ncs6k-5.2.5.47I.CSCuy47880-0.0.4.i
    Jun 02 20:19:31     ncs6k-5.2.5.CSCux82987-1.0.0
    Jun 02 20:19:38 Install operation 8 aborted

    ------------------------------------------------------------------------------------------------------------
    Non-Reload Situation:

    RP/0/RP0/CPU0:Deploy#install deactivate ncs6k-5.2.5.CSCuz65240-1.0.0
    May 31 20:14:14 Install operation 3 started by root:
      install deactivate pkg ncs6k-5.2.5.CSCuz65240-1.0.0
    May 31 20:14:14 Package list:
    May 31 20:14:14     ncs6k-5.2.5.CSCuz65240-1.0.0
    May 31 20:14:20 Install operation will continue in the background

    <--- Time Lapses --->

    RP/0/RP0/CPU0:Deploy#May 31 20:15:10 Install operation 3 finished successfully

    ------------------------------------------------------------------------------------------------------------
    Reload Situation:

    RP/0/RP0/CPU0:Deploy#install activate ncs6k-5.2.5.CSCux82987-1.0.0
    May 31 20:17:08 Install operation 4 started by root:
      install activate pkg ncs6k-5.2.5.CSCux82987-1.0.0
    May 31 20:17:08 Package list:
    May 31 20:17:08     ncs6k-5.2.5.CSCux82987-1.0.0

    <--- Time Lapses --->

    This install operation will reboot the sdr, continue?
     [yes/no]:[yes] <Hit Enter>
    May 31 20:17:47 Install operation will continue in the background

    <--- Time Lapses --->

    RP/0/RP0/CPU0:Deploy#May 31 20:18:44 Install operation 4 finished successfully

    <--- Router Starts Reloading --->

    Connection closed by foreign host.
    """
    global csm_ctx
    csm_ctx = ctx

    ABORTED = re.compile("aborted")

    # Seeing this message without the reboot prompt indicates a non-reload situation
    CONTINUE_IN_BACKGROUND = re.compile("Install operation will continue in the background")

    REBOOT_PROMPT = re.compile("This install operation will reboot the sdr, continue")

    events = [CONTINUE_IN_BACKGROUND, REBOOT_PROMPT, ABORTED]
    transitions = [
        (CONTINUE_IN_BACKGROUND, [0], -1, handle_non_reload_activate_deactivate, 20),
        (REBOOT_PROMPT, [0], -1, handle_reload_activate_deactivate, 20),
        (ABORTED, [0], -1, handle_aborted, 20),
    ]

    if not ctx.run_fsm("activate or deactivate", cmd, events, transitions, timeout=60):
        ctx.error("Failed: {}".format(cmd))
