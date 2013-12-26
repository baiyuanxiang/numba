NEW_BLOCKERS = frozenset(['SETUP_LOOP'])


class CFBlock(object):
    def __init__(self, offset):
        self.offset = offset
        self.body = []
        self.outgoing = set()
        self.incoming = set()
        self.terminating = False

    def __repr__(self):
        args = self.body, self.outgoing, self.incoming
        return "block(body: %s, outgoing: %s, incoming: %s)" % args

    def __iter__(self):
        return iter(self.body)


class ControlFlowAnalysis(object):
    """
    Attributes
    ----------
    - bytecode

    - blocks

    - blockseq

    - doms: dict of set
        Dominators

    - backbone: set of block offsets
        The set of block that is common to all possible code path.

    """
    def __init__(self, bytecode):
        self.bytecode = bytecode
        self.blocks = {}
        self.blockseq = []
        self.doms = None
        self.backbone = None
        # Internal temp states
        self._force_new_block = True
        self._curblock = None
        self._blockstack = []

    def iterblocks(self):
        for i in self.blockseq:
            yield self.blocks[i]

    def run(self):
        for inst in self._iter_inst():
            fname = "op_%s" % inst.opname
            fn = getattr(self, fname, None)
            if fn is not None:
                fn(inst)
            else:
                assert not inst.is_jump

        # Close all blocks
        for cur, nxt in zip(self.blockseq, self.blockseq[1:]):
            blk = self.blocks[cur]
            if not blk.outgoing and not blk.terminating:
                blk.outgoing.add(nxt)

        # Fill incoming
        for b in self.blocks.itervalues():
            for out in b.outgoing:
                self.blocks[out].incoming.add(b.offset)

        # Find dominators
        liveblocks = {}
        for offset, block in self.blocks.items():
            if offset == 0 or block.incoming:
                liveblocks[offset] = block
        self.doms = find_dominators(liveblocks)
        self.backbone = self.doms[self.blockseq[-1]]

    def jump(self, target):
        self._curblock.outgoing.add(target)

    def _iter_inst(self):
        for inst in self.bytecode:
            if self._use_new_block(inst):
                self._start_new_block(inst)
            self._curblock.body.append(inst.offset)
            yield inst

    def _use_new_block(self, inst):
        if inst.offset in self.bytecode.labels:
            res = True
        elif inst.opname in NEW_BLOCKERS:
            res = True
        else:
            res = self._force_new_block

        self._force_new_block = False
        return res

    def _start_new_block(self, inst):
        self._curblock = CFBlock(inst.offset)
        self.blocks[inst.offset] = self._curblock
        self.blockseq.append(inst.offset)

    def op_SETUP_LOOP(self, inst):
        self._blockstack.append(inst.next + inst.arg)

    def op_POP_BLOCK(self, inst):
        self._blockstack.pop()

    def op_FOR_ITER(self, inst):
        self.jump(self._blockstack[-1])
        self.jump(inst.next)
        self._force_new_block = True

    def op_POP_JUMP_IF_FALSE(self, inst):
        self.jump(inst.get_jump_target())
        self.jump(inst.next)
        self._force_new_block = True

    def op_POP_JUMP_IF_TRUE(self, inst):
        self.jump(inst.get_jump_target())
        self.jump(inst.next)
        self._force_new_block = True

    def op_JUMP_ABSOLUTE(self, inst):
        self.jump(inst.get_jump_target())
        self._force_new_block = True

    def op_RETURN_VALUE(self, inst):
        self._curblock.terminating = True
        self._force_new_block = True


def find_dominators(blocks):
    doms = {}
    for b in blocks:
        doms[b] = set()

    doms[0].add(0)
    allblks = set(blocks)

    remainblks = frozenset(blk.offset for blk in blocks.values()
                           if blk.offset != 0)
    for blk in remainblks:
        doms[blk] |= allblks

    changed = True
    while changed:
        changed = False
        for blk in remainblks:
            d = doms[blk]
            ps = [doms[p] for p in blocks[blk].incoming if p in doms]
            if not ps:
                p = set()
            else:
                p = reduce(set.intersection, ps)
            new = set([blk]) | p
            if new != d:
                doms[blk] = new
                changed = True

    return doms
