"""PSN ticket verification with an operator-pinned Darksiders II public key.

Independent Python implementation of the published TLV/ECDSA format. Runtime
requests never recover or install signing keys. Tickets are not logged/stored.
"""
import base64
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import threading
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class Principal:
    profile: str
    account_id: str
    expires_ms: int


def tlv(data, start, end):
    fields = []
    while start < end:
        if end - start < 4 or len(fields) >= 64:
            raise AuthError('Malformed ticket section')
        kind, size = struct.unpack_from('!HH', data, start)
        start += 4
        if start + size > end:
            raise AuthError('Malformed ticket field')
        fields.append((kind, data[start:start + size], start))
        start += size
    return fields


def parse_ticket(data):
    if not 128 <= len(data) <= 4096 or len(data)-8 != int.from_bytes(data[4:8], 'big'):
        raise AuthError('Invalid ticket length')
    if (data[0] >> 4, data[1]) not in {(2, 1), (3, 0)}:
        raise AuthError('Unsupported ticket version')
    kind, length = struct.unpack_from('!HH', data, 8)
    end = 12 + length
    if kind != 0x3000 or end + 4 > len(data):
        raise AuthError('Missing ticket body')
    fields = tlv(data, 12, end)
    expected = [(8,20),(1,4),(7,8),(7,8),(2,8),(4,32),(8,4),(4,4),(8,24)]
    if len(fields) < len(expected) or any((fields[i][0],len(fields[i][1])) != shape for i,shape in enumerate(expected)):
        raise AuthError('Unsupported ticket body')
    kind, length = struct.unpack_from('!HH', data, end)
    if kind != 0x3002 or end + 4 + length != len(data):
        raise AuthError('Missing ticket signature section')
    footer = tlv(data, end + 4, len(data))
    if len(footer) != 2 or footer[0][0] != 8 or len(footer[0][1]) != 4 or footer[1][0] != 8:
        raise AuthError('Unsupported signature section')
    signature = footer[1][1]
    if not 48 <= len(signature) <= 58 or signature[0] != 0x30 or signature[1] >= 0x80:
        raise AuthError('Invalid signature encoding')
    der_length = signature[1] + 2
    # The ticket uses a fixed-size signature field. DER INTEGER lengths vary;
    # shorter r/s values can leave more than two zero padding bytes. Only the
    # strict DER sequence is verified; the signed field header stays unchanged.
    if der_length > len(signature) or any(signature[der_length:]):
        raise AuthError('Invalid signature padding')
    signature = signature[:der_length]
    try:
        utils.decode_dss_signature(signature)
        name = fields[5][1].rstrip(b'\0').decode('ascii')
        service = fields[8][1].rstrip(b'\0').decode('ascii')
    except (ValueError, UnicodeError) as exc:
        raise AuthError('Invalid signature or identity encoding') from exc
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', name):
        raise AuthError('Invalid PSN profile')
    if int.from_bytes(fields[1][1], 'big') != 256:
        raise AuthError('Unsupported ticket issuer')
    account = int.from_bytes(fields[4][1], 'big')
    if not account:
        raise AuthError('Missing account identity')
    return {'principal': Principal('/psn/'+name.lower(), str(account), int.from_bytes(fields[3][1],'big')),
            'issued_ms':int.from_bytes(fields[2][1],'big'), 'identifier':footer[0][1].hex(),
            'service':service, 'message':data[:footer[1][2]], 'signature':signature}


class TicketVerifier:
    def __init__(self, key_path=None, *, key_config=None, clock=time.time):
        c = key_config if key_config is not None else json.loads(Path(key_path).read_text())
        if c['curve'] != 'secp192r1' or c['hash'] != 'SHA-1':
            raise ValueError('Unsupported pinned ticket key')
        self.key = ec.EllipticCurvePublicNumbers(int(c['x'],16),int(c['y'],16),ec.SECP192R1()).public_key()
        self.identifier = c['identifier'].lower()
        self.services = frozenset(c['service_ids'])
        if not self.services or not re.fullmatch('[0-9a-f]{8}',self.identifier):
            raise ValueError('Missing pinned game services/key identifier')
        self.clock = clock
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def verify_bytes(self, data, *, check_time=True):
        parts = parse_ticket(data)
        if parts['identifier'] != self.identifier or parts['service'] not in self.services:
            raise AuthError('Ticket belongs to another signing key or game service')
        try:
            self.key.verify(parts['signature'], parts['message'], ec.ECDSA(hashes.SHA1()))
        except InvalidSignature as exc:
            raise AuthError('Invalid PSN ticket signature') from exc
        principal = parts['principal']
        now_ms = int(self.clock()*1000)
        if principal.expires_ms <= parts['issued_ms']:
            raise AuthError('Invalid ticket lifetime')
        if check_time and (principal.expires_ms <= now_ms or parts['issued_ms'] > now_ms+300000):
            raise AuthError('Expired or future PSN ticket')
        return principal

    def authenticate(self, method, path, body):
        fields = parse_qs(urlsplit(path).query,keep_blank_values=True,max_num_fields=128)
        if method == 'POST':
            try:
                posted = parse_qs(body.decode('utf-8'),keep_blank_values=True,max_num_fields=128)
            except UnicodeError as exc:
                raise AuthError('Invalid request body') from exc
            for key,values in posted.items():fields.setdefault(key,[]).extend(values)
        auth = fields.get('auth',[])
        if len(auth) != 1 or not 1 <= len(auth[0]) <= 5500:
            raise AuthError('Missing unique PSN ticket')
        try:
            data = base64.b64decode(auth[0],validate=True)
        except ValueError as exc:
            raise AuthError('Invalid ticket base64') from exc
        digest = hashlib.sha256(data).digest()
        with self.lock:
            cached = self.cache.get(digest)
            if cached and cached.expires_ms > int(self.clock()*1000):
                self.cache.move_to_end(digest)
                return cached
        principal = self.verify_bytes(data)
        with self.lock:
            self.cache[digest] = principal
            self.cache.move_to_end(digest)
            while len(self.cache)>2048:self.cache.popitem(last=False)
        return principal
