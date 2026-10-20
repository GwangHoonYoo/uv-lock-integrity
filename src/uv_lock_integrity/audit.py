"""Read TOML files only. Never import project code or invoke a resolver."""
from pathlib import Path
import re
import tomllib

from packaging.markers import Marker, default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version


class Unexamined(ValueError):
    pass


def table(value):
    if not isinstance(value, dict):
        raise ValueError("Expected a TOML table")
    return value


def array(value):
    if not isinstance(value, list):
        raise ValueError("Expected a TOML array")
    return value


def name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ValueError("Invalid package name")
    return canonicalize_name(value)


def environment(custom=None):
    keys = set(default_environment())
    env = default_environment() if custom is None else custom
    if not isinstance(env, dict) or set(env) != keys or any(not isinstance(v, str) for v in env.values()):
        raise ValueError("Environment must supply exactly all keys shown by --show-environment")
    full = Version(env['python_full_version'])
    if '.'.join(map(str, full.release[:2])) != env['python_version']:
        raise ValueError("python_version must match python_full_version major.minor")
    Version(env['implementation_version'])
    if not SpecifierSet('>=3.11').contains(full):
        raise ValueError("Target Python must be >=3.11")
    return dict(env)


def active(expression, env):
    # uv also uses extra/conflict-specific marker contexts. Do not evaluate those
    # as empty extras and accidentally report a successful environment audit.
    if not isinstance(expression, str):
        raise ValueError("Marker must be a string")
    if re.search(r"\b(extra|extras|dependency_groups)\b", expression):
        raise Unexamined("Extra/group-specific marker context is outside production scope")
    return Marker(expression).evaluate(env)


def inside(root, path):
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise Unexamined("Manifest/source path escapes the project root")
    return resolved


def read(path):
    with path.open('rb') as stream:
        return tomllib.load(stream)


