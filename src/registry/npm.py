import json
import requests
import sys
import os
from datetime import datetime as dt
from constants import ExitCodes, Constants
import logging  # Added import

def get_keys(data):
    result = []
    for key in data.keys():
        if type(data[key]) != dict:
            result.append(key)
        else:
            result += get_keys(data[key])
    return result


def recv_pkg_info(pkgs, url=Constants.REGISTRY_URL_NPM):
    logging.info("npm checker engaged.")
    pkg_list = []
    for x in pkgs:
        pkg_list.append(x.pkg_name)
    payload =  '['+','.join(f'"{w}"' for w in pkg_list)+']' #list->payload conv
    headers = { 'Accept': 'application/json',
                'Content-Type': 'application/json'}
    logging.info("Connecting to registry at %s ...", url)
    try:
        res = requests.post(url, data=payload, headers=headers)
        if res.status_code != 200:
            logging.error("Unexpected status code (%s)", res.status_code)
            sys.exit(ExitCodes.CONNECTION_ERROR.value)
        x = {}
        x = json.loads(res.text)
    except:
        logging.error("Connection error.")
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    for i in pkgs:
        if i.pkg_name in x:
            i.exists = True
            i.score = x[i.pkg_name]['score']['final']
            timex = x[i.pkg_name]['collected']['metadata']['date']
            fmtx ='%Y-%m-%dT%H:%M:%S.%fZ'
            unixtime = int(dt.timestamp(dt.strptime(timex, fmtx))*1000)
            i.timestamp = unixtime
        else:
            i.exists = False
            

def scan_source(dir, recursive=False):
    try:
        logging.info("npm scanner engaged.")
        pkg_files = []
        if recursive:
            for root, dirs, files in os.walk(dir):
                if Constants.PACKAGE_JSON_FILE in files:
                    pkg_files.append(os.path.join(root, Constants.PACKAGE_JSON_FILE))
        else:
            path = os.path.join(dir, Constants.PACKAGE_JSON_FILE)
            if os.path.isfile(path):
                pkg_files.append(path)
            else:
                raise FileNotFoundError("package.json not found.")

        lister = []
        for path in pkg_files:
            with open(path, "r") as file:
                body = file.read()
            filex = json.loads(body)
            lister.extend(list(filex.get('dependencies', {}).keys()))
            if 'devDependencies' in filex:
                lister.extend(list(filex['devDependencies'].keys()))
        return list(set(lister))
    except (FileNotFoundError, IOError, json.JSONDecodeError) as e:
        logging.error("Couldn't import from given path, error: %s", e)
        sys.exit(ExitCodes.FILE_ERROR.value)
