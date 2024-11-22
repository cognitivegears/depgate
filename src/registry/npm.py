"""
  NPM registry module. This module is responsible for checking
  the existence of the packages in the NPM registry and scanning'
  the source code for dependencies."""
import json
import sys
import os
import time
from datetime import datetime as dt
import logging  # Added import
import requests
from constants import ExitCodes, Constants

def get_keys(data):
    """Get all keys from a nested dictionary.

    Args:
        data (dict): Dictionary to extract keys from.

    Returns:
        list: List of all keys in the dictionary.
    """
    result = []
    for key in data.keys():
        if not isinstance(data[key], dict):
            result.append(key)
        else:
            result += get_keys(data[key])
    return result

def get_package_details(pkg, url):
    """Get the details of a package from the NPM registry.

    Args:
        x (_type_): _description_
        url (_type_): _description_
    """

    # Short sleep to avoid rate limiting
    time.sleep(0.1)

    try:
        logging.debug("Checking package: %s", pkg.pkg_name)
        package_url = url + pkg.pkg_name
        package_headers = {
            'Accept': 'application/vnd.npm.install-v1+json; q=1.0, application/json; q=0.8, */*'}
        res = requests.get(package_url,
            headers=package_headers,
            timeout=Constants.REQUEST_TIMEOUT)
    except requests.Timeout:
        logging.error("Request timed out after %s seconds", Constants.REQUEST_TIMEOUT)
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    except requests.RequestException as e:
        logging.error("Connection error: %s", e)
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    if res.status_code == 404:
        pkg.exists = False
        return
    try:
        package_info = json.loads(res.text)
    except json.JSONDecodeError:
        logging.warning("Couldn't decode JSON, assuming package missing.")
        pkg.exists = False
        return
    pkg.exists = True
    pkg.version_count = len(package_info['versions'])

def recv_pkg_info(pkgs, should_fetch_details=False, details_url=Constants.REGISTRY_URL_NPM, url=Constants.REGISTRY_URL_NPM_STATS):
    """Check the existence of the packages in the NPM registry.

    Args:
        pkgs (list): List of packages to check.
        url (str, optional): NPM Url. Defaults to Constants.REGISTRY_URL_NPM.
    """
    logging.info("npm checker engaged.")
    pkg_list = []
    for pkg in pkgs:
        pkg_list.append(pkg.pkg_name)
        if should_fetch_details:
            get_package_details(pkg, details_url)
    payload =  '['+','.join(f'"{w}"' for w in pkg_list)+']' #list->payload conv
    headers = { 'Accept': 'application/json',
                'Content-Type': 'application/json'}
    logging.info("Connecting to registry at %s ...", url)
    try:
        res = requests.post(url, data=payload, headers=headers,
                          timeout=Constants.REQUEST_TIMEOUT)
        if res.status_code != 200:
            logging.error("Unexpected status code (%s)", res.status_code)
            sys.exit(ExitCodes.CONNECTION_ERROR.value)
        pkg = json.loads(res.text)
    except requests.Timeout:
        logging.error("Request timed out after %s seconds", Constants.REQUEST_TIMEOUT)
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    except requests.RequestException as e:
        logging.error("Connection error: %s", e)
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    for i in pkgs:
        if i.pkg_name in pkg:
            package_info = pkg[i.pkg_name]
            i.exists = True
            i.score = package_info.get('score', {}).get('final', 0)
            timex = package_info.get('collected', {}).get('metadata', {}).get('date', '')
            fmtx ='%Y-%m-%dT%H:%M:%S.%fZ'
            try:
                unixtime = int(dt.timestamp(dt.strptime(timex, fmtx))*1000)
                i.timestamp = unixtime
            except ValueError as e:
                logging.warning("Couldn't parse timestamp: %s", e)
                i.timestamp = 0
        else:
            i.exists = False


def scan_source(dir_name, recursive=False):
    """Scan the source code for dependencies.

    Args:
        dir_name (str): Directory to scan.
        recursive (bool, optional): _description_. Defaults to False.

    Returns:
        list: List of dependencies found in the source code.
    """
    try:
        logging.info("npm scanner engaged.")
        pkg_files = []
        if recursive:
            for root, _, files in os.walk(dir_name):
                if Constants.PACKAGE_JSON_FILE in files:
                    pkg_files.append(os.path.join(root, Constants.PACKAGE_JSON_FILE))
        else:
            path = os.path.join(dir_name, Constants.PACKAGE_JSON_FILE)
            if os.path.isfile(path):
                pkg_files.append(path)
            else:
                logging.error("package.json not found, unable to continue.")
                sys.exit(ExitCodes.FILE_ERROR.value)

        lister = []
        for path in pkg_files:
            with open(path, "r", encoding="utf-8") as file:
                body = file.read()
            filex = json.loads(body)
            lister.extend(list(filex.get('dependencies', {}).keys()))
            if 'devDependencies' in filex:
                lister.extend(list(filex['devDependencies'].keys()))
        return list(set(lister))
    except (FileNotFoundError, IOError, json.JSONDecodeError) as e:
        logging.error("Couldn't import from given path, error: %s", e)
        sys.exit(ExitCodes.FILE_ERROR.value)
