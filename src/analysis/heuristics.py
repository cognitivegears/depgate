import time
import logging  # Added import

STG = "[ANALYSIS] "

def combobulate_min(pkgs):
    for x in pkgs:
        test_exists(x)

def combobulate_heur(pkgs):
    for x in pkgs:
        test_exists(x)
        if x.exists is True:
            test_score(x)
            test_timestamp(x)
            test_version_count(x)
    stats_exists(pkgs)

def test_exists(x):
    if x.exists is True:
        logging.info("%sPackage: %s is present on public provider.", STG, x)
    elif x.exists is False:
        logging.warning("%sPackage: %s is NOT present on public provider.", STG, x)
    else:
        logging.info("%sPackage: %s test skipped.", STG, x)

def test_score(x):
    threshold = 0.6
    risky = 0.15
    ttxt = ". Mid set to " + str(threshold) + ")"
    if x.score is not None:
        if x.score > threshold:
            logging.info("%s.... package scored ABOVE MID - %s%s", STG, str(x.score), ttxt)
        elif x.score <= threshold and x.score > risky:
            logging.warning("%s.... [RISK] package scored BELOW MID - %s%s", STG, str(x.score), ttxt)
        elif x.score <= risky:
            logging.warning("%s.... [RISK] package scored LOW - %s%s", STG, str(x.score), ttxt)

def test_timestamp(x):
    if x.timestamp is not None:
        dayspast = ((time.time()*1000 - x.timestamp)/86400000)
        logging.info("%s.... package is %d days old.", STG, int(dayspast))
        if (dayspast < 2):  # freshness test
            logging.warning("%s.... [RISK] package is SUSPICIOUSLY NEW.", STG)

def stats_exists(pkgs):
    count = sum(1 for x in pkgs if x.exists is True)
    total = len(pkgs)
    percentage = (count / total) * 100 if total > 0 else 0
    logging.info("%s%d out of %d packages were present on the public provider (%.2f%% of total).",
                 STG, count, total, percentage)

def test_version_count(x):
    if x.version_count is None:
        if x.version_count < 2:
            logging.warning("%s.... [RISK] package history is SHORT. Total %d versions committed.",
                            STG, x.version_count)
        else:
            logging.info("%s.... Total %d versions committed.", STG, x.version_count)