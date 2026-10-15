#!/usr/bin/env python3
"""Generate private test-service TLS files; requires python3-cryptography.

Generates an experimental unknown-signature-OID chain. Not publicly trusted;
fresh material requires separate OFW client verification.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

BASE = Path(__file__).resolve().parent
ROOT_FP = 'd86d20e06db3f01be90bb7743c1e799e776e12a09023ca5d327df8b94bf35029'


def generate(directory, cloud_hosts, gds_host):
    root = x509.load_pem_x509_certificate((BASE / 'assets/thq-connect-root.pem').read_bytes())
    assert root.fingerprint(hashes.SHA256()).hex() == ROOT_FP
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    intermediate_key = rsa.generate_private_key(65537, 2048)
    unrelated_key = rsa.generate_private_key(65537, 1024)
    now = dt.datetime.now(dt.timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'DS2 original-anchor laboratory intermediate')])
    intermediate = (x509.CertificateBuilder().subject_name(subject).issuer_name(root.subject)
                    .public_key(intermediate_key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now-dt.timedelta(days=1)).not_valid_after(now+dt.timedelta(days=365))
                    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                    .add_extension(x509.KeyUsage(True,False,False,False,False,True,True,False,False), critical=True)
                    .add_extension(x509.SubjectKeyIdentifier.from_public_key(intermediate_key.public_key()), critical=False)
                    .add_extension(x509.AuthorityKeyIdentifier(root.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest, None, None), critical=False)
                    .sign(unrelated_key, hashes.SHA256()))
    known = intermediate.public_bytes(serialization.Encoding.DER)
    oid = bytes.fromhex('06092a864886f70d01010b')
    assert known.count(oid) == 2
    intermediate = x509.load_der_x509_certificate(known.replace(oid, bytes.fromhex('06092b0601040183b2037b')))
    assert intermediate.signature_algorithm_oid.dotted_string == '1.3.6.1.4.1.55555.123'
    pem = lambda cert: cert.public_bytes(serialization.Encoding.PEM)
    def write(name, data):
        path = directory/name
        with path.open('xb') as stream:
            os.chmod(path,0o600)
            stream.write(data)
    records = []
    for label, hosts in [('cloud', list(dict.fromkeys(cloud_hosts+[gds_host]))), ('gds', [gds_host])]:
        key = rsa.generate_private_key(65537, 2048)
        cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,hosts[0])]))
                .issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-dt.timedelta(days=1)).not_valid_after(now+dt.timedelta(days=365))
                .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
                .add_extension(x509.KeyUsage(True,False,True,False,False,False,False,False,False),critical=True)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in hosts]),critical=False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(intermediate_key.public_key()),critical=False)
                .sign(intermediate_key,hashes.SHA256()))
        chain = pem(cert)+pem(intermediate)+pem(root)
        write(label+'-fullchain.pem',chain)
        write(label+'.key',key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        records.append({'label':label,'hosts':hosts,'chain_sha256':hashlib.sha256(chain).hexdigest()})
    write('manifest.json',(json.dumps({'signature_oid':'1.3.6.1.4.1.55555.123','root_sha256_der':ROOT_FP,
                                     'certificates':records,'ofw_verified':False,
                                     'note':'Experimental invalid chain; fresh material requires separate OFW client verification.'},indent=2)+'\n').encode())
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--cloud-host',action='append')
    parser.add_argument('--gds-host',default='ds2.gds.thqconnect.com')
    opts=parser.parse_args()
    hosts=opts.cloud_host or ['thqc-darksiders2-ps3-na.thqconnect.com']
    if any(not re.fullmatch(r'[a-zA-Z0-9.-]{1,253}',h) or not h.endswith('.thqconnect.com') for h in hosts+[opts.gds_host]):
        parser.error('Use the exact THQ game hostnames')
    print(json.dumps(generate(opts.out.resolve(),hosts,opts.gds_host),indent=2))


if __name__=='__main__':
    main()
