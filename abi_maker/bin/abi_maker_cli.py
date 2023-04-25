#! /usr/bin/env python

import argparse
import os
import sys
from pathlib import Path

from abi_maker import make_wrapper

from typing import Dict, List, Optional, Sequence, Tuple, Union, Callable, Any


def main():
    args = parse_all_args()
    
    files_written = make_wrapper.write_project_wrapper( project_name=args.project, 
                                                        abi_json_path=args.json, 
                                                        output_dir=args.output,
                                                        overwrite_ok=args.force_overwrite)
    # package_dir = args.output / args.project
    package_dir = args.output 
    print(f'Wrote {len(files_written)} files to {package_dir}')


def parse_all_args(args_in=None):
    ''' Set up argparser and return a namespace with named
    values from the command line arguments.  
    If help is requested (-h / --help) the help message will be printed 
    and the program will exit.
    '''
    program_description = '''Generate a Python wrapper for Solidity contracts from an ABI JSON file'''

    parser = argparse.ArgumentParser( description=program_description,
                formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Replace these with your arguments below
    parser.add_argument( '--project', '-p', required=True,
        help='Name of project to create')
    parser.add_argument( '--json', '-j', type=Path, required=True,
        help='JSON containing one or more contract ABIs and addresses. See README.md for schema.')
    # TODO: add default max gas, default bonus gas, default network name & rpc 
    # parser.add_argument()
    parser.add_argument( '--output', '-o', type=Path, default= os.getcwd(),
        help=f'Write wrapper package to OUTPUT directory.')
    parser.add_argument('--force_overwrite', '-f', action='store_true', default=False,
        help=f'Overwrite existing project directory without asking.')

    # If no arguments were supplied, print help
    if len(sys.argv) == 1:
        sys.argv.append('-h')

    # If args_in isn't specified, args will be taken from sys.argv
    args_namespace = parser.parse_args(args_in)
    return args_namespace

if __name__ == '__main__':
    main()
