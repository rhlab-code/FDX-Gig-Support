# IP Lookup Helper (Patched v2.2)
# Based on user's original script to query Thanos for CM/CPE IP by MAC.
# Changes:
#   - Use sys.executable for subprocess calls (avoid wrong interpreter)
#   - Stronger diagnostics on subprocess failures
#   - Safe JSON parsing (handles None/non-JSON)
#   - Robust IPv4/IPv6 validators
#   - Optional second attempt passing --bearer <token> to thanos2.py (if supported)
#   - Clearer messaging around python-dotenv install vs .env presence


#   Sample node: PADUSTES4A
#   Sapmle Amp Name UNREG-PADUSTEST4-24:A1:86:1F:F3:AC
#   Sample MAC 24:a1:86:1f:f3:ac
#   Sample IP  2001:0558:6031:001C:3408:5385:73EF:FE58

''' example usages:
python amp_info.py PROD CPE 24:a1:86:1f:f3:ac
python amp_info.py PROD CPE 2001:0558:6031:001C:3408:5385:73EF:FE58
'''

import subprocess
import json
import ipaddress
import sys
import os
import logging
import macaddress

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Load environment variables from .env file ---
try:
    from dotenv import load_dotenv
    load_dotenv()  # Will search for .env in current and parent directories
except ImportError:
    print("python-dotenv is not installed. Install with: pip install python-dotenv")


def run_script_and_get_result(script_path, arguments=[]):
    logging.debug(f"Running script for result: {script_path} with arguments: {arguments}")
    """
    Runs a Python script in a subprocess and returns the output.

    Args:
      script_path: The path to the Python script to execute.
      arguments: A list of arguments to pass to the script.

    Returns:
      A string containing the stdout of the script, or None if an error occurred.
    """
    try:
        command = [sys.executable, script_path] + arguments
        process = subprocess.run(command, capture_output=True, text=True)
        if process.returncode == 0:
            return process.stdout.strip()
        else:
            logging.debug(f"[{os.path.basename(script_path)}] rc={process.returncode}")
            if process.stderr:
                logging.debug(f"[stderr]: {process.stderr.strip()[:500]}")
            if process.stdout:
                logging.debug(f"[stdout]: {process.stdout.strip()[:500]}")
            return None
    except FileNotFoundError:
        logging.warning(f"Script not found: {script_path}")
        return None


def run_script(script_path, arguments=[]):
    logging.debug(f"Running script: {script_path} with arguments: {arguments}")
    """Runs a Python script in a subprocess and logs errors if any."""
    try:
        command = [sys.executable, script_path] + arguments
        process = subprocess.run(command, capture_output=True, text=True)
        if process.returncode != 0:
            logging.warning(f"Error running script {script_path} (rc={process.returncode})")
            if process.stderr:
                logging.warning(f"[stderr]: {process.stderr.strip()[:500]}")
            if process.stdout:
                logging.debug(f"[stdout]: {process.stdout.strip()[:500]}")
    except FileNotFoundError:
        logging.warning(f"Script not found: {script_path}")


def is_ipv6(address):
    logging.debug(f"Validating IPv6 address: {address}")
    """Checks if a string is a valid IPv6 address."""
    if not address:
        return False
    try:
        ipaddress.IPv6Address(address)
        return True
    except (ipaddress.AddressValueError, ValueError, TypeError):
        logging.debug("Invalid IPv6 address format.")
        return False


def is_ipv4(address):
    logging.debug(f"Validating IPv4 address: {address}")
    """Checks if a string is a valid IPv4 address."""
    if not address:
        return False
    try:
        ipaddress.IPv4Address(address)
        return True
    except (ipaddress.AddressValueError, ValueError, TypeError):
        logging.debug("Invalid IPv4 address format.")
        return False

def is_mac(mac):
    logging.debug(f"Validating MAC address: {mac}")
    """
    Checks if a string is a valid MAC address using the macaddress library.
    """
    try:
        macaddress.MAC(mac)
        return True
    except ValueError:
        logging.debug("Invalid MAC address format.")
        return False

def safe_json_load(s):
    logging.debug("Parsing JSON response")
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        logging.debug("Failed to parse JSON. safe_json_load returning None.")
        return None


def find_IpAddr(json_string, search):
    ret = {}
    logging.debug(f"Finding address for key: {search}")
    """
    Finds and extracts a given key from each 'metric' result in the Thanos JSON response.

    Args:
      json_string: The JSON string to search.
      search: The key to retrieve from result_item['metric'].

    Returns:
      First matching value as string, or None.
    """
    logging.debug("Loading JSON string for address extraction")
    logging.debug(f"--- {search} ----")
    obj = safe_json_load(json_string)
    if not obj:
        if json_string:
            logging.debug(f"Non-JSON or empty response (first 200 chars): {str(json_string)[:200]}")
        else:
            logging.debug("Empty response from thanos2.py")
        return None
    try:
        for result_item in obj.get('data', {}).get('result', []):
            logging.debug(f"Inspecting result item: {result_item}")
            val = result_item.get('metric', {}).get(search) # Top level key to search for
            # need to opull the node name from the metric to correlate to the right mac/ip
            nodeName = result_item.get('metric', {}).get('fnName')
            if val: #we have a value
                logging.debug(f"Found value: {val} for key: {search}")
                # Push into ret dict for potential future use, but currently we just return the first found value
                ret[search] =val
                ret['fnName'] = nodeName
                # return val
                return ret

    except Exception as e:
        logging.warning(f"Error parsing JSON structure: {e}")
    return None


