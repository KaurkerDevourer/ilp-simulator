import pytest
from inorder.simulator import ILPSimulator

def test_load(tmp_path):
    d = tmp_path
    p = d / "test_program.misc"
    
    test_code = """lw t1, 0(t0)
    add t2, t1, t1
    sw t2, 4(t0)
    addi t3, t1, #5
    subi t4, t2, #3
    muli t5, t3, #2
    divi t6, t5, #4
    li t7, #42
    """
    p.write_text(test_code)
    sim = ILPSimulator()
    sim.load(str(p))

    assert len(sim.program) == 8
    assert sim.program[0].op == 'lw'
    assert sim.program[0].rd == 't1'
    assert sim.program[1].op == 'add'
    assert sim.program[1].rs1 == 't1'
    assert sim.program[2].op == 'sw'
    assert sim.program[2].offset == 4
    assert sim.program[3].op == 'addi'
    assert sim.program[3].rs1 == 't1'
    assert sim.program[3].imm == 5
    assert sim.program[4].op == 'subi'
    assert sim.program[4].rs1 == 't2'
    assert sim.program[4].imm == 3
    assert sim.program[5].op == 'muli'
    assert sim.program[5].rs1 == 't3'
    assert sim.program[5].imm == 2
    assert sim.program[6].op == 'divi'
    assert sim.program[6].rs1 == 't5'
    assert sim.program[6].imm == 4
    assert sim.program[7].op == 'li'
    assert sim.program[7].imm == 42

def test_all_arithmetic_ops(tmp_path):
    d = tmp_path
    p = d / "test_arithmetic.misc"
    
    test_code = """li t0, #20
    li t1, #5
    add t2, t0, t1
    sub t3, t0, t1
    mul t4, t0, t1
    div t5, t0, t1
    addi t6, t0, #3
    subi t7, t0, #2
    muli s0, t1, #4
    divi s1, t0, #2
    """
    p.write_text(test_code)
    sim = ILPSimulator()
    sim.load(str(p))
    sim.run()

    assert sim.registers['t2'] == 25
    assert sim.registers['t3'] == 15
    assert sim.registers['t4'] == 100
    assert sim.registers['t5'] == 4

    assert sim.registers['t6'] == 23
    assert sim.registers['t7'] == 18
    assert sim.registers['s0'] == 20
    assert sim.registers['s1'] == 10

def test_run(tmp_path):
    d = tmp_path
    p = d / "test_program.misc"

    test_code = """lw t1, 0(t0)
    add t2, t1, t1
    sw t2, 4(t0)
    """
    p.write_text(test_code)
    sim = ILPSimulator()
    sim.load(str(p))
    sim.registers = {'t0': 100}
    sim.memory = {100: 10}
    sim.run()
    assert sim.registers['t0'] == 100
    assert sim.registers['t1'] == 10
    assert sim.registers['t2'] == 20
    assert sim.memory[100] == 10
    assert sim.memory[104] == 20
    assert sim.total_cycles == 11
    sim.print_timeline()
