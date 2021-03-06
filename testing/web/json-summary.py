#!/usr/bin/env python3

# Print "graph.json" on standard output.
#
# Copyright (C) 2016 Andrew Cagney <cagney@gnu.org>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See <http://www.fsf.org/copyleft/gpl.txt>.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.

import argparse
import sys
import json
from os import path

def main():

    parser = argparse.ArgumentParser(description="write graph.json to standard output")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("results", metavar="table.json", nargs="+",
                        help="%(metavar)s files containing results from test runs")

    args = parser.parse_args()

    rows = []
    for result in args.results:
        args.verbose and sys.stderr.write("%s\n" % result)
        with open(result) as f:
            try:
                j = json.load(f)
            except ValueError:
                sys.stderr.write("invalid json: %s\n" % (result))
                continue
            if not "summary" in j:
                sys.stderr.write("missing summary: %s\n" % (result))
                continue
            summary = j["summary"]
            # drop .json and use rest for directory
            directory, _ = path.split(result)
            summary["directory"] = directory
            rows.append(summary)

    json.dump(rows, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
