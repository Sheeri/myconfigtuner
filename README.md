## mysqltuner.py (Python 3)

A Python 3 port of the legacy `mysqltuner.pl` (v2.0.1). It evaluates rules from a config file against MySQL server variables and status, and can print recommendations based on thresholds.

### Requirements

- Python 3.8+
- Install runtime dependencies:

```bash
pip install -r requirements.txt
```

- Runtime dependency: `mysql-connector-python` (used by default)

### Included Files

- `mysqltuner.py`: Script entry point.
- `tuner.cnf`: Comprehensive example rules for the Python evaluator.
- `minimal-tuner.cnf`: Minimal example ruleset to validate your setup.
- `vars.txt`, `status.txt`: Example inputs for offline mode.

### Config File Format

One rule per line:

```
<label> ||| <comparison> ||| <expression> ||| <recommendation>
```

- Lines beginning with `#` are comments. Category headers can be emitted by adding comment lines like `# Category: Connections`.
- `<expression>` is Python and can reference MySQL variables/status by name. Before evaluation, identifiers that match fetched variable names are replaced with their values (numeric strings remain numeric; other strings are quoted).
- Helpers available in expressions: `hr_bytes`, `hr_num`, `hr_bytime`, `pretty_uptime`, `substr`.

Example:

```
Connections ||| > 100 ||| Threads_connected ||| Consider lowering max_connections or investigating connection spikes.
```

### Usage

```
python3 mysqltuner.py --config tuner.cnf [--recommend] [--output pretty|csv] \
  [--host HOST --port 3306 --user USER (-p[PASS] | --pass PASS) | --socket /path/to/socket] \
  [--defaults-extra-file=/path/to/file.cnf] \
  [--filelist file1.txt,file2.txt] [--forcemem MB --forceswap MB --forcearch 32|64]
```

#### Common examples

- Local server using socket or `~/.my.cnf`:

```
python3 mysqltuner.py --config tuner.cnf --recommend
```

- Remote server with explicit credentials:

```
python3 mysqltuner.py --config minimal-tuner.cnf --host 10.1.2.3 --port 3306 --user root --pass secret --recommend
```

- Prompt for password (`-p` with no value):

```
python3 mysqltuner.py --config tuner.cnf --host 127.0.0.1 --user app -p
```

- Use a MySQL-style defaults file (reads `[client]` and `[mysqltuner]`; the latter overrides the former; CLI overrides both):

```
python3 mysqltuner.py --config tuner.cnf --defaults-extra-file=./tuner.local.cnf
```

Example `tuner.local.cnf`:

```
[client]
host=127.0.0.1
port=3306

[mysqltuner]
user=myuser
password=MY_SECRET_PASS
socket=/tmp/mysql.sock
```

- Offline analysis from files (each line as `key value`):

```
python3 mysqltuner.py --config minimal-tuner.cnf --filelist vars.txt,status.txt --forcemem 16384 --forceswap 8192 --forcearch 64
```

Notes:
- For remote hosts (anything other than `localhost` or `127.0.0.1`), `--forcemem` is required to mimic the original Perl behavior.
- `--output csv` prints `label,value` pairs; with `--recommend`, CSV adds `Recommendation,<text>` lines following triggering metrics.

### Behavior vs. Perl Version

- Expressions are Python, not Perl—double-check operator semantics, division, and regexes when porting custom rules.
- Uses a Python driver instead of shelling out to `mysql`/`mysqladmin`.
- Safer evaluation sandbox with a minimal set of helper functions.

### License

GPLv3 (mirrors the original `mysqltuner.pl`).