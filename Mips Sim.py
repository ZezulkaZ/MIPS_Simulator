#!/usr/bin/env python3
"""
MIPS 5-Stage Pipeline Simulator
CS3339, Spring 2026

STEP 1 (starter): Instruction parsing + register file + memory
TODO (your steps):
  - Step 2: Add pipeline state registers (IF/ID, ID/EX, EX/MEM, MEM/WB)
  - Step 3: Add control unit (decode_control)
  - Step 4: Add ALU (alu_execute)
  - Step 5: Wire up the 5 pipeline stage functions
  - Step 6: Add the main simulation loop
  - Step 7: Add debug mode output
"""

import sys
import argparse
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# ─────────────────────────────────────────────────────────────
#  REGISTER FILE
# ─────────────────────────────────────────────────────────────

REG_NAMES = {
    0: "$zero", 1: "$at",  2: "$v0",  3: "$v1",
    4: "$a0",   5: "$a1",  6: "$a2",  7: "$a3",
    8: "$t0",   9: "$t1",  10: "$t2", 11: "$t3",
    12: "$t4",  13: "$t5", 14: "$t6", 15: "$t7",
    16: "$s0",  17: "$s1", 18: "$s2", 19: "$s3",
    20: "$s4",  21: "$s5", 22: "$s6", 23: "$s7",
    24: "$t8",  25: "$t9", 26: "$k0", 27: "$k1",
    28: "$gp",  29: "$sp", 30: "$fp", 31: "$ra",
}


class RegisterFile:
    def __init__(self):
        self.regs = [0] * 32  # 32 general-purpose registers

    def read(self, idx: int) -> int:
        """Read register value. $zero (reg 0) always returns 0."""
        return 0 if idx == 0 else self.regs[idx]

    def write(self, idx: int, value: int):
        """Write to register. Writes to $zero are ignored."""
        if idx != 0:
            self.regs[idx] = value & 0xFFFFFFFF  # keep 32-bit

    def dump(self) -> str:
        """Return a formatted string of all register values."""
        lines = ["Register File:"]
        for i in range(0, 32, 4):
            row = []
            for j in range(4):
                name = REG_NAMES[i + j]
                val  = self.regs[i + j]
                row.append(f"  {name:6s}({i+j:2d}): {val:10d}  (0x{val:08X})")
            lines.append("".join(row))
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  MEMORY
# ─────────────────────────────────────────────────────────────

class Memory:
    def __init__(self):
        # Sparse dictionary: address (int) -> 32-bit word (int)
        self.data: Dict[int, int] = {}

    def load_word(self, addr: int) -> int:
        if addr % 4 != 0:
            raise ValueError(f"Unaligned memory read at 0x{addr:08X}")
        return self.data.get(addr, 0)

    def store_word(self, addr: int, value: int):
        if addr % 4 != 0:
            raise ValueError(f"Unaligned memory write at 0x{addr:08X}")
        self.data[addr] = value & 0xFFFFFFFF

    def dump(self) -> str:
        """Return a formatted string of all non-zero memory words."""
        if not self.data:
            return "Memory: (empty)"
        lines = ["Memory (non-zero words):"]
        for addr in sorted(self.data):
            val = self.data[addr]
            lines.append(f"  [0x{addr:08X}] = {val:10d}  (0x{val:08X})")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  INSTRUCTION REPRESENTATION
# ─────────────────────────────────────────────────────────────

# Encoding tables — used for binary_repr and control decoding
R_TYPE = {
    'ADD': {'funct': 0x20},
    'SUB': {'funct': 0x22},
    'MUL': {'funct': 0x18},
    'AND': {'funct': 0x24},
    'OR':  {'funct': 0x25},
    'SLL': {'funct': 0x00},
    'SRL': {'funct': 0x02},
}

I_TYPE = {
    'ADDI': {'opcode': 0x08},
    'LW':   {'opcode': 0x23},
    'SW':   {'opcode': 0x2B},
    'BEQ':  {'opcode': 0x04},
}

J_TYPE = {
    'J': {'opcode': 0x02},
}


