import json
import os

# This script is intended for testing full-cycle from reading Bill of Materials
# and to push the output as arguments for combobulator to evaluate

with open(os.path.join("tests", "package.json"), "r") as file:
    body = file.read()
    filex = json.loads(body)
print(list(filex['dependencies'].keys()))