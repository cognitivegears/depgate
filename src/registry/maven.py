import json
import os
import sys
import logging
import xml.etree.ElementTree as ET
import requests
from constants import ExitCodes, Constants

def recv_pkg_info(pkgs, url=Constants.REGISTRY_URL_MAVEN):
    logging.info("Maven checker engaged.")
    payload = {"wt": "json", "rows": 20}
    #TODO move everything off names and modify instances instead
    for x in pkgs:
        tempstring = "g:" + x.org_id + " a:" + x.pkg_name
        payload.update({"q": tempstring})
        #print(payload) 
        headers = { 'Accept': 'application/json',
                'Content-Type': 'application/json'}
        try:
            res = requests.get(url, params=payload, headers=headers)
        except requests.RequestException as e:
            logging.error("Connection error: %s", e)
            sys.exit(ExitCodes.CONNECTION_ERROR.value)
        #print(res)
        j = json.loads(res.text)
        if j['response']['numFound'] == 1: #safety, can't have multiples
            x.exists = True
            x.timestamp = j['response']['docs'][0]['timestamp']
            x.version_count = j['response']['docs'][0]['versionCount']
        else:
            x.exists = False

def scan_source(dir_name, recursive=False):
    try:
        logging.info("Maven scanner engaged.")
        pom_files = []
        if recursive:
            for root, _, files in os.walk(dir_name):
                if Constants.POM_XML_FILE in files:
                    pom_files.append(os.path.join(root, Constants.POM_XML_FILE))
        else:
            path = os.path.join(dir_name, Constants.POM_XML_FILE)
            if os.path.isfile(path):
                pom_files.append(path)
            else:
                raise FileNotFoundError("pom.xml not found.")

        lister = []
        for path in pom_files:
            tree = ET.parse(path)
            pom = tree.getroot()
            ns = ".//{http://maven.apache.org/POM/4.0.0}"
            for dependencies in pom.findall(ns + 'dependencies'):
                for dependency in dependencies.findall(ns + 'dependency'):
                    group = dependency.find(ns + 'groupId').text
                    artifact = dependency.find(ns + 'artifactId').text
                    lister.append(group + ':' + artifact)
        return list(set(lister))
    except (FileNotFoundError, ET.ParseError) as e:
        logging.error("Couldn't import from given path, error: %s", e)
        sys.exit(ExitCodes.FILE_ERROR.value)
