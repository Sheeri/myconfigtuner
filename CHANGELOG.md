### mysqltuner.py CHANGELOG
2025-10-31

## Documentation and clarifications
- Refreshed `README.md` with clear setup steps (`pip install -r requirements.txt`) and examples that use the included configs `tuner.cnf` and `minimal-tuner.cnf`.
- Documented precedence for `--defaults-extra-file` (CLI > [mysqltuner] > [client]) and provided a concrete example file.
- Noted `-p` prompt behavior when used without a value.
- Clarified CSV recommendation output format (`Recommendation,<text>` lines following triggering metrics).
- Listed helper functions available in expressions (`hr_bytes`, `hr_num`, `hr_bytime`, `pretty_uptime`, `substr`).

## Packaging
- Confirmed runtime dependency pin in `requirements.txt` (`mysql-connector-python>=8.0,<9.0`).

2025-09-15

## Overview
- Re-implemented the tuning workflow in Python 3 while preserving the original CLI shape and config-driven evaluation model.
- Replaced escaping to shell to call `mysql` and `mysqladmin` with a native MySQL driver.
- Maintained offline analysis mode and output formats, with safer expression evaluation.

## Functional changes
- Connection/driver
  - Uses `mysql-connector-python` by default instead of spawning `mysql`/`mysqladmin`.
  - Supports host/port/user/pass and unix socket (when no host specified).
  - Enforces the original remote parity behavior: `--forcemem` is required when connecting to non-local hosts.

- Offline mode
  - `--filelist` accepts one or more files of `key value` pairs. The first token is treated as the key; the remainder of the line is the value.
  - Errors opening files are reported and the program exits with a non-zero status.

- Config format and evaluation
  - Retains the four-field rule format: `label ||| comparison ||| expression ||| recommendation`.
  - Expressions are evaluated in Python with a minimal, safe namespace. Variable names from MySQL status/variables are substituted into the expression before evaluation (numeric strings remain numeric; other strings are quoted).
  - Comparison text is translated to Python at runtime and supports:
    - `eq`/`ne` → `==`/`!=`
    - Regex matches `=~ /re/flags` and `!~ /re/flags` via `re.search` with `i` case-insensitive flag.
    - Leading comparisons on the computed value (`<`, `>`, `<=`, `>=`, `==`, `!=`).
    - Leading method calls (e.g., `.lower()`) applied to the computed value.

- Helpers available in expressions
  - `hr_bytes`, `hr_num`, `hr_bytime`, `pretty_uptime`, and `substr` are exposed to configs for human-readable formatting and string slicing.
  - Numeric rounding behavior mirrors Perl intent: numeric results are rounded to two decimals; numeric strings are rounded except when the expression contains the word `version`.

- Output
  - Preserves `--output pretty|csv`. Pretty mode prints `label: value`; CSV prints `label,value`.
  - Recommendations are collected and printed at the end when `--recommend` is specified. In pretty mode, the triggering metric line is bolded (ANSI), followed by the recommendation text.
  - Category headers are recognized when written as comment lines in the config with `# Category: <name>` and are echoed into the output.

- Defaults and CLI behavior
  - Requires `--config` (prints usage and exits if missing).
  - `--help` is implemented and prints a help/usage block akin to the Perl script.
  - `--skipsize` is accepted for parity but currently acts as a no-op (reserved for future use).

## Content changes
- Sample configs and artifacts
  - Added `minimal-tuner.cnf` and `tuner.cnf` example configs tailored to the Python evaluator.
  - Included example data and output artifacts (`vars.txt`, `status.txt`, `recommend.txt`) to demonstrate offline and reporting flows.

- Rules
  - Introduced an explicit "Release cutoff" version rule section to flag versions predating a specified date window.
  - Preserved and modernized many checks (rates, percentages, thresholds) using Python helpers for readability.

- Removed/omitted legacy bits
  - The standalone `tables.pl` utility (table file size vs. metadata comparison) is not included in the Python port.
  - The legacy default config files from the Perl tree (e.g., `tuner-default.cnf` and `tuner-default_pre_5_1.cnf`) are not bundled here; use the provided Python-ready examples or adapt your existing configs to Python expression syntax.

## Compatibility notes
- Expression language changed to Python; review operators, integer division semantics, and regexes when migrating custom rules.
- Variable names are case-sensitive and substituted with string or numeric literals depending on content. Values that are numeric strings are treated as numbers where appropriate.
- When connecting to remote hosts, `--forcemem` must be provided (matching the Perl script’s behavior).

2010-04-09
mysqltuner.pl
made it so Perl didn't spit out an error if a value was undefined.  Now the error is handled gracefully by the program.

changed tuner-default.cnf to not have table_cache (it has table_open_cache)
changed Uptime to Uptime_since_flush_status for most rates in tuner-default.cnf

added:
slow query rate
reads per sec
writes per sec
rate of sorts that cause temporary tables
rate of open files
rate of aborted connections
rate of aborted clients

2010-03-02:
mysqltuner.pl
corrected the versions for SHOW GLOBAL STATUS and SHOW GLOBAL VARIABLES
Fixes https://bugs.launchpad.net/mysqltuner/+bug/530285

added tuner-default_pre_5_1.cnf
These are workarounds for https://bugs.launchpad.net/mysqltuner/+bug/530456

2010-02-25:
mysqltuner.pl:
took out the invalid reference to the print_all() function
error for not using forcemem when a host is specified is no longer thrown if the host specified is 127.0.0.1

tuner-default.cnf:
Now checks for both table_cache and table_open_cache, specifying that the former is pre 5.1

2010-02-11:
tuner-default.cnf:
Changed query cache lowmem prunes per day to a straight low memory prunes by time check
Added query cache minimum result size - warn if it's set to the default
Added rate of creating temporary disk tables (previously had only %)
Added rate of creating temporary tables (memory or disk)
Added table cache size to the output

2009-12-02:
mysqltuner.pl:
changed the split character to |||

tuner-default.cnf
changed the split character to |||
Changed the following to use readable byte-numbers (ie, anything >1024 bytes is in Kb, similar for Mb and Gb):
  query_cache_size
Changed the label for query_cache_size from "Query cache" to "Query cache size"
Changed the label of "InnoDB" to "Is InnoDB enabled?"
Changed thread cache hit rate to complain if Threads_created/Connections >20 (was <20, but < is a better hit rate)
Separated out Sorts, Joins/scans and temporary table sections
Fixed the threshold for MyISAM concurrent inserts - old test was "0", new test is "=0"
Added the following variable printouts:
 sort_buffer_size printout
 read_rnd_buffer_size printout
 tmp_table_size
 max_heap_table_size
 slow_launch_time
 Max_used_connections
 max_connections
Added the following checks:
 rate of sorted rows 
 rate of reading first index entry
 rate of reading fixed position
 rate of reading next table row
 rate of joins without indexes (removed Joins w/out indexes, Joins w/out indexes per day)
 MyISAM key buffer size
 max % MyISAM key buffer ever used
 rate of table open
 Table lock wait rate
 Total threads created
 Threads that are slow to launch
 % aborted clients