# --- Begin main behavior ---
if __name__ == '__main__':
    path = "./toybox-main"
    Short_output = len(sys.argv) == 4
    if Short_output:
        arg1 = 'PROD' #sys.argv[1]   # 'PROD' or 'DEV'
        arg2 = 'CPE' #sys.argv[2]   # 'CM' or 'CPE'
        arg3 = sys.argv[3]   # CM MAC or IP
    else:
        print("Please at least provide 3 arguments: <PROD or DEV>, <CM or CPE>, <MAC or IP>")
        arg1 = 'PROD'
        arg2 = 'CPE'
        arg3 = ''
    
#2001:0558:40A0:0013:DD18:FF03:710D:6047    CM Do not use
#2001:0558:6043:003F:2855:D2DC:2D77:FD23    CPE MACs for testing
    if arg1 == "PROD":
        url = "https://sat-prod.codebig2.net/v2/ws/token.oauth2"
        PROD_secret = os.environ.get("PROD_API_KEY")
        if PROD_secret is None:
            print("PROD_API_KEY environment variable not set.")
            sys.exit(1)
        secret = PROD_secret
        tag = 'prod'
    elif arg1 == "DEV":
        url = "https://sat-stg.codebig2.net/v2/ws/token.oauth2"
        DEV_secret = os.environ.get("DEV_API_KEY")
        if DEV_secret is None:
            print("DEV_API_KEY environment variable not set.")
            sys.exit(1)
        secret = DEV_secret
        tag = 'dev'
    else:
        print(f"Unknown environment '{arg1}'. Use PROD or DEV.")
        sys.exit(1)

    # Determine target type
    if arg2 == "CM":
        k_matrix = 'K_CmRegStatus_Config'
        find_ipv4 = 'ipV4Addr'
        find_ipv6 = 'ipv6Addr'
        find_mac = 'cmMacAddr'
    elif arg2 == "CPE":

        k_matrix = 'K_CmCpeList'
        find_ipv4 = 'cpeIpv4Addr'
        find_ipv6 = 'cpeIpv6Addr'
        find_mac = 'cmMacAddr'
    
    else:
        print(f"Unknown target '{arg2}'. Use CM or CPE.")
        sys.exit(1)

    websec = os.path.join(path, 'websec.py')
    thanos2 = os.path.join(path, 'thanos2.py')

    # Acquire token via websec.py
    logging.debug("Acquiring token via websec.py")
    run_script(websec, ["thanos-prod", "--url", url, "--id", "ngan-hs", "--secret", secret, "--scope", "ngan:telemetry:thanosapi"])
    token = run_script_and_get_result(websec, [f"thanos-{tag}", "--bearer"]) or ""


    if (is_ipv4(arg3) or is_ipv6(arg3)):
        logging.debug(f"Input argument is IP address: {arg3}. Need to find the MAC")
        if is_ipv4(arg3):
            logging.debug("Searching by IPv4 address")
            arguments = [f"--{tag}", k_matrix, f"{find_ipv4}={arg3}"]
        elif is_ipv6(arg3):
            logging.debug("Searching by IPv6 address")
            arguments = [f"--{tag}", k_matrix, f"{find_ipv6}={arg3}"]
        else:
            logging.error("Invalid IP address provided.")
            sys.exit(1)
    elif is_mac(arg3):
        # mac = arg3
        logging.debug(f"Input argument is MAC address: {arg3}")
        arguments = [f"--{tag}", k_matrix, f"{find_mac}={arg3}"]

    logging.debug(f"------------ {arguments}  --------------------")
    result = run_script_and_get_result(thanos2, arguments)
        
    # If no result, try again passing bearer explicitly (if supported)
    if (not result) and token:
        logging.debug("No result from thanos2.py, retrying with --bearer token")
        # arguments_bearer = [f"--{tag}", k_matrix, f"cmMacAddr={arg3}", "--bearer", token]
        # result = run_script_and_get_result(thanos2, arguments_bearer)

    if not result:
        print(f"CM MAC = {arg3}: no result from thanos2.py")
        # continue

    ## Process the reslt and pull the right key:value
    if is_ipv4(arg3): #we're passing an ipv4 looking for mac
        mac = find_IpAddr(result, find_mac)
        #print(f"Functionality not yet implemented for IPv4 to MAC lookup.")
        print(mac if Short_output else f"IPv4 = {arg3}, {find_mac} = {mac}")
    elif is_ipv6(arg3):# passing ipv6 looking for mac
        mac = find_IpAddr(result, find_mac)
        print(mac if Short_output else f"IPv6 = {arg3}, {find_mac} = {mac}")
    elif is_mac(arg3): # passing mac looking for ipv6
        ip = find_IpAddr(result, find_ipv6)
        print(ip if Short_output else f"IPv6 = {arg3}, {find_ipv6} = {ip}")
    else:
        print(f"CM MAC = {arg3}: No valid {find_ipv4}/{find_ipv6} found.")
        