def audit(project, env=None):
    result = {'schema_version': 1, 'status': 'inconclusive', 'exit_code': 2,
              'target_environment': {}, 'scope': 'root and workspace direct production version constraints',
              'findings': [], 'checks': [], 'unexamined': [
                  'transitive dependency constraints', 'optional dependencies/extras',
                  'dependency groups', 'wheel availability', 'build and runtime compatibility',
                  'artifact contents, hashes and authenticity',
                  'vulnerabilities', 'other target environments'], 'errors': []}
    root = Path(project).resolve()

    def issue(code, message, manifest=None, **details):
        result['errors'].append(dict(code=code, message=message, **({'manifest': manifest} if manifest else {}), **details))

    try:
        env = environment(env)
        result['target_environment'] = env
        lock = read(inside(root, root/'uv.lock'))
        config = read(inside(root, root/'pyproject.toml'))
        if type(lock.get('version')) is not int or lock['version'] != 1 or type(lock.get('revision', 0)) is not int or not 0 <= lock.get('revision', 0) <= 3:
            raise Unexamined("Supported lock format: version1, revisions0 through3")
        if not SpecifierSet(lock.get('requires-python', '')).contains(env['python_full_version'], prereleases=True):
            raise Unexamined("Target environment is outside uv.lock requires-python")
        if any(table(lock.get('manifest', {})).get(k) for k in ('overrides','constraints','dependency-metadata')):
            raise Unexamined("Lock manifest contains unsupported dependency transformations")
        packages = array(lock.get('package'))
        for p in packages:
            table(p); name(p.get('name')); Version(p['version']); table(p.get('source'))
        manifests = [(root/'pyproject.toml', config)]
        uv = table(table(config.get('tool', {})).get('uv', {}))
        workspace = table(uv.get('workspace', {}))
        exclusions = set()
        for pattern in array(workspace.get('exclude', [])):
            if not isinstance(pattern, str) or Path(pattern).is_absolute() or '..' in Path(pattern).parts:
                raise Unexamined('Workspace patterns must remain inside the project')
            exclusions.update(inside(root, p) for p in root.glob(pattern))
        members = set()
        for pattern in array(workspace.get('members', [])):
            if not isinstance(pattern, str) or Path(pattern).is_absolute() or '..' in Path(pattern).parts:
                raise Unexamined('Workspace patterns must remain inside the project')
            matches = list(root.glob(pattern))
            if not matches:
                raise Unexamined(f"Workspace member pattern has no local matches: {pattern}")
            for member in matches:
                member = inside(root, member)
                if member not in exclusions:
                    members.add(member)
        for member in sorted(members):
            if member == root:
                continue
            manifests.append((member/'pyproject.toml', read(inside(root, member/'pyproject.toml'))))
        for path, manifest in manifests:
            label = path.relative_to(root).as_posix()
            project_data = table(manifest.get('project', {}))
            settings = table(table(manifest.get('tool', {})).get('uv', {}))
            for key in ('override-dependencies','constraint-dependencies','dependency-metadata','exclude-dependencies'):
                if settings.get(key):
                    issue('unsupported_transform', f"tool.uv.{key} requires resolver semantics", label)
            if 'dependencies' in array(project_data.get('dynamic', [])):
                issue('dynamic_dependencies', 'Dynamic dependencies require executing project code', label)
                continue
            if not project_data:
                if path.parent != root:
                    issue('missing_project', 'Workspace member has no static project table', label)
                continue
            requires_python = project_data.get('requires-python', '')
            if not SpecifierSet(requires_python).contains(env['python_full_version'], prereleases=True):
                issue('target_outside_project', 'Target is outside project requires-python', label)
                continue
            project_name = name(project_data.get('name'))
            rel = path.parent.relative_to(root).as_posix()
            owners = [p for p in packages if name(p['name']) == project_name and
                      any(p['source'].get(k) == rel for k in ('editable','virtual','path'))]
            if len(owners) != 1:
                issue('ambiguous_project', 'Expected exactly one matching local project lock entry', label)
                continue
            owner = owners[0]
            edges = array(owner.get('dependencies', []))
            sources = table(settings.get('sources', {}))
            # Workspace source declarations may be inherited from its root.
            sources = {**table(uv.get('sources', {})), **sources}
            declared_names = set()
            for raw in array(project_data.get('dependencies', [])):
                try:
                    req = Requirement(raw)
                    dep_name = name(req.name)
                    if req.marker and not active(str(req.marker), env):
                        result['checks'].append(dict(manifest=label, requirement=raw, status='inactive'))
                        continue
                    declared_names.add(dep_name)
                    if req.url:
                        raise Unexamined('Direct URL requirements are outside registry/workspace scope')
                    source = sources.get(dep_name)
                    if source is None:
                        source = next((v for k, v in sources.items() if name(k) == dep_name), None)
                    if source is not None and source != {'workspace': True}:
                        raise Unexamined('Source override is outside registry/workspace scope')
                    matches = []
                    for edge in edges:
                        table(edge)
                        if name(edge.get('name')) != dep_name:
                            continue
                        if set(edge) - {'name','version','source','marker','extra'}:
                            raise Unexamined('Unknown lock dependency edge fields')
                        if edge.get('marker') and not active(edge['marker'], env):
                            continue
                        candidates = [p for p in packages if name(p['name']) == dep_name]
                        if 'version' in edge:
                            candidates = [p for p in candidates if p['version'] == edge['version']]
                        if 'source' in edge:
                            candidates = [p for p in candidates if p['source'] == edge['source']]
                        for p in candidates:
                            markers = array(p.get('resolution-markers', []))
                            if markers and not any(active(m, env) for m in markers):
                                continue
                            if p not in matches:
                                matches.append(p)
                    if len(matches) != 1:
                        raise Unexamined(f'Expected one applicable lock target, found {len(matches)}')
                    selected = matches[0]
                    if source == {'workspace': True}:
                        local = next((selected['source'][k] for k in ('editable','virtual','path') if k in selected['source']), None)
                        if local is None or inside(root, root/local) not in members:
                            raise Unexamined('Workspace source does not resolve to a declared local member')
                    elif set(selected['source']) != {'registry'} or not isinstance(selected['source']['registry'], str):
                        raise Unexamined('Selected dependency source is not a registry package')
                    record = dict(manifest=label, requirement=raw, dependency=dep_name, locked_version=selected['version'])
                    if req.specifier.contains(selected['version'], prereleases=True):
                        result['checks'].append(dict(record, status='consistent'))
                    else:
                        result['findings'].append(dict(record, code='dependency_constraint_violation'))
                except Unexamined as exc:
                    issue('unsupported_dependency', str(exc), label, requirement=raw)
            # Unexpected active edges mean the declaration and graph disagree.
            for edge in edges:
                table(edge)
                if edge.get('marker') and not active(edge['marker'], env):
                    continue
                if name(edge.get('name')) not in declared_names:
                    issue('undeclared_lock_edge', 'Active lock dependency has no active production declaration', label, dependency=edge['name'])
        if not result['checks'] and not result['findings'] and not result['errors']:
            issue('empty_scope', 'No production requirements were available to check')
    except Unexamined as exc:
        issue('unsupported_input', str(exc))
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        issue('input_error', str(exc))
    if result['errors']:
        result['status'], result['exit_code'] = 'inconclusive', 2
    elif result['findings']:
        result['status'], result['exit_code'] = 'violations', 1
    else:
        result['status'], result['exit_code'] = 'consistent', 0
    return result
