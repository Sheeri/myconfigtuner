#!/usr/bin/env python3
"""
mysqltuner.py - Python 3 port of mysqltuner.pl (v2.0.1)

High-level behavior:
- Reads MySQL server variables and status either by connecting to a live server
  or from offline files (--filelist), then evaluates expressions defined in a
  config file to produce human-readable metrics and optional recommendations.

Notes:
- This is a functional port focused on parity with the Perl script's CLI and flow.
- Expression evaluation uses Python syntax. If you are migrating an old config
  originally written for Perl, verify operators and function names.
"""

import argparse
import os
import re
import sys
from typing import Dict, List, Tuple, Any


 


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        add_help=False,
        description="Python port of mysqltuner.pl. Requires a config file.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # Required
    parser.add_argument("--config", dest="config", default=None, help="Path to config file with thresholds, calculations, and output")

    # Optional
    parser.add_argument("--filelist", dest="filelist", default=None, help="Comma-separated list of files to populate key/value hash in offline mode")
    parser.add_argument("--forcearch", dest="forcearch", type=int, default=None, help="Force architecture (32 or 64)")
    parser.add_argument("--forcemem", dest="forcemem", type=int, default=None, help="Use this RAM size (MB) instead of detecting local memory")
    parser.add_argument("--forceswap", dest="forceswap", type=int, default=None, help="Swap size (MB)")

    parser.add_argument("--host", dest="host", default=None, help="Hostname (default: localhost)")
    parser.add_argument("--socket", dest="socket", default=None, help="MySQL socket path")
    parser.add_argument("--port", dest="port", type=int, default=3306, help="Port (default: 3306)")
    parser.add_argument("--user", dest="user", default=None, help="Username")
    parser.add_argument("--pass", dest="password", default=None, help="Password")

    parser.add_argument("--debug", dest="debug", action="store_true", help="Enable debug output")
    parser.add_argument("--recommend", dest="recommend", action="store_true", help="Print recommendations at the end")
    parser.add_argument("--output", dest="output", choices=["pretty", "csv"], default="pretty", help="Output format (pretty|csv)")
    parser.add_argument("--help", action="store_true", help="Show this help message")
    parser.add_argument("--skipsize", dest="skipsize", action="store_true", help="Reserved for parity with Perl script")

    args = parser.parse_args()
    if args.help:
        print_usage_and_exit()
    if not args.config:
        print_usage_and_exit()
    return args


def print_usage_and_exit() -> None:
    prog = os.path.basename(sys.argv[0])
    print(
        f"\n   How to use {prog}:\n"
        f"    The script requires a config file.\n"
        f"    Example: '{prog} --config tuner-default.cnf'\n\n"
        f"    --config <filename>  File to use with thresholds, calculations, and output\n\n"
        f"   OPTIONAL COMMANDS\n"
        f"   Output and Recommendations\n"
        f"    --recommend          Output recommendations after results\n"
        f"    --output <type>      Output format, choices are 'pretty' (default) and 'csv'\n\n"
        f"   Connection and Authentication\n"
        f"    --host <hostname>    Host to connect to for data retrieval (default: localhost)\n"
        f"    --port <port>        Port to use for connection (default: 3306)\n"
        f"    --socket <socket>    Socket to connect to for data retrieval\n"
        f"    --user <username>    Username to use for authentication\n"
        f"    --pass <password>    Password to use for authentication\n\n"
        f"   Remote/Offline Options\n"
        f"    --filelist <f1,f2..> Comma-separated file(s) to populate the key/value hash\n"
        f"                         Use --filelist when you do not want to connect to a database to get\n"
        f"                         variable values. You must use --forcemem, --forceswap and --forcearch for remote.\n"
        f"    --forcemem <size>    Use this amount of RAM in MB instead of getting local memory size\n"
        f"    --forceswap <size>   Amount of swap memory configured in MB\n"
        f"    --forcearch 32|64    Architecture of operating system (32-bit or 64-bit)\n\n"
        f"   Misc\n"
        f"    --help               Shows this help message\n"
        f"    --debug              Show debug output\n"
    )
    sys.exit(1)


def debug_print(debug: bool, message: str) -> None:
    if debug:
        print(message)


