#!/usr/bin/env python3
"""Create a consistent private SQLite backup; retain only this tool's snapshots."""
import argparse
import datetime as dt
import os
from pathlib import Path
import sqlite3
import uuid


def backup(database, directory, keep=14):
    if keep < 1:
        raise ValueError('keep must be positive')
    os.umask(0o077)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    filename = 'cloud-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8] + '.sqlite3'
    temporary = directory / (filename + '.partial')
    final = directory / filename
    try:
        with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(temporary) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup integrity check failed')
        temporary.chmod(0o600)
        temporary.rename(final)
    finally:
        temporary.unlink(missing_ok=True)
    for old in sorted(directory.glob('cloud-*.sqlite3'), reverse=True)[keep:]:
        old.unlink()
    return final


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--keep',type=int,default=14)
    args=parser.parse_args()
    print(backup(args.database,args.out,args.keep))


if __name__=='__main__':
    main()
