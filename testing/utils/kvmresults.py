#!/usr/bin/env python3

# Print a test result summary gathered by scanning the OUTPUT.
#
# Copyright (C) 2015-2016 Andrew Cagney <cagney@gnu.org>
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
import os
import re
from enum import Enum

from fab import testsuite
from fab import logutil
from fab import post
from fab import stats
from fab import skip
from fab import ignore
from fab import argutil
from fab import jsonutil


class Print(argutil.List):
    diffs = "diffs"
    directory = "directory"
    expected_result = "expected-result"
    full_name = "full-name"
    host_names = "host-names"
    kind = "kind"
    name = "name"
    output_directory = "output-directory"
    result = "result"
    sanitize_directory = "sanitize-directory"
    saved_output_directory = "saved-output-directory"
    scripts = "scripts"
    errors = "errors"
    runtime = "runtime"
    total_time = "total-time"
    start_time = "start-time"
    end_time = "end-time"
    script_time = "script-time"
    boot_time = "boot-time"


class Prefix(Enum):
    def __str__(self):
        return self.value
    name = "name"
    test_directory = "test-directory"
    output_directory = "output-directory"


class Stats(Enum):
    def __str__(self):
        return self.value
    details = "details"
    summary = "summary"
    none = "none"


def main():

    parser = argparse.ArgumentParser(description="list all tests in the form: <test> [ <directory> ] [ <result> <details...> ]",
                                     epilog="By default this tool uses 'sanitizer.sh' and 'diff' to generate up-to-the-minuite test results (the previously generated files 'OUTPUT/*.console.txt' and 'OUTPUT/*.console.diff' are ignored).  While this makes things a little slower, it has the benefit of always providing the most up-to-date and correct results (for instance, changes to known-good files are reflected immediately).  If a BASELINE directory is specified, anywhere a test result is different to the baseline is also identified.")
    parser.add_argument("--verbose", "-v", action="count", default=0)

    parser.add_argument("--quick", action="store_true",
                        help=("Use the previously generated '.console.txt' and '.console.diff' files"))
    parser.add_argument("--quick-sanitize", action="store_true",
                        help=("Use the previously generated '.console.txt' file"))
    parser.add_argument("--quick-diff", action="store_true",
                        help=("Use the previously generated '.console.diff' file"))

    parser.add_argument("--update", action="store_true",
                        help=("Update the '.console.txt' and '.console.diff' files"))
    parser.add_argument("--update-sanitize", action="store_true",
                        help=("Update the '.console.txt' file"))
    parser.add_argument("--update-diff", action="store_true",
                        help=("Update the '.console.diff' file"))

    parser.add_argument("--dump-args", action="store_true")

    parser.add_argument("--prefix", action="store", type=Prefix,
                        choices=[p for p in Prefix],
                        help="prefix to display with each test")

    # how to parse --print directory,saved-directory,...?
    parser.add_argument("--print", action="store",
                        default=Print(Print.result, Print.errors),
                        type=Print, metavar=str(Print),
                        help="comman separate list of attributes to print for each test; default: '%(default)s'")

    parser.add_argument("--stats", action="store", default=Stats.summary, type=Stats,
                        choices=[c for c in Stats],
                        help="provide overview statistics; default: \"%(default)s\"");

    parser.add_argument("--baseline", metavar="DIRECTORY",
                        help="a %(metavar)s containing baseline testsuite output")

    parser.add_argument("directories", metavar="DIRECTORY", nargs="+",
                        help="%(metavar)s containing: a test, a testsuite (contains a TESTLIST file), a TESTLIST file, test output, or testsuite output")
    # Note: this argument serves as documentation only.  The
    # TEST-DIRECTORY argument always consumes all remaining arguments.
    parser.add_argument("baseline", metavar="BASELINE-DIRECTORY", nargs="?",
                        help="an optional testsuite directory (contains a TESTLIST file) containing output from a previous test run")

    parser.add_argument("--json", action="store_true",
                        help="output each result as an individual json object (pipe the output through 'jq -s .' to convert it to a well formed json list")

    testsuite.add_arguments(parser)
    logutil.add_arguments(parser)
    skip.add_arguments(parser)
    ignore.add_arguments(parser)

    args = parser.parse_args()

    logutil.config(args)
    logger = logutil.getLogger("kvmresults")

    # The option -vvvvvvv is a short circuit for these; make
    # re-ordering easy by using V as a counter.
    v = 0

    if args.dump_args:
        logger.info("Arguments:")
        logger.info("  Stats: %s", args.stats)
        logger.info("  Print: %s", args.print)
        logger.info("  Prefix: %s", args.prefix)
        logger.info("  Baseline: %s", args.baseline)
        logger.info("  Json: %s", args.json)
        testsuite.log_arguments(logger, args)
        logutil.log_arguments(logger, args)
        skip.log_arguments(logger, args)
        ignore.log_arguments(logger, args)
        return 0

    # Try to find a baseline.  If present, pre-load it.
    baseline = None
    if args.baseline:
        # An explict baseline testsuite, can be more forgiving in how
        # it is loaded.
        baseline = testsuite.load(logger, args,
                                  testsuite_directory=args.baseline,
                                  error_level=logutil.DEBUG)
        if not baseline:
            # Perhaps the baseline just contains output, magic up the
            # corresponding testsuite directory.
            baseline_directory = os.path.join(args.testing_directory, "pluto")
            baseline = testsuite.load(logger, args,
                                      testsuite_directory=baseline_directory,
                                      saved_testsuite_output_directory=args.baseline,
                                      error_level=logutil.DEBUG)
        if not baseline:
            logger.info("'%s' is not a baseline", args.baseline)
            return 1
    elif len(args.directories) > 1:
        # If there is more than one directory then, perhaps, the last
        # one is a baseline.  A baseline might be: a complete
        # testsuite snapshot; or just output saved as
        # testing/pluto/OUTPUT/TESTDIR.
        baseline = testsuite.load(logger, logutil.DEBUG, args,
                                  testsuite_directory=args.directories[-1])
        if baseline:
            # discard the last argument as consumed above.
            logger.debug("discarding baseline testsuite argument '%s'", args.directories[-1])
            args.directories.pop()

    tests = testsuite.load_testsuite_or_tests(logger, args.directories, args)
    # And check
    if not tests:
        logger.error("Invalid testsuite or test directories")
        return 1

    result_stats = stats.Results()
    try:
        results(logger, tests, baseline, args, result_stats)
    finally:
        if args.stats is Stats.details:
            result_stats.log_details(stderr_log, header="Details:", prefix="  ")
        if args.stats in [Stats.details, Stats.summary]:
            result_stats.log_summary(stderr_log, header="Summary:", prefix="  ")

    return 0