def get_mysql_kv_from_live(args: argparse.Namespace) -> Dict[str, Any]:
    """Fetches SHOW GLOBAL VARIABLES and SHOW GLOBAL STATUS and flattens them into a single dict."""
    try:
        import mysql.connector as mysql
    except Exception as exc:  # pragma: no cover
        print(
            "ERROR: mysql-connector-python is required to connect to MySQL.\n"
            "Install with: pip install mysql-connector-python",
            file=sys.stderr,
        )
        raise

    connect_kwargs = {}
    if args.host:
        connect_kwargs["host"] = args.host
    if args.port:
        connect_kwargs["port"] = args.port
    if args.user:
        connect_kwargs["user"] = args.user
    if args.password is not None:
        connect_kwargs["password"] = args.password
    if args.socket and not args.host:
        connect_kwargs["unix_socket"] = args.socket

    # Enforce remote forcemem parity similar to Perl script
    if args.host and args.host not in ("127.0.0.1", "localhost") and args.forcemem is None:
        print("!! - The --forcemem option is required for remote connections", file=sys.stderr)
        sys.exit(20)

    try:
        connection = mysql.connect(**connect_kwargs)
    except Exception as exc:  # pragma: no cover
        print(f"Unable to connect to MySQL: {exc}", file=sys.stderr)
        sys.exit(30)

    cursor = connection.cursor()
    kv: Dict[str, Any] = {}
    for statement in ("SHOW /*!40003 GLOBAL */ VARIABLES", "SHOW /*!50002 GLOBAL */ STATUS"):
        cursor.execute(statement)
        rows = cursor.fetchall()
        # Expect 2 columns: Variable_name, Value
        for row in rows:
            if len(row) >= 2:
                key = str(row[0])
                value = row[1]
                kv[key] = value

    cursor.close()
    connection.close()
    return kv


def get_mysql_kv_from_files(filelist_arg: str, debug: bool) -> Dict[str, Any]:
    """
    Reads one or more files and parses lines into key/value pairs.
    Follows the Perl behavior: first token is key, remainder of the line is the value.
    """
    debug_print(debug, f"using filenames from list {filelist_arg}")
    kv: Dict[str, Any] = {}
    for filename in filelist_arg.split(","):
        filename = filename.strip()
        if not filename:
            continue
        try:
            with open(filename, "r", encoding="utf-8", errors="ignore") as f:
                for raw in f:
                    line = raw.rstrip("\n")
                    match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*(.*)", line)
                    if match:
                        key, value = match.group(1), match.group(2)
                        kv[key] = value
        except OSError:
            print(f"cannot open {filename}", file=sys.stderr)
            sys.exit(1)
    return kv


def read_config_file(path: str, debug: bool) -> List[str]:
    debug_print(debug, f"Reading from {path}")
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.readlines()


def is_numeric_string(value: str) -> bool:
    return bool(re.match(r"^-?\d+\.?\d*(e[+-]?\d+)?$", str(value), flags=re.IGNORECASE))


def round2_if_numeric(value: Any, expr_text: str) -> Any:
    if isinstance(value, (int, float)):
        return float(f"{float(value):.2f}")
    # When we get string results, mimic Perl behavior: only round numeric strings and skip 'version'
    if isinstance(value, str) and "version" not in expr_text.lower() and is_numeric_string(value):
        try:
            return float(f"{float(value):.2f}")
        except Exception:
            return value
    return value


# Helper functions available to expressions and formatting
def hr_bytime(per_second_rate: float) -> str:
    num = float(per_second_rate)
    label = "per second"
    if num >= 1:
        pass
    elif num * 60 >= 1:
        num = num * 60
        label = "per minute"
    elif num * 3600 >= 1:
        num = num * 3600
        label = "per hour"
    else:
        num = num * 86400
        label = "per day"
    return f"{round2_if_numeric(num, '')} {label}"


def hr_bytes(num: float) -> str:
    n = float(num)
    kb = 1024.0
    mb = kb * 1024.0
    gb = mb * 1024.0
    tb = gb * 1024.0
    pb = tb * 1024.0
    eb = pb * 1024.0
    zb = eb * 1024.0
    yb = zb * 1024.0
    
    if n >= yb:
        return f"{n / yb:.1f} Yb"
    if n >= zb:
        return f"{n / zb:.1f} Zb"
    if n >= eb:
        return f"{n / eb:.1f} Eb"
    if n >= pb:
        return f"{n / pb:.1f} Pb"
    if n >= tb:
        return f"{n / tb:.1f} Tb"
    if n >= gb:
        return f"{n / gb:.1f} Gb"
    if n >= mb:
        return f"{n / mb:.1f} Mb"
    if n >= kb:
        return f"{n / kb:.1f} Kb"
    return f"{int(n)} bytes" if n.is_integer() else f"{n} bytes"

