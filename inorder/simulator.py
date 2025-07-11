import re
from dataclasses import dataclass
from typing import List, Dict, Optional

CPU_CONFIG = {
    'units': {
        'ALU': 2,
        'MUL_DIV': 1,
        'LOAD_STORE': 1,
    },
    'latency': {
        'add': 1,
        'addi': 1,
        'sub': 1,
        'subi': 1,
        'mul': 3,
        'muli': 3,
        'div': 10,
        'divi': 10,
        'lw': 5,
        'li': 5,
        'sw': 5
    },
    'op_to_unit': {
        'add': 'ALU',
        'addi': 'ALU',
        'sub': 'ALU',
        'subi': 'ALU',
        'mul': 'MUL_DIV',
        'muli': 'MUL_DIV',
        'div': 'MUL_DIV',
        'divi': 'MUL_DIV',
        'lw': 'LOAD_STORE',
        'li': 'ALU',
        'sw': 'LOAD_STORE'
    }
}

@dataclass
class Instruction:
    op: str
    rd: Optional[str] = None
    rs1: Optional[str] = None
    rs2: Optional[str] = None
    imm: Optional[int] = None
    offset: int = 0
    status: str = "WAITING"
    start_cycle: int = -1
    complete_cycle: int = -1
    result_value: Optional[int] = None
    raw_text: str = ""

