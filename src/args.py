
"""Argument parsing functionality for Combobulator."""

import argparse
from constants import Constants

def parse_args():
    """Parses the arguments passed to the program."""
    parser = argparse.ArgumentParser(
        prog="combobulator.py",
        description="Dependency Combobulator - Dependency Confusion Checker",
        epilog='Apiiro <Heart> Community',
        add_help=True)
    
    parser.add_argument("-t", "--type",
                        dest="package_type",
                        help="Package Manager Type, i.e: npm, PyPI, maven",
                        action="store", type=str, 
                        choices=Constants.SUPPORTED_PACKAGES,
                        required=True)

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("-l", "--load_list",
                        dest="LIST_FROM_FILE",
                        help="Load list of dependencies from a file",
                        action="append", type=str,
                        default=[])
    input_group.add_argument("-d", "--directory",
                    dest="FROM_SRC",
                    help="Extract dependencies from local source repository",
                    action="append",
                    type=str)
    input_group.add_argument("-p", "--package",
                            dest="SINGLE",
                            help="Name a single package.",
                            action="append", type=str)

    output_group = parser.add_mutually_exclusive_group(required=False)
    output_group.add_argument("-c", "--csv",
        dest="CSV",
        help="Export packages properties onto CSV file",
                    action="store", type=str)

    parser.add_argument("-a", "--analysis",
        dest="LEVEL",
        help="Required analysis level - compare (comp), heuristics (heur) (default: compare)",
                    action="store", default="compare", type=str,
                    choices=Constants.LEVELS)
    parser.add_argument("--loglevel",
                        dest="LOG_LEVEL",
                        help="Set the logging level",
                        action="store",
                        type=str,
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        default='INFO')
    parser.add_argument("--logfile",
                        dest="LOG_FILE",
                        help="Log output file",
                        action="store",
                        type=str)
    parser.add_argument("-r", "--recursive",
                        dest="RECURSIVE",
                        help="Recursively scan directories when scanning from source.",
                        action="store_true")
    parser.add_argument("--error-on-warnings",
                        dest="ERROR_ON_WARNINGS",
                        help="Exit with a non-zero status code if warnings are present.",
                        action="store_true")

    return parser.parse_args()