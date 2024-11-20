import json
import requests
import requirements
import sys
import os
from datetime import datetime as dt
from constants import ExitCodes, Constants
import logging  # Added import

def recv_pkg_info(pkgs, url=Constants.REGISTRY_URL_PYPI):
    logging.info("PyPI registry engaged.")
    payload = {}
    names = []
    for x in pkgs:
        fullurl = url + x.pkg_name + '/json'
        logging.debug(fullurl)
        headers = {'Accept': 'application/json',
                   'Content-Type': 'application/json'}
        try:
            res = requests.get(fullurl, params=payload, headers=headers)
        except:
            logging.error("Connection error.")
            exit(ExitCodes.CONNECTION_ERROR.value)
        if res.status_code == 404:
            # Package not found
            x.exists = False
            continue
        if res.status_code != 200:
            logging.error("Connection error, status code: %s", res.status_code)
            exit(ExitCodes.CONNECTION_ERROR.value)
        try:
            j = json.loads(res.text)
        except:
            x.exists = False
            return
        if j['info']:
            names.append(j['info']['name'])  # add pkgName
            x.exists = True
            latest = j['info']['version']
            for version in j['releases']:
                if version == latest:
                    timex = j['releases'][version][0]['upload_time_iso_8601']
                    fmtx = '%Y-%m-%dT%H:%M:%S.%fZ'
                    unixtime = int(dt.timestamp(dt.strptime(timex, fmtx)) * 1000)
                    x.timestamp = unixtime
            x.verCount = len(j['releases'])
        else:
            x.exists = False
    return names

def scan_source(dir):
    try:
        logging.info("PyPI scanner engaged.")
        path = os.path.join(dir, Constants.REQUIREMENTS_FILE)
        with open(path, "r") as file:
            body = file.read()
        reqs = requirements.parse(body)
        return [x.name for x in reqs]
    except (FileNotFoundError, IOError) as e:
        logging.error("Couldn't import from given path '%s', error: %s", path, e)
        sys.exit(ExitCodes.FILE_ERROR.value)
