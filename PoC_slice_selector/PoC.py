import subprocess
import json
import sys
import time
import threading
import os
import re
from datetime import datetime


CONFIG_FILE = "config.json"

try:
    with open(CONFIG_FILE, 'r') as f:
        config_data = json.load(f)
        # The destination IP address to ping
        TARGET = config_data.get("TARGET", "8.8.8.8")
        # Number of ping packets to send per iteration
        PING_COUNT = str(config_data.get("PING_COUNT", "5"))
        # Maximum time to wait for a ping response (in seconds)
        PING_TIMEOUT = str(config_data.get("PING_TIMEOUT", "1"))
        # Delay between ping iterations per interface (in seconds)
        SAMPLE_SLEEP = float(config_data.get("SAMPLE_SLEEP", 1))
        # How frequently the dashboard UI refreshes (in seconds)
        REFRESH = float(config_data.get("REFRESH", 1))


        PING_INTERVAL = str(config_data.get("PING_INTERVAL", "0.5"))



        
except (FileNotFoundError, json.JSONDecodeError):
    print(f"Warning: Could not read {CONFIG_FILE}. Defaulting to TARGET 8.8.8.8 and default params")
    TARGET = "8.8.8.8"
    PING_COUNT = "5"
    PING_TIMEOUT = "1"
    PING_INTERVAL = "0.5"
    SAMPLE_SLEEP = 1
    REFRESH = 1




dashboard_state = {}
state_lock = threading.Lock()

