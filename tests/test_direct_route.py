import json
import subprocess
import unittest
from unittest.mock import patch

import configure_vps_direct as direct

CONFIG={'server':'203.0.113.10','client':'192.168.0.178','interface':'enp3s0','priority':10177,'dns_port':1053}


class DirectRouteTests(unittest.TestCase):
    def test_unrelated_priority_collision_prevents_any_firewall_changes(self):
        mutations=[]
        def kernel(*args,check=True):
            if args[:4]==('ip','-j','rule','show'):
                data=[{'priority':10178,'src':CONFIG['client'],'table':10178},
                      {'priority':10177,'src':'192.0.2.55','table':'main'}]
                return subprocess.CompletedProcess(args,0,json.dumps(data),'')
            if args[:4]==('ip','-j','route','get'):
                return subprocess.CompletedProcess(args,0,json.dumps([{'dev':'enp3s0'}]),'')
            mutations.append(args)
            raise AssertionError('Kernel mutation must not occur on a conflicting priority')
        with patch.object(direct,'run',side_effect=kernel),patch('pathlib.Path.read_text',return_value='1'):
            with self.assertRaises(ValueError):direct.apply(dict(CONFIG))
        self.assertEqual(mutations,[])

    def test_failure_rolls_back_only_inserted_project_rules(self):
        installed=set();inserts=0
        def kernel(*args,check=True):
            nonlocal inserts
            if args[:4]==('ip','-j','rule','show'):
                return subprocess.CompletedProcess(args,0,json.dumps([{'priority':10178,'src':CONFIG['client'],'table':10178}]),'')
            if args[:4]==('ip','-j','route','get'):
                return subprocess.CompletedProcess(args,0,json.dumps([{'dev':'enp3s0'}]),'')
            self.assertEqual(args[0],'iptables')
            action=args[5];chain=args[6]
            spec=tuple(args[8:] if action=='-I' else args[7:])
            key=(args[4],chain,spec)
            if action=='-C':return subprocess.CompletedProcess(args,0 if key in installed else 1,'','')
            if action=='-I':
                inserts+=1
                if inserts==4:raise subprocess.CalledProcessError(1,args,stderr='controlled failure')
                installed.add(key)
            elif action=='-D':installed.remove(key)
            else:raise AssertionError(action)
            return subprocess.CompletedProcess(args,0,'','')
        with patch.object(direct,'run',side_effect=kernel),patch('pathlib.Path.read_text',return_value='1'):
            with self.assertRaises(subprocess.CalledProcessError):direct.apply(dict(CONFIG))
        self.assertEqual(installed,set())

    def test_rule_scope_is_one_console_and_one_vps(self):
        for table,chain,spec in direct.specs(dict(CONFIG)):
            self.assertIn(direct.COMMENT,spec)
            if chain=='OUTPUT':
                self.assertEqual(spec[spec.index('-d')+1],CONFIG['client']+'/32')
                self.assertEqual(spec[spec.index('--icmp-type')+1],'redirect')
            else:
                addresses={spec[spec.index('-s')+1],spec[spec.index('-d')+1]}
                self.assertEqual(addresses,{CONFIG['client']+'/32',CONFIG['server']+'/32'})


if __name__=='__main__':unittest.main()