def hr_num(num: float) -> str:
    n = float(num)
SCALES = [
    (1000.0**5, "Quadrillion"),
    (1000.0**4, "Trillion"),
    (1000.0**3, "Billion"),
    (1000.0**2, "Million"),
    (1000.0, "Thousand"),
]

def hr_num(num: float) -> str:
    n = float(num)
    for scale, name in SCALES:
        if n >= scale:
            return f"{int(n / scale)} {name}"
    return f"{int(n)}" if n.is_integer() else f"{n}"


def pretty_uptime(uptime_seconds: int) -> str:
    total = int(float(uptime_seconds))
    seconds = total % 60
    minutes = int((total % 3600) / 60)
    hours = int((total % 86400) / 3600)
    days = int(total / 86400)
    if days > 0:
        return f"{days}d {hours}h {minutes}m {seconds}s"
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def substr(s: Any, start: int, length: int = None) -> str:
    """Perl-like substr supporting start and optional length."""
    text = str(s)
    if length is None:
        return text[start:]
    return text[start:start + length]


def build_safe_eval_env(extra_vars: Dict[str, Any]) -> Dict[str, Any]:
    env: Dict[str, Any] = {
        # Safe builtins
        "__builtins__": {},
        # Numeric helpers
        "abs": abs,
        "min": min,
        "max": max,
        "int": int,
        "float": float,
        "round": round,
        "len": len,
        # Human-readable helpers
        "hr_bytime": hr_bytime,
        "hr_bytes": hr_bytes,
        "hr_num": hr_num,
        "pretty_uptime": pretty_uptime,
        # String helpers
        "substr": substr,
    }
    env.update(extra_vars)
    return env


def substitute_expr_variables(expr: str, variables: Dict[str, Any]) -> str:
    """
    Replace identifiers that match keys in `variables` with their values (stringified),
    similar to Perl's word-boundary substitution.
    """

    def repl(match: re.Match) -> str:
        word = match.group(0)
        if word in variables:
            value = variables[word]
            # Preserve numeric values; quote strings
            if isinstance(value, (int, float)):
                return str(value)
            # Treat numeric strings as numbers
            if isinstance(value, str) and is_numeric_string(value):
                return value
            # Fallback: quote strings and other types
            return repr(value)
        return word

    return re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", repl, expr)


def build_condition_expression(comp_text: str, value_alias: str = "v") -> str:
    """Convert legacy comparison syntax to a Python expression using alias `v` as the expr value.

    Supported conversions:
    - eq/ne -> ==/!=
    - =~ /re/flags -> re.search(r"re", str(v), flags) is not None
    - !~ /re/flags -> re.search(...) is None
    - Leading method call like .lower()... -> str(v).lower()...
    - Leading binary operators (<, >, <=, >=, ==, !=) -> v <op> rhs
    - Otherwise: treat as a Python expression that can reference v
    """
    text = comp_text.strip()

    # Regex matchers
    m = re.match(r"=~\s*/(.+?)/([a-zA-Z]*)$", text)
    if m:
        pattern, flags = m.groups()
        pyflags = []
        if flags and "i" in flags.lower():
            pyflags.append("re.I")
        flags_expr = " | ".join(pyflags) if pyflags else "0"
        return f"re.search(r'{pattern}', str({value_alias}), {flags_expr}) is not None"

    m = re.match(r"!~\s*/(.+?)/([a-zA-Z]*)$", text)
    if m:
        pattern, flags = m.groups()
        pyflags = []
        if flags and "i" in flags.lower():
            pyflags.append("re.I")
        flags_expr = " | ".join(pyflags) if pyflags else "0"
        return f"re.search(r'{pattern}', str({value_alias}), {flags_expr}) is None"

    # Equality aliases
    if text.startswith("eq "):
        return f"{value_alias} == {text[3:].strip()}"
    if text.startswith("ne "):
        return f"{value_alias} != {text[3:].strip()}"

    # Leading method call on value
    if text.startswith('.'):
        return f"str({value_alias}){text}"

    # Leading comparison operators
    if re.match(r"^[<>!=]", text):
        return f"{value_alias} {text}"

    # Otherwise assume it's a full Python expression referencing v
    return text


