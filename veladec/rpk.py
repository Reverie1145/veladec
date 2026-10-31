"""rpk / jsc input handling."""

import io
import json
import os
import zipfile

JSC_SUFFIX = '.jsc'


class Target:
    """A set of .jsc files plus optional manifest, from rpk / jsc / directory."""

    def __init__(self, path):
        self.path = path
        self.kind = None
        self.manifest = {}
        self.files = {}          # archive-relative name -> bytes
        self._load()

    def _load(self):
        p = self.path
        if os.path.isdir(p):
            self.kind = 'dir'
            for root, _dirs, files in os.walk(p):
                for fn in sorted(files):
                    if fn.endswith(JSC_SUFFIX):
                        full = os.path.join(root, fn)
                        rel = os.path.relpath(full, p)
                        self.files[rel] = open(full, 'rb').read()
            mf = os.path.join(p, 'manifest.json')
            if os.path.exists(mf):
                self.manifest = _load_manifest(open(mf, 'rb').read())
            return
        raw = open(p, 'rb').read()
        if raw[:2] == b'PK':
            self.kind = 'rpk'
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                for info in z.infolist():
                    if info.filename.endswith(JSC_SUFFIX):
                        self.files[info.filename] = z.read(info.filename)
                    elif info.filename in ('manifest.json', 'manifest-watch.json'):
                        self.manifest.update(_load_manifest(z.read(info.filename)))
            return
        self.kind = 'jsc'
        self.files[os.path.basename(p)] = raw
        self.manifest = {}

    # ------------------------------------------------------------------
    def summary(self):
        return {
            'path': self.path,
            'kind': self.kind,
            'jsc_files': sorted(self.files),
            'package': self.manifest.get('package'),
            'name': self.manifest.get('name'),
            'version': '%s (%s)' % (self.manifest.get('versionName'),
                                    self.manifest.get('versionCode'))
            if self.manifest else None,
            'minPlatformVersion': self.manifest.get('minPlatformVersion'),
            'deviceType': self.manifest.get('deviceTypeList'),
            'features': sorted(self.manifest.get('features') or []),
            'toolkit': ((self.manifest.get('packageInfo') or {}).get('toolkit')
                        if isinstance(self.manifest.get('packageInfo'), dict) else None),
            'pages': self.manifest.get('router', {}).get('pages')
            if isinstance(self.manifest.get('router'), dict) else None,
        }


def _load_manifest(raw):
    try:
        d = json.loads(raw.decode('utf-8-sig'))
    except Exception:
        return {}
    if isinstance(d, dict) and isinstance(d.get('features'), list):
        names = []
        for f in d['features']:
            if isinstance(f, dict):
                names.append(f.get('name') or '?')
            else:
                names.append(str(f))
        d['features'] = names
    r = d.get('router') if isinstance(d, dict) else None
    if isinstance(r, dict):
        pages = r.get('pages')
        if isinstance(pages, dict):
            r['pages'] = list(pages.keys())
        elif isinstance(pages, list):
            r['pages'] = [p.get('path') if isinstance(p, dict) else str(p) for p in pages]
    return d


def dump_files(target, outdir):
    """Write every .jsc of the target to outdir, keeping relative layout."""
    written = []
    for rel, data in sorted(target.files.items()):
        dst = os.path.join(outdir, rel.replace('\\', '/'))
        os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
        with open(dst, 'wb') as fh:
            fh.write(data)
        written.append((rel, dst, len(data)))
    return written
