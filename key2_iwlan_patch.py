#!/usr/bin/env python3
"""Provisional IWLAN network-list fix for one SHA-256-pinned FP3 radio library.

No adb, firmware, NV/EFS, build-environment or OUT_DIR operations.
The extraction callback and CLI share the same checked binary transformation.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

SPEC = {'original_sha256': '60de0168e73eef0c54d718d467a575e2073edbd52b36c559752f7fbf3f1529d3', 'patched_sha256': 'f568f7436f81961815aa4e2456247a824052264369edd975039b53d77342a58d', 'original_sha1': 'cc70a2e8e2435dee4cb396dadbcd7c4c244287bd', 'patched_sha1': '97b9c5abcc28f45da45149e81b3a7f4f0df2e065', 'size': 33687744, 'patches': [{'offset': 22118480, 'old': 'a8a640a9', 'new': '54000014'}, {'offset': 22118816, 'old': 'c8482094f40300aae8030591e073079178972094e26fffd0e0030591e1031faa42681a91534a20940000c03d080840f9e1030691e063803de8cb00f91ffc00a91f0000f9e00314aaba482094', 'new': 'a8a640a9ea0308aaeb0308aa5f0109ebc00000544c4540b84c0000346c4500b85f0109eb81ffff54ab0a00f91f010beb00160054a4ffff171f2003d51f2003d51f2003d51f2003d51f2003d5'}], 'source_changes': {'device/blackberry/sdm660-common/extract-files.py': {'original_sha256': '5dd6c99ec29c415b89a0e017df38652b1805eb7c0f9b6256adf80be3db1eca1d', 'patched_sha256': '4cd546ace66a7ca11494eb3d75ea42c8b39e1f59c79ec2d7701cb09409d92138'}, 'device/blackberry/sdm660-common/proprietary-files.txt': {'original_sha256': '2047c9646ec1d03fa03c20c2a2ed5dc0c84b086ff06d7679141a71b71273036b', 'patched_sha256': '9228c0c1352c58feba0e01e2117a96807e1f8a51c046e5d389dc747d0adc782f'}}}
RADIO = 'vendor/blackberry/sdm660-common/proprietary/vendor/lib64/libril-qc-hal-qmi.so'
HELPER = 'device/blackberry/sdm660-common/key2_iwlan_patch.py'
DEFAULT_ROOT = '/mnt/android-building/android'
DEFAULT_WORK = '/mnt/android-building/AI-work-files'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patched_bytes(data):
    digest = sha(data)
    if digest == SPEC['patched_sha256']:
        return data
    if digest != SPEC['original_sha256']:
        raise RuntimeError('Unsupported radio-library SHA-256: ' + digest +
                           '; no bytes changed. Obtain a patch for this exact library.')
    if len(data) != SPEC['size']:
        raise RuntimeError('Unexpected library size')
    result = bytearray(data)
    for patch in SPEC['patches']:
        offset = patch['offset']
        old = bytes.fromhex(patch['old'])
        new = bytes.fromhex(patch['new'])
        if len(old) != len(new) or data[offset:offset + len(old)] != old:
            raise RuntimeError('Original instructions do not match at ' + hex(offset))
        result[offset:offset + len(old)] = new
    result = bytes(result)
    if len(result) != len(data) or sha(result) != SPEC['patched_sha256']:
        raise RuntimeError('Patched library verification failed')
    return result


def modified_source(relative, data):
    text = data.decode()
    if relative.endswith('/extract-files.py'):
        loader = ("from pathlib import Path\nfrom runpy import run_path\n\n"
                  "# Also works when this module is loaded by the Athena/Luna extractor.\n"
                  "fixup_iwlan_network_list = run_path(\n"
                  "    str(Path(__file__).with_name('key2_iwlan_patch.py'))\n"
                  ")[\"fixup_iwlan_network_list\"]\n\n")
        text = text.replace('from extract_utils.fixups_blob import (',
                            loader + 'from extract_utils.fixups_blob import (', 1)
        anchor = ("    #'vendor/lib64/libril-qc-hal-qmi.so': blob_fixup()\n"
                  "    #    .replace_needed('android.hardware.radio.config@1.0.so', "
                  "'android.hardware.radio.c_shim@1.0.so'),")
        if text.count(anchor) != 1:
            raise RuntimeError('Extraction integration anchor does not match')
        text = text.replace(anchor,
                            "    # Filter UNKNOWN entries without discarding a later valid IWLAN network.\n"
                            "    'vendor/lib64/libril-qc-hal-qmi.so': blob_fixup()\n"
                            "        .call(fixup_iwlan_network_list, need_tmp_dir=False),", 1)
    elif relative.endswith('/proprietary-files.txt'):
        line = 'vendor/lib64/libril-qc-hal-qmi.so|' + SPEC['original_sha1']
        if text.splitlines().count(line) != 1:
            raise RuntimeError('Original blob pin does not match')
        text = text.replace(line + '\n', line + '|' + SPEC['patched_sha1'] + '\n', 1)
    else:
        raise RuntimeError('Unsupported source integration path')
    result = text.encode()
    if sha(result) != SPEC['source_changes'][relative]['patched_sha256']:
        raise RuntimeError('Source integration verification failed: ' + relative)
    return result


def atomic_write(path, data, mode):
    # Caller creates/preflights directories before any source mutation.
    fd, temp = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def fixup_iwlan_network_list(ctx, file, file_path, *args, **kwargs):
    """Extract-utils callback; accepts original or already-patched exact blob."""
    path = Path(file_path)
    old = path.read_bytes()
    new = patched_bytes(old)
    if new != old:
        atomic_write(path, new, stat.S_IMODE(path.stat().st_mode))
    if sha(path.read_bytes()) != SPEC['patched_sha256']:
        raise RuntimeError('Radio-library readback verification failed')


def verify(root):
    paths = {RADIO: SPEC['patched_sha256']}
    paths.update({p: s['patched_sha256'] for p, s in SPEC['source_changes'].items()})
    for relative, expected in paths.items():
        path = root / relative
        if not path.is_file() or sha(path.read_bytes()) != expected:
            raise RuntimeError('Verification failed: ' + str(path))
        print('PASS: ' + relative)
    helper = root / HELPER
    if not helper.is_file() or helper.read_bytes() != Path(__file__).read_bytes():
        raise RuntimeError('Installed extraction helper differs from this package')
    print('PASS: extraction helper')


def restore(backup):
    manifest = json.loads((backup / 'backup.json').read_text())
    root = Path(manifest['android_root'])
    # Preflight every file before restoring anything, protecting later user edits.
    for item in manifest['files']:
        path = root / item['path']
        actual = sha(path.read_bytes()) if path.is_file() else None
        if actual not in (item['original_sha256'], item['patched_sha256']):
            raise RuntimeError('Refusing to overwrite later edits: ' + str(path))
        if item['original_sha256'] is not None:
            original = (backup / 'original' / item['path']).read_bytes()
            if sha(original) != item['original_sha256']:
                raise RuntimeError('Backup integrity check failed: ' + item['path'])
    for item in reversed(manifest['files']):
        path = root / item['path']
        if item['original_sha256'] is None:
            if path.exists():
                path.unlink()
        else:
            atomic_write(path, (backup / 'original' / item['path']).read_bytes(), item['mode'])
    print('RESTORED: original library and extraction files. Rebuild normally before flashing.')


def apply(root, work):
    if sha((root / RADIO).read_bytes()) == SPEC['patched_sha256']:
        verify(root)
        print('Already applied; no new backup or changes.')
        return
    planned = []
    radio_path = root / RADIO
    original = radio_path.read_bytes()
    planned.append((RADIO, original, patched_bytes(original), stat.S_IMODE(radio_path.stat().st_mode)))
    for relative, change in SPEC['source_changes'].items():
        path = root / relative
        old = path.read_bytes()
        if sha(old) != change['original_sha256']:
            raise RuntimeError('Source changed since review: ' + str(path) +
                               '; no source files modified. Send the current file for integration.')
        planned.append((relative, old, modified_source(relative, old), stat.S_IMODE(path.stat().st_mode)))
    helper = root / HELPER
    if helper.exists():
        raise RuntimeError('Refusing to overwrite existing helper: ' + str(helper))
    planned.append((HELPER, None, Path(__file__).read_bytes(), 0o644))
    backup = work / ('key2-iwlan-network-list-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'android_root': str(root), 'files': []}
    for relative, old, new, mode in planned:
        if old is not None:
            saved = backup / 'original' / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(old)
            if sha(saved.read_bytes()) != sha(old):
                raise RuntimeError('Backup readback failed')
        manifest['files'].append({'path': relative, 'original_sha256': sha(old) if old is not None else None,
                                  'patched_sha256': sha(new), 'mode': mode})
    (backup / 'backup.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Backup directory: ' + str(backup), flush=True)
    try:
        for relative, old, new, mode in planned:
            path = root / relative
            actual = path.read_bytes() if path.exists() else None
            if actual != old:
                raise RuntimeError('Concurrent source change detected: ' + str(path))
            atomic_write(path, new, mode)
        verify(root)
    except Exception:
        # Do not overwrite concurrent/later user edits during rollback.
        restore(backup)
        raise
    print('APPLIED: provisional radio-library fix and persistent extraction integration.')
    print('Restore command: python3 ' + str(Path(__file__).resolve()) + ' restore --backup ' + str(backup))
    print('Build normally in your usual shell and output directory. No build settings were changed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('apply', 'verify'):
        command = sub.add_parser(name)
        command.add_argument('--android-root', default=DEFAULT_ROOT)
        if name == 'apply':
            command.add_argument('--work-dir', default=DEFAULT_WORK)
    command = sub.add_parser('restore')
    command.add_argument('--backup', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'restore':
            restore(Path(args.backup).resolve())
        elif args.action == 'verify':
            verify(Path(args.android_root).resolve())
        else:
            apply(Path(args.android_root).resolve(), Path(args.work_dir).resolve())
    except (OSError, RuntimeError, ValueError) as error:
        print('STOP: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