def parse_config_line(line: str) -> Tuple[str, str, str, str]:
    parts = line.split("|||")
    if len(parts) != 4:
        raise ValueError("Invalid config line (expected 4 fields separated by '|||')")
    label, comp, expr, output = [p.strip() for p in parts]
    return label, comp, expr, output


def evaluate_and_print(
    lines: List[str],
    variables: Dict[str, Any],
    output_mode: str,
    debug: bool,
    show_recommendations: bool,
) -> None:
    # Keep pairs of (displayed_metric_line, recommendation_text)
    recommendation_pairs: List[Tuple[str, str]] = []
    current_category: str = ""

    for raw in lines:
        if not raw.strip():
            continue
        # Handle category headers expressed as comment lines without rules
        if raw.lstrip().startswith("#"):
            if "|||" not in raw:
                # Only treat lines with an explicit Category label as headers
                m_cat = re.match(r"^\s*#\s*Category\s*:\s*(.+?)\s*$", raw, flags=re.IGNORECASE)
                if m_cat:
                    category_text = m_cat.group(1)
                    if category_text and category_text != current_category:
                        current_category = category_text
                        if output_mode == "csv":
                            print(f"Category,{current_category}")
                        else:
                            print(f"\n{current_category}")
                # Regardless, skip pure comment lines
                continue
            # Commented-out rule; skip
            continue
        try:
            label, comp, expr, output_text = parse_config_line(raw)
        except Exception:
            # Skip malformed lines silently to mimic robustness
            continue

        if debug:
            print(f"expr starts as {expr}")
        parsed_expr = substitute_expr_variables(expr, variables)
        if debug:
            print(f"expr after parsing is {parsed_expr}")

        try:
            value = eval(parsed_expr, build_safe_eval_env({}))
        except Exception:
            # Fall back to raw string if eval fails
            value = parsed_expr

        if debug:
            print(f"expr evals to '{value}'")

        if output_mode == "csv":
            displayed_metric_line = f"{label},{value}"
            print(displayed_metric_line)
        else:
            displayed_metric_line = f"{label}: {round2_if_numeric(value, expr)}"
            print(displayed_metric_line)

        # Determine if recommendation condition is met
        comp_text = comp.strip()
        if comp_text:
            try:
                condition_ok = bool(
                    eval(
                        build_condition_expression(comp_text, value_alias="v"),
                        build_safe_eval_env({"re": re, "v": value, "_": value}),
                    )
                )
            except Exception:
                condition_ok = False
        else:
            condition_ok = False

        if condition_ok:
            if debug:
                print(f"\t{label} matches {comp_text}")
            recommendation_pairs.append((displayed_metric_line, output_text))

    if show_recommendations and recommendation_pairs:
        print("\n\nRECOMMENDATIONS:")
        if output_mode == "csv":
            # CSV: print the metric line followed by a Recommendation line
            for metric_line, rec_text in recommendation_pairs:
                print(metric_line)
                print(f"Recommendation,{rec_text}")
        else:
            # Pretty: print the metric line (bold), then the recommendation, then a blank line
            ANSI_BOLD = "\033[1m"
            ANSI_RESET = "\033[0m"
            for metric_line, rec_text in recommendation_pairs:
                print(f"{ANSI_BOLD}{metric_line}{ANSI_RESET}")
                print(rec_text)
                print("")


def main() -> None:
    args = parse_args()

    # Determine mode: offline from files or live server
    if args.filelist:
        args.skipsize = True
        variables = get_mysql_kv_from_files(args.filelist, args.debug)
    else:
        variables = get_mysql_kv_from_live(args)

    # Read and parse the provided config file
    config_lines = read_config_file(args.config, args.debug)

    # Convert all keys to plain strings for uniform replacement
    flattened_vars: Dict[str, Any] = {}
    for key, value in variables.items():
        # Normalize keys to match Perl behavior (keys are case-sensitive in MySQL)
        flattened_vars[str(key)] = value

    evaluate_and_print(
        lines=config_lines,
        variables=flattened_vars,
        output_mode=args.output,
        debug=args.debug,
        show_recommendations=args.recommend,
    )


if __name__ == "__main__":
    main()


