import subprocess
import random
import sys
import json
import os
import time



# CONFIGURATION 
FILE_PATH= "active_ifaces.json"
CONFIG_FILE= "config.json"
LAST_SWITCH_FILE= "/tmp/last_slice_switch.txt"
SWITCH_COOLDOWN= 30  
IMPROVEMENT_THRESHOLD= 10.0  



# prevent continuous switching #


def can_switch_now():
    now = time.time()

    try:
        with open(LAST_SWITCH_FILE, "r") as f:
            last_switch = float(f.read().strip())
    except FileNotFoundError:
        return True

    return (now - last_switch) >= SWITCH_COOLDOWN


def mark_switch_done():
    with open(LAST_SWITCH_FILE, "w") as f:
        f.write(str(time.time()))


#####################################################################################





def load_config():
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
    return {
        "app_type": config.get("APP_TYPE", "latency-critical"),
        "latency_requirement": float(config.get("LATENCY_REQUIREMENT", 50)),
        "violation_threshold": int(config.get("VIOLATION_THRESHOLD", 3)),
        "sample_sleep": float(config.get("SAMPLE_SLEEP", 0)),
    }


def get_active_ifaces():
    with open(FILE_PATH, "r") as f:
        active_ifaces = json.load(f)
    active_ifaces = list(active_ifaces.keys())
    return active_ifaces