class ILPSimulator:
    def __init__(self, config = CPU_CONFIG):
        self.config = config

        self.reset()
    
    def reset(self):
        self.total_cycles: int = 0

        self.program: List[Instruction] = []
        
        self.registers: Dict[str, int] = {}
        self.memory: Dict[int, int] = {}
        
        self.waiting_instructions: List[Instruction] = []
        self.executing_instructions: List[Instruction] = []
        
        self.free_units: Dict[str, int] = dict(self.config['units'])
        self.register_writeback_cycle: Dict[str, int] = {}

    def load(self, file):
        r_type_regex = re.compile(r"^\s*(\w+)\s+(\w+),\s*(\w+),\s*(\w+)\s*$")
        mem_type_regex = re.compile(r"^\s*(\w+)\s+(\w+),\s*(-?\d+)\((\w+)\)\s*$")
        imm_type_regex = re.compile(r"^\s*(\w+)\s+(\w+),\s*(\w+),\s*#(-?\d+)\s*$")
        loadi_regex = re.compile(r"^\s*(\w+)\s+(\w+),\s*#(-?\d+)\s*$")

        with open(file) as f:
            for i, line in enumerate(f):
                line = line.strip()
                r_match = r_type_regex.match(line)
                mem_match = mem_type_regex.match(line)
                imm_match = imm_type_regex.match(line)
                loadi_match = loadi_regex.match(line)

                if r_match:
                    op, rd, rs1, rs2 = r_match.groups()
                    if op not in self.config['op_to_unit']:
                        raise ValueError(f"Строка {i}: Недоступная операция '{op}' в {line}")

                    self.program.append(Instruction(op=op, rd=rd, rs1=rs1, rs2=rs2, raw_text=line))

                elif mem_match:
                    op, reg1, offset_str, reg2 = mem_match.groups()
                    offset = int(offset_str)

                    if op not in self.config['op_to_unit']:
                        raise ValueError(f"Строка {i}: Недоступная операция '{op}' в {line}")

                    if op == "sw":
                        reg1, reg2 = reg2, reg1
                    self.program.append(Instruction(op=op, rd=reg1, rs1=reg2, offset=offset, raw_text=line))
                elif imm_match:
                    op, rd, rs1, imm_str = imm_match.groups()
                    imm = int(imm_str)
                    if op not in self.config['op_to_unit']:
                        raise ValueError(f"Строка {i}: Недоступная операция '{op}' в {line}")
                    self.program.append(Instruction(op=op, rd=rd, rs1=rs1, imm=imm, raw_text=line))
                elif loadi_match:
                    op, rd, imm_str = loadi_match.groups()
                    imm = int(imm_str)
                    if op not in self.config['op_to_unit']:
                        raise ValueError(f"Строка {i}: Недоступная операция '{op}' в {line}")
                    self.program.append(Instruction(op=op, rd=rd, imm=imm, raw_text=line))

    def run(self):
        register_ready_at: Dict[str, int] = {}

        units_free_at: Dict[str, List[int]] = {
            unit_type: [0] * count for unit_type, count in self.config['units'].items()
        }

        total_time = 0
        last_time = 0
        for instr in self.program:
            source_regs = [r for r in [instr.rs1, instr.rs2, instr.rd if instr.op == 'sw' else None] if r]
            data_ready_at = max([register_ready_at.get(r, 0) for r in source_regs], default=0)

            unit_type = self.config['op_to_unit'][instr.op]

            earliest_unit_free_at = min(units_free_at[unit_type])
            unit_index_to_use = units_free_at[unit_type].index(earliest_unit_free_at)

            start_time = max(data_ready_at, earliest_unit_free_at, last_time) + 1
            last_time = start_time
            
            latency = self.config['latency'][instr.op]
            end_time = start_time + latency - 1

            instr.start_cycle = start_time
            instr.complete_cycle = end_time

            if instr.rd and instr.op != 'sw':
                register_ready_at[instr.rd] = end_time

            units_free_at[unit_type][unit_index_to_use] = end_time
            
            total_time = max(total_time, end_time)

            self.compute_and_commit(instr)

        self.total_cycles = total_time

    def compute_and_commit(self, instr):
        op = instr.op

        val1 = self.registers.get(instr.rs1, 0)
        val2 = self.registers.get(instr.rs2, 0)

        result = None

        if op == 'li':
            result = instr.imm
        elif op == 'addi':
            result = val1 + instr.imm
        elif op == 'subi':
            result = val1 - instr.imm
        elif op == 'muli':
            result = val1 * instr.imm
        elif op == 'divi':
            result = val1 // instr.imm
        elif op == 'lw':
            base_addr = self.registers.get(instr.rs1, 0)
            address = base_addr + instr.offset
            result = self.memory.get(address, 0)
        elif op == 'add':
            result = val1 + val2
        elif op == 'sub':
            result = val1 - val2
        elif op == 'mul':
            result = val1 * val2
        elif op == 'div':
            result = val1 // val2
        elif op == 'sw':
            pass 
        else:
            raise NotImplementedError(f"Операция '{op}' не реализована")

        if instr.op == 'sw':
            base_addr = self.registers.get(instr.rd, 0)
            address = base_addr + instr.offset
            value_to_store = self.registers.get(instr.rs1, 0)
            self.memory[address] = value_to_store
        elif instr.rd:
                self.registers[instr.rd] = result

    def print_timeline(self):
        header_text = "Результаты симуляции (Таймлайн)"
        width = 80
        print(f"\n{'=' * width}")
        print(f"{header_text.center(width)}")
        print(f"{'=' * width}")

        if not self.program:
            print("Программа не загружена или пуста.")
            return

        try:
            max_len = max(len(instr.raw_text) for instr in self.program)
        except ValueError:
            max_len = 20

        print(f"{'Инструкция':<{max_len}} | {'Start':>5} | {'End':>5} | Таймлайн (Циклы 1..{self.total_cycles})")
        print(f"{'-' * max_len}-+---------+-------+-{'-' * (self.total_cycles if self.total_cycles < 65 else 65)}")

        for instr in self.program:
            timeline_bar = ['·'] * self.total_cycles

            for c in range(instr.start_cycle - 1, instr.complete_cycle):
                if 0 <= c < self.total_cycles:
                    timeline_bar[c] = '#'

            timeline_str = "".join(timeline_bar)

            print(f"{instr.raw_text:<{max_len}} "
                f"| {instr.start_cycle - 1:>5} "
                f"| {instr.complete_cycle - 1:>5} "
                f"| {timeline_str}")

        print(f"\nИТОГО ЦИКЛОВ: {self.total_cycles}")
