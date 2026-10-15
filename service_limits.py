"""Bounded per-peer and global token buckets for public service traffic."""
from collections import OrderedDict
import threading
import time


class RateLimit:
    def __init__(self, rate, burst, global_rate, global_burst, max_peers=8192, clock=time.monotonic):
        self.rate,self.burst,self.global_rate,self.global_burst=rate,burst,global_rate,global_burst
        self.max_peers,self.clock=max_peers,clock
        self.peers=OrderedDict()
        self.global_tokens=float(global_burst)
        self.last=clock()
        self.lock=threading.Lock()

    def allow(self, peer):
        now=self.clock()
        with self.lock:
            self.global_tokens=min(self.global_burst,self.global_tokens+max(0,now-self.last)*self.global_rate)
            self.last=now
            tokens,last=self.peers.pop(peer,(float(self.burst),now))
            tokens=min(self.burst,tokens+max(0,now-last)*self.rate)
            granted=tokens>=1 and self.global_tokens>=1
            if granted:
                tokens-=1;self.global_tokens-=1
            self.peers[peer]=(tokens,now)
            while len(self.peers)>self.max_peers:self.peers.popitem(last=False)
            return granted