def get_current_iface(active_options):
    current_iface = None
    lowest_metric = float("inf")

    result = subprocess.run(
        ["ip", "route", "show", "default"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if "default" in line and "dev" in line:
            parts = line.split()
            iface = parts[parts.index("dev") + 1]
            metric = int(parts[parts.index("metric") + 1]) if "metric" in parts else 0
            if metric < lowest_metric:
                lowest_metric = metric
                current_iface = iface

    if current_iface not in active_options:
        print(f"Current interface {current_iface} is not in active options.")
        return None

    print(f"Current active interface: {current_iface} (metric {lowest_metric})")
    return current_iface




def get_interface_gateway(iface):
    try:
        result = subprocess.run(
            ["ip", "route", "show", "dev", iface],
            capture_output=True, text=True, check=True
        )
        lines = result.stdout.splitlines()

        for line in lines:
            if "default" in line:
                parts = line.split()
                if "via" in parts:
                    return parts[parts.index("via") + 1]

        for line in lines:
            if "scope link" in line:
                parts = line.split()
                subnet = parts[0].split('/')[0]
                octets = subnet.split('.')
                if len(octets) == 4:
                    octets[3] = "1"
                    return ".".join(octets)

        return None
    except subprocess.CalledProcessError:
        return None


def is_interface_up(iface):
    try:
        result = subprocess.run(
            ["ip", "link", "show", iface],
            capture_output=True, text=True, check=True
        )
        return "LOWER_UP" in result.stdout
    except subprocess.CalledProcessError:
        return False

def switch_route_via_metrics(chosen_iface, active_options):
    """Purges all default routes for the specified interfaces only, 
    then sets up the new structured metrics.
    """
    print("Cleaning old default routes for target interfaces")
    
    for iface in active_options.keys():
        while True:
            result = subprocess.run(
                ["sudo", "ip", "route", "del", "default", "dev", iface], 
                capture_output=True
            )
            # When returncode is non-zero, no more default routes exist for this device
            if result.returncode != 0:
                break
        print(f"Cleared default routes from {iface}")

    print("\nInjecting new structured metrics...")
    iface_list = list(active_options.keys())
    
    for iface, gateway in active_options.items():
        if iface == chosen_iface:
            metric = "10"
            status = "PRIMARY"
        else:
            metric = str(101 + iface_list.index(iface) * 10)
            status = "BACKUP"
            
        print(f"   ➜Setting {iface:15} (via {gateway:<15}) to metric {metric:<3} [{status}]")
        
        result = subprocess.run([
            "sudo", "ip", "route", "add", "default", 
            "via", gateway, 
            "dev", iface, 
            "metric", metric
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Warning mapping {iface}: {result.stderr.strip()}", file=sys.stderr)

    print(f"\nSuccess! All system traffic now cleanly obeys {chosen_iface}.")






def select_iface(active_options, kpi_data, app_type, latency_requirement):
    best_iface = None
    best_latency_critical = float("inf")   # for latency-critical and fallback
    best_elastic = float("-inf")            # for elastic
    best_elastic_iface = None

    for iface in active_options.keys():
        entry = kpi_data.get(iface)
        if entry is None or entry.get("status") != "ok":
            continue
        try:
            latency = float(entry["avg"])
        except (KeyError, ValueError):
            continue

        # Always track the global minimum (fallback)
        if latency < best_latency_critical:
            best_latency_critical = latency
            best_iface = iface

        # Track the best elastic candidate (highest latency within bound)
        if latency <= latency_requirement and latency > best_elastic:
            best_elastic = latency
            best_elastic_iface = iface

    if app_type == "latency-critical":
        # Use candidates within bound, fallback to global minimum
        if best_latency_critical <= latency_requirement:
            return best_iface
        else:
            print(" No interface satisfies the latency requirement. Falling back to lowest latency available.")
            return best_iface

    elif app_type == "elastic":
        if best_elastic_iface is not None:
            return best_elastic_iface
        else:
            print(" No interface satisfies the latency requirement. Falling back to lowest latency available.")
            return best_iface

    return None



def main():
    time.sleep(75)
    config = load_config()
    app_type = config["app_type"]
    latency_requirement = config["latency_requirement"]
    violation_threshold = config["violation_threshold"]
    sample_sleep = config["sample_sleep"]

    print(f"App type: {app_type} | Latency requirement: {latency_requirement}ms | Violation threshold: {violation_threshold}")

    # --- Initial interface scan ---
    print("\nScanning interfaces for default gateways...")
    active_options = {}
    MY_INTERFACES = get_active_ifaces()
    print(f"Interfaces to check: {MY_INTERFACES}")

    for iface in MY_INTERFACES:
        gw = get_interface_gateway(iface)
        if gw and is_interface_up(iface):
            active_options[iface] = gw
            print(f"   -> Found {iface:6} gateway: {gw}")
        else:
            print(f"   {iface:6} is disconnected or has no detectable gateway. Skipping.")

    if not active_options:
        print("\nError: No active networks with valid gateways were found!", file=sys.stderr)
        sys.exit(1)

    current_iface = get_current_iface(active_options)
    violation_count = 0

    # --- Main monitoring loop ---
    while True:
        time.sleep(sample_sleep)

        with open(FILE_PATH, "r") as f:
            latency_data = json.load(f)

        # Check if current interface is violating the latency requirement
        if current_iface is None:
            violation_count = violation_threshold
        else:
            current_entry = latency_data.get(current_iface)
            if current_entry is None or current_entry.get("status") != "ok":
                print(f"WARNING: Current interface {current_iface} has no valid latency data.")
                violation_count += 1
            else:
                current_latency = float(current_entry["avg"])
                if current_latency > latency_requirement:
                    violation_count += 1
                    print(f"Violation {violation_count}/{violation_threshold} on {current_iface}: {current_latency:.3f}ms > {latency_requirement}ms")
                else:
                    violation_count = 0  # Reset on a good sample

        if violation_count >= violation_threshold:
            print(f"\nViolation threshold reached. Selecting new interface...")
            violation_count = 0

            best_iface = select_iface(active_options, latency_data, app_type, latency_requirement)

            if best_iface == current_iface:
                print(f"Best interface is still {current_iface}. No switch needed.")

            elif not can_switch_now():
                print("Switch cooldown active. No switch.")

            else:
                current_entry = latency_data.get(current_iface)
                current_latency = float(current_entry["avg"]) if current_entry and current_entry.get("status") == "ok" else float("inf")
                best_latency = float(latency_data[best_iface]["avg"])

                improvement = current_latency - best_latency

                if improvement < IMPROVEMENT_THRESHOLD:
                    print(
                        f"No switch: improvement ({improvement:.3f} ms) "
                        f"is below threshold ({IMPROVEMENT_THRESHOLD} ms)."
                    )
                else:
                    print(f"Switching from {current_iface} -> {best_iface}")
                    current_iface = best_iface
                    switch_route_via_metrics(current_iface, active_options)
                    mark_switch_done()




if __name__ == "__main__":
    if subprocess.run(["id", "-u"], capture_output=True).stdout.decode().strip() != "0":
        print("This script must be run with sudo privileges", file=sys.stderr)
        sys.exit(1)

    main()
