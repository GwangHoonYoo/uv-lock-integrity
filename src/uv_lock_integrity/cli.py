import argparse
import json
from pathlib import Path

from packaging.markers import default_environment

from . import __version__
from .audit import audit


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline read-only audit of direct production version constraints in uv.lock')
    parser.add_argument('project', nargs='?', default='.', help='Directory containing pyproject.toml and uv.lock')
    parser.add_argument('--format', choices=['text','json'], default='text')
    parser.add_argument('--environment', type=Path, help='Complete PEP508 marker environment JSON; defaults to this interpreter')
    parser.add_argument('--show-environment', action='store_true', help='Print this interpreter marker environment as JSON')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)
    if args.show_environment:
        print(json.dumps(default_environment(), sort_keys=True, indent=2))
        return 0
    try:
        custom = json.loads(args.environment.read_text()) if args.environment else None
    except (OSError, ValueError) as exc:
        result = audit(args.project, {})
        result['errors'] = [{'code': 'input_error', 'message': str(exc)}]
    else:
        result = audit(args.project, custom)
    if args.format == 'json':
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print(f"{result['status'].upper()}: {len(result['findings'])} contradiction(s), {len(result['errors'])} unresolved condition(s)")
        if result.get('target_environment'):
            env = result['target_environment']
            print(f"Target: Python {env['python_full_version']}, {env['sys_platform']}, {env['platform_machine']}")
        for finding in result['findings']:
            print(f"{finding['manifest']}: {finding['requirement']} rejects locked {finding['locked_version']}")
        for error in result['errors']:
            print(f"{error.get('manifest', 'input')}: {error['code']}: {error['message']}")
        print('Scope: direct production version constraints. Use --format json for checks and unexamined scope.')
    return result['exit_code']
