import json
import requests
import requirements
import sys
import os
from datetime import datetime as dt

# classic api - https://pypi.org/pypi/<package-name>/json
REGISTRY_URL = "https://pypi.org/pypi/"


def recv_pkg_info(pkgs, url=REGISTRY_URL):
    print("[PROC] PyPI registry engaged.")
    payload = {}
    names = []
    for x in pkgs:
        fullurl = url + x.pkg_name + '/json'
        print(fullurl)
        headers = {'Accept': 'application/json',
                   'Content-Type': 'application/json'}
        try:
            res = requests.get(fullurl, params=payload, headers=headers)
        except:
            print("[ERR] Connection error.")
            exit(2)
        if res.status_code == 404:
            # Package not found
            x.exists = False
            continue
        if res.status_code != 200:
            print(f"[ERR] Connection error, status code: {res.status_code}")
            exit(2)
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
        print("[PROC] PyPI scanner engaged.")
        path = os.path.join(dir, "requirements.txt")
        with open(path, "r") as file:
            body = file.read()
        reqs = requirements.parse(body)
        return [x.name for x in reqs]
    except (FileNotFoundError, IOError) as e:
        print(f"[ERR] Couldn't import from given path '{path}', error: {e}")
        sys.exit(1)