def stderr_log(fmt, *args):
    sys.stderr.write(fmt % args)
    sys.stderr.write("\n")


class JsonOutput:
    def __init__(self):
        self.table = {}
    def prefix(self, key, value):
        self.add(key, value)
    def add(self, *keyval, string=None):
        keys = [key.replace("-","_") for key in keyval[0:-1]]
        value = keyval[-1]
        # Only suppress non-existant values.
        if value is None:
            return
        table = self.table
        for key in keys[0:-1]:
            key = key.replace("-","_")
            if not key in table:
                table[key] = {}
            table = table[key]
        table[keys[-1]] = value
    def flush(self):
        jsonutil.dump(self.table, sys.stdout)
        sys.stdout.write("\n")
        sys.stdout.flush()

class PrintOutput:
    def prefix(self, key, value):
        sys.stdout.write(value)
    def add(self, *keyval, string=lambda x: x and " " + str(x) or ""):
        # By default, suppress anything Null or empty/false/...
        keys = keyval[0:-1]
        value = keyval[-1]
        sys.stdout.write(string(value))
    def flush(self):
        sys.stdout.write("\n")
        sys.stdout.flush()


class ResultCache:
    """Load the results on-demand"""

    def __init__(self, logger, test, args, baseline, result_stats):
        self.cached_debug_log = None
        self.cached_result = None
        self.logger = logger
        self.test = test
        self.args = args
        self.baseline = baseline
        self.result_stats = result_stats

    def result(self, reason):
        if self.cached_result:
            return self.cached_result
        self.logger.debug("loading results for %s", reason)
        self.cached_result = post.mortem(self.test, self.args, baseline=self.baseline,
                                         output_directory=self.test.saved_output_directory,
                                         skip_sanitize=self.args.quick or self.args.quick_sanitize,
                                         skip_diff=self.args.quick or self.args.quick_diff,
                                         update=self.args.update,
                                         update_sanitize=self.args.update_sanitize,
                                         update_diff=self.args.update_diff)
        self.result_stats.add_result(self.cached_result)
        return self.cached_result

    def grub(self, regex, cast=lambda x: x):
        """Grub around in the debug log to find useful stuff"""
        if self.cached_debug_log is None:
            debug_log = os.path.join(self.test.output_directory, "debug.log")
            if os.path.isfile(debug_log):
                with open(debug_log) as f:
                    self.cached_debug_log = f.read()
            else:
                self.cached_debug_log = ""
        match = re.search(regex, self.cached_debug_log, re.MULTILINE)
        if not match:
            return None
        return cast(match.group(1))


