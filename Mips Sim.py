#!/usr/bin/env python3
"""
MIPS 5-Stage Pipeline Simulator
CS3339, Spring 2026

STEP 1 : Instruction parsing + register file + memory
TODO :
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
#  PIPELINE STATE REGISTERS  (Step 2 )
# ─────────────────────────────────────────────────────────────

@dataclass
class IF_ID:
    instruction: Instruction = field(default_factory=lambda: NOP_INSTR)
    pc_plus4:    int  = 0     # word index of the instruction that follows this one
    valid:       bool = False  # False → bubble, downstream stages ignore this slot


@dataclass
class ID_EX:
    instruction: Instruction = field(default_factory=lambda: NOP_INSTR)
    pc_plus4:    int  = 0

    # Values read from the register file in the ID stage
    reg_rs:   int = 0   # value of rs (first source register)
    reg_rt:   int = 0   # value of rt (second source register)

    # Immediate sign-extended to 32 bits
    imm_ext:  int = 0

    # Control signals — set by decode_control(), carried forward unchanged
    reg_dst:    bool = False  # True  → write dest is rd (R-type)
                               # False → write dest is rt (I-type)
    alu_src:    bool = False  # True  → 2nd ALU input is imm_ext, not reg_rt
    mem_to_reg: bool = False  # True  → write-back comes from memory (LW)
    reg_write:  bool = False  # True  → write result to register file
    mem_read:   bool = False  # True  → read from data memory (LW)
    mem_write:  bool = False  # True  → write to data memory (SW)
    branch:     bool = False  # True  → this is BEQ
    jump:       bool = False  # True  → this is J
    alu_op:     str  = ""     # which ALU operation to run (e.g. "ADD", "LW")

    valid: bool = False

@dataclass
class EX_MEM:
    instruction:   Instruction = field(default_factory=lambda: NOP_INSTR)

    alu_result:    int  = 0    # ALU output (result or computed memory address)
    reg_rt:        int  = 0    # rt value — needed by SW to know what to store
    write_reg:     int  = 0    # register index that WB will write to

    branch_target: int  = 0    # PC to use if BEQ is taken  (pc_plus4 + imm_ext)
    zero_flag:     bool = False # True when rs == rt; gates the branch
    jump_target:   int  = 0    # word-address for J

    # Control signals still needed by MEM and WB
    mem_to_reg:  bool = False
    reg_write:   bool = False
    mem_read:    bool = False
    mem_write:   bool = False
    branch:      bool = False
    jump:        bool = False

    valid: bool = False


@dataclass
class MEM_WB:
    instruction: Instruction = field(default_factory=lambda: NOP_INSTR)

    alu_result:  int  = 0   # used when mem_to_reg is False (R-type, ADDI, etc.)
    mem_data:    int  = 0   # used when mem_to_reg is True  (LW)
    write_reg:   int  = 0   # destination register index

    # Control signals needed by WB
    mem_to_reg: bool = False  # selects between mem_data and alu_result
    reg_write:  bool = False  # whether to actually write

    valid: bool = False


# ─────────────────────────────────────────────────────────────
#  CONTROL UNIT  (Step 3 )
# ─────────────────────────────────────────────────────────────

@dataclass
class ControlSignals:
    reg_dst:    bool = False
    alu_src:    bool = False
    mem_to_reg: bool = False
    reg_write:  bool = False
    mem_read:   bool = False
    mem_write:  bool = False
    branch:     bool = False
    jump:       bool = False
    alu_op:     str  = ""    # changed from "NOP" → ""


# ── CHANGED: decode_control ───────────────────────────────────
# Your version had the function signature but no body (would crash
# with a SyntaxError). Filled in the full truth table for all opcodes.
def decode_control(instr: Instruction) -> ControlSignals:
    """
    Control unit: maps opcode -> control signals.

    Truth table:
    ┌────────┬─────────┬─────────┬───────────┬───────────┬──────────┬───────────┬────────┬──────┐
    │ Opcode │ reg_dst │ alu_src │ mem_to_reg│ reg_write │ mem_read │ mem_write │ branch │ jump │
    ├────────┼─────────┼─────────┼───────────┼───────────┼──────────┼───────────┼────────┼──────┤
    │ R-type │    1    │    0    │     0     │     1     │    0     │     0     │   0    │  0   │
    │ ADDI   │    0    │    1    │     0     │     1     │    0     │     0     │   0    │  0   │
    │ LW     │    0    │    1    │     1     │     1     │    1     │     0     │   0    │  0   │
    │ SW     │    —    │    1    │     —     │     0     │    0     │     1     │   0    │  0   │
    │ BEQ    │    —    │    0    │     —     │     0     │    0     │     0     │   1    │  0   │
    │ J      │    —    │    —    │     —     │     0     │    0     │     0     │   0    │  1   │
    │ NOP    │    0    │    0    │     0     │     0     │    0     │     0     │   0    │  0   │
    └────────┴─────────┴─────────┴───────────┴───────────┴──────────┴───────────┴────────┴──────┘
    """
    op = instr.opcode.upper()
    c  = ControlSignals()  # all signals default False / ""

    if op == 'NOP':
        pass  # nothing to do

    elif op in R_TYPE:  # ADD, SUB, MUL, AND, OR, SLL, SRL
        c.reg_dst   = True
        c.reg_write = True
        c.alu_op    = op

    elif op == 'ADDI':
        c.alu_src   = True
        c.reg_write = True
        c.alu_op    = 'ADDI'

    elif op == 'LW':
        c.alu_src    = True
        c.mem_to_reg = True
        c.reg_write  = True
        c.mem_read   = True
        c.alu_op     = 'LW'

    elif op == 'SW':
        c.alu_src   = True
        c.mem_write = True
        c.alu_op    = 'SW'

    elif op == 'BEQ':
        c.branch    = True
        c.alu_op    = 'BEQ'

    elif op == 'J':
        c.jump      = True

    else:
        raise ValueError(f"decode_control: unknown opcode '{op}'")

    return c


# ─────────────────────────────────────────────────────────────
#  ALU  (TODO: Step 4)
# ─────────────────────────────────────────────────────────────

# TODO: Implement alu_execute(op, a, b) -> int
# Should handle: ADD, ADDI, SUB, MUL, AND, OR, SLL, SRL, LW (addr), SW (addr), BEQ (subtract)
# Remember: sign-extend inputs, mask result to 32 bits

def sign_extend_16(val: int) -> int:
    """
    Sign-extend a 16-bit immediate to a Python int.
 
    MIPS immediates are stored as 16-bit two's complement.
    When fed to the ALU, negative offsets (e.g. -4 stored as 0xFFFC)
    must be treated as negative Python integers, not large positives.
 
    Example:
        0x0005  ->  5      (positive, unchanged)
        0xFFF8  -> -8      (bit 15 set, subtract 2^16)
    """
    val = val & 0xFFFF       # keep only the low 16 bits
    if val & 0x8000:         # bit 15 is the sign bit
        val -= 0x10000       # wrap into negative range
    return val
 
 
def to_signed32(val: int) -> int:
    """
    Interpret a value as a 32-bit signed integer.
 
    Register values are masked to 32 bits, but Python ints are
    unbounded. This converts 0x80000000–0xFFFFFFFF into their negative
    equivalents so arithmetic like SUB and BEQ works across the
    positive/negative boundary correctly.
 
    Example:
        0x00000007  ->   7
        0xFFFFFFF9  ->  -7
    """
    val = val & 0xFFFFFFFF
    if val & 0x80000000:
        val -= 0x100000000
    return val
 
 
def alu_execute(op: str, a: int, b: int) -> int:
    """
    Execute one ALU operation and return a 32-bit unsigned result.
 
    Parameters
    ----------
    op : str
        The operation — matches the alu_op set by decode_control.
        e.g. "ADD", "SUB", "LW", "BEQ".
    a : int
        First operand. For most instructions this is reg_rs.
        For SLL/SRL this is reg_rt (the value being shifted).
    b : int
        Second operand. Either reg_rt or imm_ext, chosen by the
        alu_src signal in stage_EX before calling this function.
        For SLL/SRL this is the shift amount (shamt from the imm field).
 
    Returns
    -------
    int
        Result masked to 32 bits (0x00000000–0xFFFFFFFF).
        For BEQ the caller checks result == 0 for the zero flag;
        this function just does the subtraction.
 
    How each opcode maps to the pipeline
    ──────────────────────────────────────
    ADD / SUB / MUL / AND / OR  — R-type arithmetic and logic
    ADDI                         — I-type add with sign-extended immediate
    SLL / SRL                    — shifts; a = reg_rt, b = shamt
    LW  / SW                     — address calc: base + offset
    BEQ                          — subtraction; zero flag set by caller
    """
    # Convert both operands to signed 32-bit before arithmetic.
    # Bitwise and shift ops work on unsigned too, but this keeps
    # everything consistent and handles negative register values.
    a = to_signed32(a)
    b = to_signed32(b)
 
    if op in ('ADD', 'ADDI'):
        result = a + b
 
    elif op == 'SUB':
        result = a - b
 
    elif op == 'MUL':
        result = a * b
 
    elif op == 'AND':
        result = a & b
 
    elif op == 'OR':
        result = a | b
 
    elif op == 'SLL':
        # a = value to shift (reg_rt), b = shift amount (shamt)
        # Mask shift amount to 5 bits (0–31) per MIPS spec.
        result = a << (b & 0x1F)
 
    elif op == 'SRL':
        # Logical right shift — use unsigned a so no sign bits
        # are dragged in from the left.
        result = (a & 0xFFFFFFFF) >> (b & 0x1F)
 
    elif op in ('LW', 'SW'):
        # Both load and store compute the same address: base + offset
        result = a + b
 
    elif op == 'BEQ':
        # rs - rt; caller checks result == 0 to decide branch
        result = a - b
 
    else:
        # NOP, J, or unknown — ALU unused, return 0
        result = 0
 
    # Mask to 32 bits — silently wraps overflow, matching real hardware.
    # e.g. 0xFFFFFFFF + 1 -> 0x00000000
    return result & 0xFFFFFFFF

# ─────────────────────────────────────────────────────────────
#  PIPELINE SIMULATOR  (Steps 5 + 6 + 7 )
# ─────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────
    #  STEP 5: PIPELINE STAGE FUNCTIONS  
    # ─────────────────────────────────────────────────────────────

class MIPSSimulator:
    # ── CHANGED: added debug flag and instructions_committed counter
    def __init__(self, program, debug=False):
        self.program = program
        self.pc = 0                       # WORD index
        self.cycle = 0
        self.debug = debug                # -d flag enables per-cycle output
        self.instructions_committed = 0   # incremented each time WB writes
        self.registers = RegisterFile()
        self.memory = Memory()

        self.if_id  = IF_ID(valid=False)
        self.id_ex  = ID_EX(valid=False)
        self.ex_mem = EX_MEM(valid=False)
        self.mem_wb = MEM_WB(valid=False)

    # ───────── IF ─────────
    def stage_IF(self):
        if self.pc < len(self.program):
            instr = self.program[self.pc]
            return IF_ID(
                instruction=instr,
                pc_plus4=self.pc + 1,
                valid=True
            )
        return IF_ID(valid=False)

    # ───────── ID ─────────
    def stage_ID(self, if_id_latch):
        if not if_id_latch.valid:
            return ID_EX(valid=False)

        instr = if_id_latch.instruction

        reg_rs_val = self.registers.read(instr.rs)
        reg_rt_val = self.registers.read(instr.rt)
        imm_ext = sign_extend_16(instr.imm)
        signals = decode_control(instr)

        return ID_EX(
            instruction=instr,
            pc_plus4=if_id_latch.pc_plus4,

            reg_rs=reg_rs_val,
            reg_rt=reg_rt_val,
            imm_ext=imm_ext,

            reg_dst=signals.reg_dst,
            alu_src=signals.alu_src,
            mem_to_reg=signals.mem_to_reg,
            reg_write=signals.reg_write,
            mem_read=signals.mem_read,
            mem_write=signals.mem_write,
            branch=signals.branch,
            jump=signals.jump,
            alu_op=signals.alu_op,

            valid=True
        )

    # ───────── EX ─────────
    def stage_EX(self, id_ex_latch):
        if not id_ex_latch.valid:
            return EX_MEM(valid=False)

        instr = id_ex_latch.instruction
        op    = instr.opcode.upper()

        # ── CHANGED: SLL/SRL use (reg_rt, shamt) not (reg_rs, reg_rt/imm)
        # All other instructions use reg_rs as input-a, and either
        # imm_ext (alu_src=True) or reg_rt (alu_src=False) as input-b.
        if op in ('SLL', 'SRL'):
            val_a = id_ex_latch.reg_rt   # value to shift
            val_b = instr.imm            # shamt (NOT sign-extended)
        elif id_ex_latch.alu_src:
            val_a = id_ex_latch.reg_rs
            val_b = id_ex_latch.imm_ext
        else:
            val_a = id_ex_latch.reg_rs
            val_b = id_ex_latch.reg_rt

        alu_result = alu_execute(id_ex_latch.alu_op, val_a, val_b)

        write_reg = instr.rd if id_ex_latch.reg_dst else instr.rt

        branch_target = id_ex_latch.pc_plus4 + id_ex_latch.imm_ext

        # ── CHANGED: zero_flag compares the register values directly,
        # not the ALU result. BEQ asks 'are rs and rt equal?' — the ALU
        # does rs-rt and the hardware checks if the result is zero, but
        # here we compare directly so other instructions (like ADD whose
        # result happens to be 0) don't accidentally trigger a branch.
        zero_flag = (to_signed32(id_ex_latch.reg_rs) == to_signed32(id_ex_latch.reg_rt))

        jump_target = instr.target

        return EX_MEM(
            instruction=instr,
            alu_result=alu_result,
            reg_rt=id_ex_latch.reg_rt,
            write_reg=write_reg,

            branch_target=branch_target,
            zero_flag=zero_flag,
            jump_target=jump_target,

            mem_to_reg=id_ex_latch.mem_to_reg,
            reg_write=id_ex_latch.reg_write,
            mem_read=id_ex_latch.mem_read,
            mem_write=id_ex_latch.mem_write,
            branch=id_ex_latch.branch,
            jump=id_ex_latch.jump,

            valid=True
        )

    # ───────── MEM ─────────
    def stage_MEM(self, ex_mem_latch):
        if not ex_mem_latch.valid:
            return MEM_WB(valid=False)

        alu_result = ex_mem_latch.alu_result
        mem_data = 0

        if ex_mem_latch.mem_read:
            mem_data = self.memory.load_word(alu_result)

        if ex_mem_latch.mem_write:
            self.memory.store_word(alu_result, ex_mem_latch.reg_rt)

        return MEM_WB(
            instruction=ex_mem_latch.instruction,
            alu_result=alu_result,
            mem_data=mem_data,
            write_reg=ex_mem_latch.write_reg,
            mem_to_reg=ex_mem_latch.mem_to_reg,
            reg_write=ex_mem_latch.reg_write,
            valid=True
        )

    # ───────── WB ─────────
    def stage_WB(self, mem_wb_latch):
        if not mem_wb_latch.valid:
            return

        value_to_write = (
            mem_wb_latch.mem_data
            if mem_wb_latch.mem_to_reg
            else mem_wb_latch.alu_result
        )

        if mem_wb_latch.reg_write:
            self.registers.write(mem_wb_latch.write_reg, value_to_write)
            self.instructions_committed += 1

    # ───────── PC UPDATE ─────────
    def update_pc(self, ex_mem_latch):
        if not ex_mem_latch.valid:
            self.pc += 1
            return

        if ex_mem_latch.jump:
            self.pc = ex_mem_latch.jump_target

        elif ex_mem_latch.branch and ex_mem_latch.zero_flag:
            self.pc = ex_mem_latch.branch_target

        else:
            self.pc += 1

    # ─────────────────────────────────────────────────────────
    #  STEP 6: Main simulation loop 
    # ─────────────────────────────────────────────────────────
    #
    # Cycle order each tick:
    #   1. WB        — commit result to register file
    #   2. MEM       — compute next MEM/WB from EX/MEM
    #   3. EX        — compute next EX/MEM from ID/EX
    #   4. ID        — compute next ID/EX from IF/ID
    #   5. update_pc — override PC for branch/jump
    #   6. IF        — fetch using updated PC
    #   7. Latch     — all four new latches take effect
    #
    # Stops when all latches are empty AND PC is past the program.

    def run(self):
        while True:
            self.cycle += 1

            # Stages execute in order — WB first so results are
            # committed before this cycle's IF fetches
            self.stage_WB(self.mem_wb)

            new_mem_wb = self.stage_MEM(self.ex_mem)
            new_ex_mem = self.stage_EX(self.id_ex)
            new_id_ex  = self.stage_ID(self.if_id)

            # ── CHANGED: IF fetches BEFORE update_pc runs.
            # The team's update_pc always increments self.pc by 1
            # (normal case) or overrides it (branch/jump). Since
            # stage_IF uses self.pc to fetch and then sets
            # pc_plus4 = self.pc + 1, it must see the pre-update
            # value. update_pc then advances or overrides for the
            # NEXT cycle's fetch.
            new_if_id  = self.stage_IF()
            self.update_pc(new_ex_mem)

            # Latch all simultaneously
            self.if_id  = new_if_id
            self.id_ex  = new_id_ex
            self.ex_mem = new_ex_mem
            self.mem_wb = new_mem_wb

            if self.debug:
                self.print_debug_state()

            # Stop once all stages are drained and PC is past end
            pipeline_empty = not any([
                self.if_id.valid,
                self.id_ex.valid,
                self.ex_mem.valid,
                self.mem_wb.valid,
            ])
            if pipeline_empty and self.pc >= len(self.program):
                break

            # Safety valve — catches runaway programs
            if self.cycle > len(self.program) * 20 + 50:
                print('[WARNING] Cycle limit reached.')
                break

        self.print_final_state()

    # ─────────────────────────────────────────────────────────
    #  STEP 7: Debug and final output 
    # ─────────────────────────────────────────────────────────

    def print_final_state(self):
        print("Final Register File:")
        print(self.registers.dump())
        print()
        print("Final Memory:")
        print(self.memory.dump())

    def print_debug_state(self):
        print("=" * 60)
        print(f"Cycle {self.cycle} | Next PC = {self.pc}")
        print("-" * 60)

        def instr_str(latch):
            return str(latch.instruction) if latch.valid else "[BUBBLE]"

        # Pipeline stages
        print(f"IF/ID : {instr_str(self.if_id)}")
        print(f"ID/EX : {instr_str(self.id_ex)}")
        print(f"EX/MEM: {instr_str(self.ex_mem)}")
        print(f"MEM/WB: {instr_str(self.mem_wb)}")

        print("-" * 60)

        # Control signals
        if self.id_ex.valid:
            print("ID/EX Control Signals:")
            print(f"  reg_dst={self.id_ex.reg_dst} "
                  f"alu_src={self.id_ex.alu_src} "
                  f"mem_to_reg={self.id_ex.mem_to_reg}")
            print(f"  reg_write={self.id_ex.reg_write} "
                  f"mem_read={self.id_ex.mem_read} "
                  f"mem_write={self.id_ex.mem_write}")
            print(f"  branch={self.id_ex.branch} "
                  f"jump={self.id_ex.jump} "
                  f"alu_op={self.id_ex.alu_op}")
        else:
            print("ID/EX Control Signals: [BUBBLE]")

        print("-" * 60)

        if self.ex_mem.valid:
            print("EX/MEM State:")
            print(f"  ALU Result   = {self.ex_mem.alu_result}")
            print(f"  Zero Flag    = {self.ex_mem.zero_flag}")
            print(f"  Write Reg    = {self.ex_mem.write_reg}")
            print(f"  Branch Target= {self.ex_mem.branch_target}")
        else:
            print("EX/MEM State: [BUBBLE]")

        print("-" * 60)

        print(self.registers.dump())
        print()
        print(self.memory.dump())
        print("=" * 60)
        print()


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

    # ── CHANGED: removed old step verification blocks, wired real simulator
    sim = MIPSSimulator(instructions, debug=args.debug)
    sim.run()
        
if __name__ == "__main__":
    main()