@dataclass
class Instruction:
    raw:    str   # original assembly text (e.g. "ADD $t0, $t1, $t2")
    opcode: str   # uppercase opcode string (e.g. "ADD")
    rd:     int = 0   # destination register (R-type)
    rs:     int = 0   # source register 1
    rt:     int = 0   # source register 2 / base for LW/SW
    imm:    int = 0   # immediate value / shift amount / branch offset
    target: int = 0   # jump target (word address)
    label:  str = ""  # branch/jump label (for display)
    pc:     int = 0   # word index of this instruction in the program

    def binary_repr(self) -> str:
        """Return a human-readable binary encoding of this instruction."""
        op = self.opcode.upper()

        if op == 'NOP':
            return (
                "0x00000000  [00000000000000000000000000000000]"
                "  NOP (SLL $zero,$zero,0)"
            )

        if op in R_TYPE:
            funct = R_TYPE[op]['funct']
            shamt = self.imm if op in ('SLL', 'SRL') else 0
            rs    = 0 if op in ('SLL', 'SRL') else self.rs
            word  = (0 << 26) | (rs << 21) | (self.rt << 16) | (self.rd << 11) | (shamt << 6) | funct
            return (
                f"0x{word:08X}  [{word:032b}]"
                f"  R-type: op=000000 rs={rs:05b} rt={self.rt:05b}"
                f" rd={self.rd:05b} shamt={shamt:05b} funct={funct:06b}"
            )

        if op == 'J':
            opbits = J_TYPE[op]['opcode']
            word   = (opbits << 26) | (self.target & 0x3FFFFFF)
            return (
                f"0x{word:08X}  [{word:032b}]"
                f"  J-type: op={opbits:06b} target={self.target & 0x3FFFFFF:026b}"
            )

        # I-type
        opbits = I_TYPE[op]['opcode']
        imm16  = self.imm & 0xFFFF
        word   = (opbits << 26) | (self.rs << 21) | (self.rt << 16) | imm16
        return (
            f"0x{word:08X}  [{word:032b}]"
            f"  I-type: op={opbits:06b} rs={self.rs:05b} rt={self.rt:05b}"
            f" imm={imm16:016b}"
        )

    def __str__(self):
        return self.raw


# A bubble / empty pipeline slot
NOP_INSTR = Instruction(raw="NOP", opcode="NOP")


# ─────────────────────────────────────────────────────────────
#  ASSEMBLER  (two-pass: collect labels, then parse)
# ─────────────────────────────────────────────────────────────

def reg_num(name: str) -> int:
    """Convert a register name string to its integer index (0-31)."""
    name = name.strip().lower().rstrip(',')
    if name.startswith('$'):
        name = name[1:]
    if name.lstrip('-').isdigit():
        return int(name)
    rev = {v.lstrip('$'): k for k, v in REG_NAMES.items()}
    if name in rev:
        return rev[name]
    for prefix, base in [('t', 8), ('s', 16), ('a', 4), ('v', 2), ('k', 26)]:
        if name.startswith(prefix) and name[1:].isdigit():
            n = int(name[1:])
            if prefix == 't' and n >= 8:
                return 24 + (n - 8)
            return base + n
    raise ValueError(f"Unknown register: '{name}'")


def parse_imm(s: str) -> int:
    return int(s.strip().rstrip(','), 0)


def assemble(lines: List[str]) -> List['Instruction']:
    """
    Two-pass assembler.
    Pass 1: strip comments, collect label -> word-index mapping.
    Pass 2: parse each instruction, resolve branch/jump labels.
    Returns a list of Instruction objects (one per non-empty line).
    """
    labels: Dict[str, int] = {}
    cleaned: List[tuple]   = []  # (text, word_index)

    # ── Pass 1 ──────────────────────────────
    pc = 0
    for line in lines:
        line = line.split('#')[0].strip()   # strip comments
        if not line:
            continue
        if ':' in line:
            label, _, rest = line.partition(':')
            labels[label.strip()] = pc
            line = rest.strip()
            if not line:
                continue
        cleaned.append((line, pc))
        pc += 1

    # ── Pass 2 ──────────────────────────────
    instructions: List[Instruction] = []

    for raw, pc in cleaned:
        parts = raw.replace(',', ' ').split()
        op    = parts[0].upper()

        if op == 'NOP':
            instructions.append(Instruction(raw=raw, opcode='NOP', pc=pc))
            continue

        try:
            if op in ('ADD', 'SUB', 'MUL', 'AND', 'OR'):
                rd = reg_num(parts[1])
                rs = reg_num(parts[2])
                rt = reg_num(parts[3])
                instructions.append(Instruction(raw=raw, opcode=op, rd=rd, rs=rs, rt=rt, pc=pc))

            elif op in ('SLL', 'SRL'):
                rd    = reg_num(parts[1])
                rt    = reg_num(parts[2])
                shamt = parse_imm(parts[3])
                instructions.append(Instruction(raw=raw, opcode=op, rd=rd, rt=rt, imm=shamt, pc=pc))

            elif op == 'ADDI':
                rt  = reg_num(parts[1])
                rs  = reg_num(parts[2])
                imm = parse_imm(parts[3])
                instructions.append(Instruction(raw=raw, opcode=op, rt=rt, rs=rs, imm=imm, pc=pc))

            elif op in ('LW', 'SW'):
                rt   = reg_num(parts[1])
                rest = parts[2]
                if '(' in rest:
                    off_str, base = rest.split('(')
                    rs  = reg_num(base.rstrip(')'))
                    imm = parse_imm(off_str)
                else:
                    rs  = reg_num(parts[3]) if len(parts) > 3 else 0
                    imm = parse_imm(rest)
                instructions.append(Instruction(raw=raw, opcode=op, rt=rt, rs=rs, imm=imm, pc=pc))

            elif op == 'BEQ':
                rs  = reg_num(parts[1])
                rt  = reg_num(parts[2])
                lbl = parts[3].strip()
                offset = labels[lbl] - (pc + 1) if lbl in labels else parse_imm(lbl)
                instructions.append(Instruction(raw=raw, opcode=op, rs=rs, rt=rt, imm=offset, label=lbl, pc=pc))

            elif op == 'J':
                lbl    = parts[1].strip()
                target = labels[lbl] if lbl in labels else parse_imm(lbl)
                instructions.append(Instruction(raw=raw, opcode=op, target=target, label=lbl, pc=pc))

            else:
                raise ValueError(f"Unknown opcode: '{op}'")

        except Exception as e:
            raise ValueError(f"Parse error at '{raw}': {e}")

    return instructions