def results(logger, tests, baseline, args, result_stats):

    for test in tests:

        # If debug logging is enabled this will provide fine grained
        # per-test timing.
        with logger.debug_time("processing test %s", test.name):

            # Filter out tests that are being ignored?
            ignored, details = ignore.test(logger, args, test)
            if ignored:
                result_stats.add_ignored(test, ignored)
                continue

            # Filter out tests that have not been run
            result_cache = ResultCache(logger, test, args, baseline, result_stats)
            if args.skip:
                result = result_cache.result("skip")
                if skip.result(logger, args, result):
                    result_stats.add_skipped(result)
                    continue

            b = args.json and JsonOutput() or PrintOutput()

            # Print the test's name/path
            if not args.prefix:
                # By default: when the path given on the command line
                # explicitly specifies a test's output directory
                # (found in TEST.SAVED_OUTPUT_DIRECTORY), print that;
                # otherwise print the path to the test's directory.
                if test.saved_output_directory:
                    b.prefix(Print.saved_output_directory,
                             test.saved_output_directory)
                else:
                    b.prefix(Print.directory, test.directory)
            else:
                # Print the test name/path per command line
                if args.prefix is Prefix.name:
                    b.prefix(Print.name, test.name)
                elif args.prefix is Prefix.test_directory:
                    b.prefix(Print.directory, test.directory)
                elif args.prefix is Prefix.output_directory:
                    if test.saved_output_directory:
                        b.prefix(Print.saved_output_directory,
                                 test.saved_output_directory)
                    else:
                        b.prefix(Print.output_directory,
                                 test.output_directory)

            for p in args.print:
                if p is Print.diffs:
                    continue
                elif p is Print.directory:
                    b.add(p, test.directory)
                elif p is Print.expected_result:
                    b.add(p, test.expected_result)
                elif p is Print.full_name:
                    b.add(p, test.full_name)
                elif p is Print.host_names:
                    b.add(p, test.host_names,
                          string=lambda host_names: " " + ",".join(host_names))
                elif p is Print.kind:
                    b.add(p, test.kind)
                elif p is Print.name:
                    b.add(p, test.name)
                elif p is Print.output_directory:
                    b.add(p, test.output_directory)
                elif p is Print.result:
                    b.add(p, result_cache.result(p))
                elif p is Print.errors:
                    b.add(p, result_cache.result(p).errors)
                elif p is Print.sanitize_directory:
                    b.add(p, test.sanitize_directory)
                elif p is Print.saved_output_directory:
                    b.add(p, test.saved_output_directory)
                elif p is Print.scripts:
                    b.add(p, [{ "host": h, "script": s} for h, s in test.host_script_tuples],
                          string=lambda scripts: " " + ",".join([script["host"] + ":" + script["script"] for script in scripts]))
                elif p is Print.start_time:
                    b.add(p, result_cache.grub(r"starting debug log at (.*)$"))
                elif p is Print.end_time:
                    b.add(p, result_cache.grub(r"ending debug log at (.*)$"))
                elif p is Print.runtime:
                    b.add(p, result_cache.grub(r": stop testing .* after (.*) second", float))
                elif p is Print.boot_time:
                    b.add(p, result_cache.grub(r": stop booting domains after (.*) second", float))
                elif p is Print.script_time:
                    b.add(p, result_cache.grub(r": stop running scripts .* after (.*) second", float))
                elif p is Print.total_time:
                    b.add(p, result_cache.grub(r": stop processing test .* after (.*) second", float))
                else:
                    raise Exception("unhandled print option %s" % p)

            if Print.diffs in args.print:
                result = result_cache.result(Print.diffs)
                for domain in result.diffs:
                    b.add(Print.diffs, domain, result.diffs[domain],
                          string=lambda diff: diff and "\n" + "\n".join(diff) or "")

            b.flush()


if __name__ == "__main__":
    sys.exit(main())
