MIPS 5-Stage Pipeline Simulator
CS3339 — Computer Architecture, Spring 2026

What's Already Done (Step 1)
Running python3 mips_sim.py test.asm already works and produces:

A binary program listing — hex encoding, 32-bit binary, and field breakdown for every instruction
A placeholder register/memory dump (zeros until the simulator is wired up)

The following are fully implemented and ready to use:

RegisterFile — 32 registers, $zero hardwired to 0, read() / write() / dump()
Memory — sparse word-addressed dictionary, load_word() / store_word() / dump()
Instruction dataclass — holds opcode, fields, and binary_repr()
assemble() — two-pass assembler: resolves labels, parses all 13 opcodes


Requirements

Python 3.8+ (no third-party libraries needed)

bashpython3 --version   # must be 3.8 or higher

Running
bash# Normal mode — binary listing + final register/memory state
python3 mips_sim.py test.asm

# Debug mode — also prints pipeline state after every clock cycle
python3 mips_sim.py test.asm -d

Build Plan (Step by Step)
Step 1 — Already done ✅
Instruction parsing, register file, memory, binary listing.

Step 2 — Pipeline State Registers
Add four dataclasses to mips_sim.py:
IF_ID   — holds: instruction, pc_plus4, valid
ID_EX   — holds: instruction, pc_plus4, reg_rs, reg_rt, imm_ext, control signals, valid
EX_MEM  — holds: instruction, alu_result, reg_rt, write_reg, branch_target, zero_flag, control signals, valid
MEM_WB  — holds: instruction, alu_result, mem_data, write_reg, mem_to_reg, reg_write, valid
Each one represents the latch between two pipeline stages.
The valid flag is False for bubbles (empty pipeline slots).

Step 3 — Control Unit
Add a ControlSignals dataclass and decode_control(instr) function.
Signals to generate:
SignalMeaningreg_dstWrite destination is rd (R-type) vs rt (I-type)alu_srcSecond ALU input is sign-extended immediate (not reg_rt)mem_to_regWrite-back value comes from memory (LW only)reg_writeWrite result to register filemem_readRead from data memorymem_writeWrite to data memorybranchThis is a BEQ instructionjumpThis is a J instructionalu_opWhich operation the ALU should perform (pass the opcode string)

Step 4 — ALU
Add sign_extend_16(val) and alu_execute(op, a, b).
opOperationADD / ADDIa + bSUBa - bMULa * bANDa & bORa | bSLLa << (b & 0x1F)SRL(a & 0xFFFFFFFF) >> (b & 0x1F)LW / SWa + b (address calculation)BEQa - b (used to set zero flag)
Mask the result to 32 bits: result & 0xFFFFFFFF

Step 5 — Pipeline Stage Functions
Add stage_IF, stage_ID, stage_EX, stage_MEM, stage_WB methods to the MIPSSimulator class.
Each takes the current latch as input and returns the next latch as output.
stage_IF()        -> IF_ID     fetch instruction at self.pc
stage_ID(IF_ID)   -> ID_EX     read registers, sign-extend imm, decode control
stage_EX(ID_EX)   -> EX_MEM   run ALU, compute branch target
stage_MEM(EX_MEM) -> MEM_WB   read/write data memory
stage_WB(MEM_WB)              write result back to register file
Also add update_pc(ex_mem) — overrides self.pc for BEQ (if zero flag set) or J.

Step 6 — Simulation Loop
Add the run() method. Each iteration is one clock cycle:
1. WB   — write back from current MEM_WB latch
2. MEM  — compute next MEM_WB from current EX_MEM
3. EX   — compute next EX_MEM from current ID_EX
4. ID   — compute next ID_EX from current IF_ID
5. update_pc — override PC if branch/jump
6. IF   — fetch next instruction using updated PC
7. Latch all new stage registers simultaneously
Terminate when all four latches are empty (valid == False) and self.pc is past the end of the instruction list.

Step 7 — Debug Mode
Add print_debug_state() — called after each cycle when -d is passed.
Should display:

Cycle number and next-fetch PC
Which instruction is in each stage (or [BUBBLE])
Control signals in ID/EX
ALU result and flags in EX/MEM
Full register file
Full memory state


Supported Instructions
OpcodeTypeDescriptionADDRrd = rs + rtSUBRrd = rs - rtMULRrd = rs * rtANDRrd = rs & rtORRrd = rs | rtSLLRrd = rt << shamtSRLRrd = rt >> shamtADDIIrt = rs + immLWIrt = mem[rs + offset]SWImem[rs + offset] = rtBEQIif rs == rt: PC = PC+4+offsetJJPC = targetNOP—no operation

The simulator assumes programs are hazard-free.
Insert NOP instructions between dependent instructions as needed (see test.asm).


Input Format
asm# Comments start with #
        ADDI  $t0, $zero, 10    # $t0 = 10
        NOP
        NOP
        NOP
        ADD   $t1, $t0, $t0     # $t1 = 20

loop:
        BEQ   $t0, $t1, done    # branch if equal
        NOP
        NOP
        NOP
done:
        NOP

Registers: $zero, $t0–$t9, $s0–$s7, $a0–$a3, $v0–$v1, etc.
Memory syntax: LW $rt, offset($rs) or SW $rt, offset($rs)


File Structure
mips_sim/
├── mips_sim.py    # Simulator source
├── test.asm       # Test program (all instructions, hazard-free)
└── README.md      # This file