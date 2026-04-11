# test.asm — CS3339 MIPS Simulator Test Program
#
# Tests every supported instruction.
# NOPs are inserted between dependent instructions (no forwarding assumed).
#
# Expected final register values:
#   $t0 = 10
#   $t1 = 3
#   $t2 = 13    (ADD:  10 + 3)
#   $t3 = 7     (SUB:  10 - 3)
#   $t4 = 30    (MUL:  10 * 3)
#   $t5 = 2     (AND:  10 & 3  = 0b1010 & 0b0011 = 0b0010)
#   $t6 = 11    (OR:   10 | 3  = 0b1010 | 0b0011 = 0b1011)
#   $t7 = 40    (SLL:  10 << 2)
#   $s0 = 5     (SRL:  10 >> 1)
#   $s1 = 100   (base memory address)
#   $s2 = 13    (LW from mem[100])
#   $s3 = 7     (LW from mem[104])
#   $s4 = 0     (skipped by BEQ)
#   $s5 = 0     (skipped by J)
#
# Expected memory:
#   mem[100] = 13
#   mem[104] = 7

# ── Setup ───────────────────────────────────────────────────
        ADDI  $t0, $zero, 10       # $t0 = 10
        NOP
        NOP
        NOP
        ADDI  $t1, $zero, 3        # $t1 = 3
        NOP
        NOP
        NOP

# ── Arithmetic ──────────────────────────────────────────────
        ADD   $t2, $t0, $t1        # $t2 = 13
        NOP
        NOP
        NOP
        SUB   $t3, $t0, $t1        # $t3 = 7
        NOP
        NOP
        NOP
        MUL   $t4, $t0, $t1        # $t4 = 30
        NOP
        NOP
        NOP

# ── Logic ───────────────────────────────────────────────────
        AND   $t5, $t0, $t1        # $t5 = 2
        NOP
        NOP
        NOP
        OR    $t6, $t0, $t1        # $t6 = 11
        NOP
        NOP
        NOP

# ── Shifts ──────────────────────────────────────────────────
        SLL   $t7, $t0, 2          # $t7 = 40  (10 << 2)
        NOP
        NOP
        NOP
        SRL   $s0, $t0, 1          # $s0 = 5   (10 >> 1)
        NOP
        NOP
        NOP

# ── Memory ──────────────────────────────────────────────────
        ADDI  $s1, $zero, 100      # $s1 = 100  (base address)
        NOP
        NOP
        NOP
        SW    $t2, 0($s1)          # mem[100] = 13
        NOP
        NOP
        NOP
        SW    $t3, 4($s1)          # mem[104] = 7
        NOP
        NOP
        NOP
        LW    $s2, 0($s1)          # $s2 = 13
        NOP
        NOP
        NOP
        LW    $s3, 4($s1)          # $s3 = 7
        NOP
        NOP
        NOP

# ── Branch: BEQ taken, $s4 assignment is skipped ────────────
        BEQ   $t1, $t1, skip       # always taken ($t1 == $t1)
        NOP
        NOP
        NOP
        ADDI  $s4, $zero, 99       # SKIPPED — $s4 stays 0
skip:
        NOP
        NOP
        NOP

# ── Jump: J taken, $s5 assignment is skipped ────────────────
        J     done
        NOP
        NOP
        NOP
        ADDI  $s5, $zero, 88       # SKIPPED — $s5 stays 0
done:
        NOP