def get_interfaces_and_ips():
    """Retrieves a JSON list of interfaces and IPv4 addresses using the 'ip' command."""
    try:
        result = subprocess.run(
            # ['ip', '-j', '-4', 'addr', 'show'], 
            ['ip', '-j',  'addr', 'show'], 
            capture_output=True, 
            text=True, 
            check=True
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Error: Ensure you are on Linux and the 'ip' command is installed. Details: {e}")
        sys.exit(1)

def collector_loop(ifname, target, csv_file):
    """Runs continuously in a background thread to gather ping metrics."""
    while True:
        if ifname is not None and ifname != "DEFAULT_GW":
            cmd = ['ping', '-c', PING_COUNT, '-W', PING_TIMEOUT,'-i', PING_INTERVAL, '-I', ifname, target]
        else:
            cmd = ['ping', '-c', PING_COUNT, '-W', PING_TIMEOUT, '-s', '2500', target]
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout + result.stderr
        
        # Parse packet loss (e.g. "0% packet loss")
        loss_match = re.search(r'([\d.]+)%\s*packet loss', output)
        loss = loss_match.group(1) if loss_match else "100"
        
        avg = "999999"
        status = "ok"
        
        # Parse average latency (e.g. "rtt min/avg/max/mdev = 1.2/3.4/5.6/7.8 ms")
        rtt_match = re.search(r'=\s*[\d.]+/([\d.]+)/[\d.]+/[\d.]+\s*ms', output)
        if rtt_match:
            avg = rtt_match.group(1)
            
        if loss == "100":
            status = "no-reply"
        elif avg == "999999":
            status = "no-rtt"
            
        ts = datetime.now().strftime('%H:%M:%S')
        
        # Safely update the global dashboard state
        with state_lock:
            dashboard_state[ifname] = {
                'ts': ts,
                'avg': avg,
                'loss': loss,
                'status': status,
                "ip": dashboard_state[ifname].get('ip', '-')  # Preserve existing IP if available
            }
            
        # Write to local CSV
        with open(csv_file, 'a') as f:
            f.write(f"{ts},{ifname},{avg},{loss},{status}\n")
            
        time.sleep(SAMPLE_SLEEP)

def check_active_interfaces(active_ifaces):
    """Periodically checks which interfaces are active and updates the dashboard state."""
    while True:
        interfaces_data = get_interfaces_and_ips()
        current_ifaces = {iface.get('ifname') for iface in interfaces_data if iface.get('ifname') != 'lo'}
        
        with state_lock:
            # Remove interfaces that are no longer active
            for ifname in list(dashboard_state.keys()):
                if ifname not in current_ifaces and ifname != "DEFAULT_GW":
                    print(f"Interface {ifname} is no longer active. Removing from dashboard.")
                    del dashboard_state[ifname]
                    if ifname in active_ifaces:
                        active_ifaces.remove(ifname)
            
            # Add new active interfaces
            for ifname in current_ifaces:
                if ifname not in dashboard_state:
                    print(f"New interface detected: {ifname}. Adding to dashboard.")
                    dashboard_state[ifname] = {'ts': '-', 'avg': '...', 'loss': '...', 'status': 'warming'}
                    active_ifaces.append(ifname)
        
        with open("active_ifaces.json", 'w') as f:
            dump_json={}
            for ifname in active_ifaces:
                if ifname is not None and ifname != "DEFAULT_GW":
                    st = dashboard_state.get(ifname, {})
                    if st.get('status') in ['ok']:
                        dump_json[ifname] = st
            json.dump(dump_json, f, indent=4)


        time.sleep(5)  # Check every 5 seconds



def main():
    interfaces_data = get_interfaces_and_ips()
    active_ifaces = []
    print(interfaces_data)
    for iface in interfaces_data:
        ifname = iface.get('ifname')
        print(f"Checking interface: {ifname}")
        
        if ifname == 'lo':
            continue  
        
        addr_info = iface.get('addr_info', [])
        # if not addr_info:
        #     continue

        ipv4_addrs = [addr.get('local') for addr in addr_info if addr.get('family') == 'inet']
        if not ipv4_addrs:
            continue
        print(f"Found interface: {ifname} with addresses: {[addr.get('local') for addr in addr_info]}")
        active_ifaces.append(ifname)



        dashboard_state[ifname] = {'ts': '-', 'avg': '...', 'loss': '...', 'status': 'warming',"ip": ipv4_addrs[0]}

    # add default gw interface
    active_ifaces.append("DEFAULT_GW")
    dashboard_state["DEFAULT_GW"] = {'ts': '-', 'avg': '...', 'loss': '...', 'status': 'warming'}
        
    if not active_ifaces:
        print("ERROR: No active network interfaces found.")
        sys.exit(1)
        
    base_dir = os.path.dirname(os.path.abspath(__file__))
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = os.path.join(base_dir, "results", f"latency_dashboard_{run_id}")
    os.makedirs(run_dir, exist_ok=True)
    csv_file = os.path.join(run_dir, "results.csv")
    
    with open(csv_file, 'w') as f:
        f.write("timestamp,iface,latency_ms,packet_loss_pct,status\n")

    # Start background collection threads
    for ifname in active_ifaces:
        t = threading.Thread(target=collector_loop, args=(ifname, TARGET, csv_file), daemon=True)
        t.start()

    t = threading.Thread(target=check_active_interfaces, args=(active_ifaces,), daemon=True)
    t.start()

    # Dashboard Loop
    try:
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print("==============================================================")
            print(f" Latency Dashboard (Python) | {run_dir}")
            print("==============================================================")
            print(f" target={TARGET}  ping_count={PING_COUNT}  timeout={PING_TIMEOUT}s")
            print(f" sample_sleep={SAMPLE_SLEEP}s  refresh={REFRESH}s\n")
            
            print(f"{'iface':<15} {'lat_avg_ms':<12} {'pkt_loss%':<12} {'status':<12} {'updated':<10} {'ip':<15}")
            print(f"{'-'*15} {'-'*12} {'-'*12} {'-'*12} {'-'*10} {'-'*15}")
            
            with state_lock:
                for ifname in active_ifaces:
                    st = dashboard_state[ifname]
                    ping_rtt = float(st['avg']) if st['avg'] != '...' else 0
                    if ping_rtt == 999999:
                        ping_rtt = 0

                    if ping_rtt != 0:
                        print(f"{ifname:<15} {ping_rtt:<12} {st['loss']:<12} {st['status']:<12} {st['ts']:<10} {st['ip']}")

                print(f"{'-'*15} {'-'*12} {'-'*12} {'-'*12} {'-'*10}")
                default_gw="DEFAULT_GW"
                print(f"Default gateway interface is labeled as 'DEFAULT_GW' in the dashboard and is {default_gw}.")
                print("****************************************************************")          
                print("\nNote: 'lat_avg_ms' of 999999 indicates no valid RTT was received.")
                print("****************************************************************")               
            time.sleep(REFRESH)
    except KeyboardInterrupt:
        print("\nExiting dashboard.")
        sys.exit(0)

if __name__ == "__main__":
    main()