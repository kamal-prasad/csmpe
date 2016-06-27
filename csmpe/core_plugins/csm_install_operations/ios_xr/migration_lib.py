import time
import re
import json

SUPPORTED_HW_JSON = "./asr9k_64bit/migration_supported_hw.json"

ADMIN_RP = "\d+/RS?P\d+"
ADMIN_LC = "\d+/\d+"


def log_and_post_status(ctx, msg):
    ctx.info(msg)
    ctx.post_status(msg)


def parse_exr_admin_show_platform(output):
    """Get all RSP/RP/LC string node names matched with the card type."""
    inventory = {}
    lines = output.split('\n')

    for line in lines:
        line = line.strip()
        if len(line) > 0 and line[0].isdigit():
            node = line[:10].strip()
            print "node = *{}*".format(node)
            node_type = line[10:34].strip(),
            print "node_type = *{}*".format(node_type)
            inventory[node] = node_type
    return inventory


def get_all_supported_nodes(ctx, supported_cards):
    """Get the list of string node names(all available RSP/RP/LC) that are supported for migration."""
    supported_nodes = []
    ctx.send("admin")
    output = ctx.send("show platform")
    inventory = parse_exr_admin_show_platform(output)

    rp_pattern = re.compile(ADMIN_RP)
    lc_pattern = re.compile(ADMIN_LC)
    supported_rp = supported_cards.get("RP")
    if not supported_rp:
        ctx.error("Missing supported hardware information for RP in {}.".format(SUPPORTED_HW_JSON))

    supported_lc = supported_cards.get("LC")
    if not supported_lc:
        ctx.error("Missing supported hardware information for LC in {}.".format(SUPPORTED_HW_JSON))

    for node, node_type in inventory.items():
        if rp_pattern.match(node):
            for rp in supported_rp:
                if rp in node_type:
                    supported_nodes.append(node)
                    break
        elif lc_pattern.match(node):
            for lc in supported_lc:
                if lc in node_type:
                    supported_nodes.append(node)
                    break
    ctx.send("exit")
    return supported_nodes


def get_version(ctx):
    output = ctx.send("show version | include Version")
    version = re.search("Version\s*?(\d+\.\d+\.\d+)(?:\.\d+I)?", output)
    if not version:
        ctx.error("Failure to retrieve release number.")
    return version.group(1)


def wait_for_final_band(ctx):
    """This is for ASR9K eXR. Wait for all present nodes to come to FINAL Band."""
    exr_version = get_version(ctx)
    with open(SUPPORTED_HW_JSON) as supported_hw_file:
        supported_hw = json.load(supported_hw_file)
    if supported_hw.get(exr_version) is None:
        ctx.error("No hardware support information available for release {}.".format(exr_version))

    supported_nodes = get_all_supported_nodes(ctx, supported_hw.get(exr_version))
    # Wait for all nodes to Final Band
    timeout = 1200
    poll_time = 20
    time_waited = 0

    cmd = "show platform vm"
    while 1:
        # Wait till all nodes are in FINAL Band
        time_waited += poll_time
        if time_waited >= timeout:
            break
        time.sleep(poll_time)
        output = ctx.send(cmd)
        all_nodes_present = True
        for node in supported_nodes:
            if node not in output:
                all_nodes_present = False
                break
            print "supported node that is in show platform vm = " + str(node)
        if all_nodes_present and check_sw_status(output):
            return True

    # Some nodes did not come to FINAL Band
    return False


def check_sw_status(output):
    """Check is a node has FINAL Band status"""
    lines = output.splitlines()

    for line in lines:
        line = line.strip()
        if len(line) > 0 and line[0].isdigit():
            sw_status = line[48:64].strip()
            if "FINAL Band" not in sw_status:
                return False
    return True
