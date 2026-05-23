import hashlib
import json
import os
from datetime import datetime


BLOCKCHAIN_FILE = 'blockchain_data.json'


class Block:
    def __init__(self, index, voter_id, candidate, timestamp, previous_hash):
        self.index         = index
        self.voter_id      = voter_id
        self.candidate     = candidate
        self.timestamp     = timestamp
        self.previous_hash = previous_hash
        self.hash          = self.calculate_hash()

    def calculate_hash(self):
        block_data = json.dumps({
            "index":         self.index,
            "voter_id":      self.voter_id,
            "candidate":     self.candidate,
            "timestamp":     self.timestamp,
            "previous_hash": self.previous_hash
        }, sort_keys=True)
        return hashlib.sha256(block_data.encode()).hexdigest()

    def to_dict(self):
        return {
            "index":         self.index,
            "voter_id":      self.voter_id,
            "candidate":     self.candidate,
            "timestamp":     self.timestamp,
            "previous_hash": self.previous_hash,
            "hash":          self.hash
        }

    @classmethod
    def from_dict(cls, data):
        block = cls(
            index         = data['index'],
            voter_id      = data['voter_id'],
            candidate     = data['candidate'],
            timestamp     = data['timestamp'],
            previous_hash = data['previous_hash']
        )
        # Restore the original hash (don't recalculate — trust persisted value,
        # but is_chain_valid() will verify it independently)
        block.hash = data['hash']
        return block


class Blockchain:
    def __init__(self):
        self.chain = []
        self._load_or_create()

    # ── Persistence ────────────────────────────────────────────────────────

    def _load_or_create(self):
        """Load chain from disk if it exists, otherwise create genesis block."""
        if os.path.exists(BLOCKCHAIN_FILE):
            try:
                with open(BLOCKCHAIN_FILE, 'r') as f:
                    data = json.load(f)
                self.chain = [Block.from_dict(b) for b in data]
                if not self.chain:
                    self._create_genesis_block()
                    self._save()
                return
            except Exception:
                # Corrupted file — start fresh
                self.chain = []

        self._create_genesis_block()
        self._save()

    def _save(self):
        """Persist the entire chain to disk atomically."""
        tmp = BLOCKCHAIN_FILE + '.tmp'
        try:
            with open(tmp, 'w') as f:
                json.dump([b.to_dict() for b in self.chain], f, indent=2)
            os.replace(tmp, BLOCKCHAIN_FILE)   # atomic on POSIX
        except Exception as e:
            print(f'[Blockchain] WARNING: could not save chain: {e}')
            if os.path.exists(tmp):
                os.remove(tmp)

    # ── Core chain operations ───────────────────────────────────────────────

    def _create_genesis_block(self):
        genesis = Block(
            index         = 0,
            voter_id      = "GENESIS",
            candidate     = "GENESIS",
            timestamp     = str(datetime.now()),
            previous_hash = "0" * 64
        )
        self.chain.append(genesis)

    def get_last_block(self):
        return self.chain[-1]

    def add_vote(self, voter_id, candidate):
        last_block = self.get_last_block()
        new_block  = Block(
            index         = len(self.chain),
            voter_id      = voter_id,
            candidate     = candidate,
            timestamp     = str(datetime.now()),
            previous_hash = last_block.hash
        )
        self.chain.append(new_block)
        self._save()                            # persist after every vote
        return new_block.hash

    def is_chain_valid(self):
        for i in range(1, len(self.chain)):
            current  = self.chain[i]
            previous = self.chain[i - 1]

            # Recalculate and compare hash
            if current.hash != current.calculate_hash():
                return False

            # Check previous hash linkage
            if current.previous_hash != previous.hash:
                return False

        return True

    def get_all_blocks(self):
        return [block.to_dict() for block in self.chain]


# Single shared blockchain instance used across the app
voting_blockchain = Blockchain()