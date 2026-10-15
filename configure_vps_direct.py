#!/usr/bin/env python3
"""Install a narrow VPS exception in an existing ps3-vpn gateway. No local DNS/TLS relay."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

MARKER = 'Managed by Darksiders II configure_vps_direct.py'
CODE = Path('/usr/local/lib/ps3-vpn/ds2_vps_direct.py')
CONFIG = Path('/etc/ps3-vpn/ds2-vps-direct.json')
DROPIN = Path('/etc/systemd/system/ps3-vpn.service.d/20-ds2-vps-direct.conf')
COMMENT = 'ds2-vps-direct'


def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True)


def validate(config):
    for key in ('server', 'client'):
        config[key] = str(ipaddress.IPv4Address(config[key]))
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', config['interface']):
        raise ValueError('Invalid interface')
    if type(config['priority']) is not int or not 1 <= config['priority'] < 10178:
        raise ValueError('Choose a free priority below ps3-vpn priority 10178')
    if type(config['dns_port']) is not int or not 1024 <= config['dns_port'] <= 65535:
        raise ValueError('Extra VPS DNS port must be 1024..65535')
    if config['server'] == config['client']:
        raise ValueError('VPS must differ from PS3')
    return config


def specs(c):
    client, server, interface = c['client']+'/32', c['server']+'/32', c['interface']
    comment = ['-m', 'comment', '--comment', COMMENT]
    forward = ['-i', interface, '-o', interface, '-s', client, '-d', server]
    return [
        ('nat', 'PREROUTING', ['-i', interface, '-s', client, '-d', server, '-p', proto,
          '--dport', '53', *comment, '-j', 'DNAT', '--to-destination', c['server']+':'+str(c['dns_port'])])
        for proto in ('udp', 'tcp')
    ] + [
        ('filter', 'OUTPUT', ['-d', client, '-p', 'icmp', '--icmp-type', 'redirect',
          *comment, '-j', 'DROP']),
        ('filter', 'FORWARD', [*forward, '-p', 'tcp', '-m', 'multiport', '--dports',
          f"443,8443,{c['dns_port']}", *comment, '-j', 'ACCEPT']),
        ('filter', 'FORWARD', [*forward, '-p', 'udp', '--dport', str(c['dns_port']),
          *comment, '-j', 'ACCEPT']),
        ('filter', 'FORWARD', ['-i', interface, '-o', interface, '-s', server, '-d', client,
          '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', *comment, '-j', 'ACCEPT']),
        ('nat', 'POSTROUTING', ['-s', client, '-d', server, '-o', interface,
          *comment, '-j', 'MASQUERADE']),
    ]


def rule_state(c):
    occupied = [r for r in json.loads(run('ip', '-j', 'rule', 'show').stdout) if r.get('priority') == c['priority']]
    if occupied and not (len(occupied) == 1 and occupied[0].get('src') in (c['client'], c['client']+'/32')
                         and occupied[0].get('dst') in (c['server'], c['server']+'/32')
                         and occupied[0].get('table') in ('main', 254)):
        raise ValueError('Chosen rule priority is occupied by another configuration')
    return occupied


def apply(c):
    # Parent installs its rejection rule before priority10178; wait for that marker.
    for _ in range(50):
        rules = json.loads(run('ip', '-j', 'rule', 'show').stdout)
        if any(r.get('priority') == 10178 and r.get('src') in (c['client'],c['client']+'/32') for r in rules):
            break
        time.sleep(.2)
    else:
        raise ValueError('Expected ps3-vpn source rule10178 is not ready')
    if Path('/proc/sys/net/ipv4/ip_forward').read_text().strip() != '1':
        raise ValueError('Existing gateway must already enable IPv4 forwarding')
    route = json.loads(run('ip', '-j', 'route', 'get', c['server']).stdout)
    if not route or route[0].get('dev') != c['interface']:
        raise ValueError('Normal PC route to VPS does not use the configured LAN interface')
    occupied = rule_state(c)
    added = []
    rule_added = False
    try:
        for table, chain, spec in specs(c):
            exists = run('iptables','-w','5','-t',table,'-C',chain,*spec,check=False)
            if exists.returncode:
                run('iptables','-w','5','-t',table,'-I',chain,'1',*spec)
                added.append((table,chain,spec))
        if not occupied:
            run('ip','rule','add','priority',str(c['priority']),'from',c['client']+'/32',
                'to',c['server']+'/32','lookup','main')
            rule_added = True
    except BaseException:
        if rule_added:
            run('ip','rule','del','priority',str(c['priority']),'from',c['client']+'/32',
                'to',c['server']+'/32','lookup','main',check=False)
        for table,chain,spec in reversed(added):
            run('iptables','-w','5','-t',table,'-D',chain,*spec,check=False)
        raise
    print('VPS-only route and DNS port translation applied; PSN keeps existing VPN route.')


def stop(c):
    occupied = rule_state(c)
    if occupied:
        run('ip','rule','del','priority',str(c['priority']),'from',c['client']+'/32',
            'to',c['server']+'/32','lookup','main')
    for table,chain,spec in reversed(specs(c)):
        while run('iptables','-w','5','-t',table,'-C',chain,*spec,check=False).returncode == 0:
            run('iptables','-w','5','-t',table,'-D',chain,*spec)
    print('Only project VPS rules removed; base ps3-vpn configuration retained.')


def install(c):
    if not Path('/etc/systemd/system/ps3-vpn.service').is_file():
        raise ValueError('This helper requires the existing ps3-vpn.service gateway')
    if DROPIN.exists() and MARKER not in DROPIN.read_text():
        raise ValueError('Refusing to replace an unrelated systemd drop-in')
    if CONFIG.exists():
        previous = validate(json.loads(CONFIG.read_text()))
        if previous != c and DROPIN.exists():
            raise ValueError('Existing project configuration differs; remove it before changing VPS')
    CODE.parent.mkdir(parents=True, exist_ok=True)
    if CODE.exists() and 'VPS exception' not in CODE.read_text():
        raise ValueError('Refusing to replace unrelated helper code')
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    DROPIN.parent.mkdir(parents=True, exist_ok=True)
    old_files = {path: (path.read_bytes(), path.stat().st_mode & 0o777) if path.exists() else None
                 for path in (CODE, CONFIG, DROPIN)}
    if Path(__file__).resolve() != CODE.resolve():
        shutil.copyfile(Path(__file__), CODE)
    CODE.chmod(0o644)
    CONFIG.write_text(json.dumps(c,indent=2)+'\n');CONFIG.chmod(0o600)
    DROPIN.write_text(f'# {MARKER}\n[Service]\nExecStartPost=/usr/bin/python3 {CODE} --mode apply\nExecStopPost=/usr/bin/python3 {CODE} --mode stop\n')
    DROPIN.chmod(0o644)
    try:
        run('systemctl','daemon-reload')
        apply(c)
    except BaseException:
        for path, old in old_files.items():
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old[0]);path.chmod(old[1])
        run('systemctl','daemon-reload',check=False)
        raise
    print('Installed hooks for future ps3-vpn restarts; current VPN was not restarted.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--server')
    p.add_argument('--client',default='192.168.0.178')
    p.add_argument('--interface',default='enp3s0')
    p.add_argument('--priority',type=int,default=10177)
    p.add_argument('--dns-port',type=int,default=1053)
    p.add_argument('--mode',choices=['plan','install','apply','stop','remove'],default='install')
    a=p.parse_args()
    try:
        if a.server:
            c=validate({'server':a.server,'client':a.client,'interface':a.interface,'priority':a.priority,'dns_port':a.dns_port})
        else:
            c=validate(json.loads(CONFIG.read_text()))
        if a.mode=='plan':
            print(json.dumps({'settings':c,'rule_scope':'Only PS3 -> supplied VPS','persistence':str(DROPIN),
                              'other_destinations':'Existing VPN unchanged','root_required_for_install':True},indent=2))
            return
        if os.geteuid()!=0:raise PermissionError('Run with sudo: changing kernel routes requires root')
        if a.mode=='install':install(c)
        elif a.mode=='apply':apply(c)
        elif a.mode=='stop':stop(c)
        else:
            if DROPIN.exists() and MARKER not in DROPIN.read_text():raise ValueError('Unrelated drop-in found')
            stop(c);DROPIN.unlink(missing_ok=True);run('systemctl','daemon-reload')
            print('Restart hooks removed; configuration/code retained for review.')
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        detail=exc.stderr.strip() if isinstance(exc,subprocess.CalledProcessError) else str(exc)
        p.exit(1,f'VPS route setup failed: {detail}\n')


if __name__=='__main__':main()