# ─────────────────────────────────────────────────────────────
#  PIPELINE STATE REGISTERS  (TODO: Step 2)
# ─────────────────────────────────────────────────────────────

# TODO: Define IF_ID, ID_EX, EX_MEM, MEM_WB dataclasses here.
# Each should hold:
#   - the Instruction passing through it
#   - a `valid: bool` flag (False = bubble/NOP)
#   - any values computed in the previous stage
#   - control signals relevant to downstream stages
#
# For example, IF_ID might hold the fetched instruction and its PC,
# while ID_EX might hold the decoded instruction, register values, and control signals.
# This allows multiple instructions to be processed at the same time, each at a different stage.

@dataclass
class IF_ID:
    instr: Instruction = NOP_INSTR
    pc: int = 0
    valid: bool = False

@dataclass
class ID_EX:
    instr: Instruction = NOP_INSTR
    pc: int = 0
    rs_val: int = 0
    rt_val: int = 0
    imm: int = 0
    valid: bool = False

@dataclass
class EX_MEM:
    instr: Instruction = NOP_INSTR
    alu_result: int = 0
    rt_val: int = 0
    valid: bool = False

@dataclass
class MEM_WB:
    instr: Instruction = NOP_INSTR
    write_val: int = 0
    valid: bool = False


# ─────────────────────────────────────────────────────────────
#  CONTROL UNIT  (TODO: Step 3) 
# ─────────────────────────────────────────────────────────────

# TODO: Define a ControlSignals dataclass and decode_control(instr) function.
# decode_control should return the correct signals for each opcode:
#   reg_dst, alu_src, mem_to_reg, reg_write,
#   mem_read, mem_write, branch, jump, alu_op

# UNFINISHED

class ControlSignals:
    reg_dst: bool = False
    alu_src: bool = False
    mem_to_reg: bool = False
    reg_write: bool = False
    mem_read: bool = False
    mem_write: bool = False
    branch: bool = False
    jump: bool = False
    alu_op: str = "NOP"

def decode_control(instr: Instruction):


# ─────────────────────────────────────────────────────────────
#  ALU  (TODO: Step 4)
# ─────────────────────────────────────────────────────────────

# TODO: Implement alu_execute(op, a, b) -> int
# Should handle: ADD, ADDI, SUB, MUL, AND, OR, SLL, SRL, LW (addr), SW (addr), BEQ (subtract)
# Remember: sign-extend inputs, mask result to 32 bits


# ─────────────────────────────────────────────────────────────
#  PIPELINE SIMULATOR  (TODO: Steps 5-7)
# ─────────────────────────────────────────────────────────────

# TODO: Implement MIPSSimulator class with:
#   - __init__: initialize regfile, memory, pc, cycle counter, pipeline latches
#   - stage_IF, stage_ID, stage_EX, stage_MEM, stage_WB methods
#   - update_pc: handle branch/jump PC override
#   - run: main cycle loop
#   - print_debug_state: per-cycle output for -d flag
#   - print_final_state: final register + memory dump


# ─────────────────────────────────────────────────────────────
#  ENTRY POINT  (wire up when simulator class is ready)
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="MIPS 5-Stage Pipeline Simulator — CS3339 Spring 2026"
    )
    parser.add_argument("input", help="Input MIPS assembly file (.asm)")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Debug mode: print pipeline state every cycle")
    args = parser.parse_args()

    # Load file
    try:
        with open(args.input) as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: file '{args.input}' not found.")
        sys.exit(1)

    # Assemble
    try:
        instructions = assemble(lines)
    except ValueError as e:
        print(f"Assembly error: {e}")
        sys.exit(1)

    if not instructions:
        print("No instructions found in input file.")
        sys.exit(0)

    # Print binary listing (works now — simulator not needed for this)
    print("=" * 70)
    print("  Binary Program Listing")
    print("=" * 70)
    for i, instr in enumerate(instructions):
        print(f"  [{i:3d}]  {instr.raw:<32s}  =>  {instr.binary_repr()}")
    print()

    # TODO: uncomment once MIPSSimulator is implemented
    # sim = MIPSSimulator(instructions, debug=args.debug)
    # sim.run()

    # Temporary: just dump a blank register file and memory
    print("(Simulator not yet implemented — register/memory output placeholder)")
    print()
    rf = RegisterFile()
    mem = Memory()
    print(rf.dump())
    print()
    print(mem.dump())


if __name__ == "__main__":
    main()