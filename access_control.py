"""Explicit source-IP allowlist shared by DNS and HTTPS listeners."""
import ipaddress


class AllowedPeers:
    def __init__(self, addresses):
        self.networks = [ipaddress.ip_network(address, strict=False) for address in addresses if address]

    @classmethod
    def from_args(cls, args):
        return cls(['0.0.0.0/0'] if getattr(args,'public_mode',False) else
                   [getattr(args, 'client', None), args.listen, '127.0.0.1',
                    *getattr(args, 'allowed_clients', [])])

    def __contains__(self, address):
        try:
            peer = ipaddress.ip_address(address)
        except ValueError:
            return False
        return any(peer.version == network.version and peer in network for network in self.networks)
