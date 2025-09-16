import re
import copy
from dataclasses import dataclass
from typing import List, Dict, Optional

CPU_CONFIG = {
    'units': {
        'ALU': 2,
        'MUL_DIV': 1,
        'LOAD_STORE': 1,
        'INF': 1000000,
    },
    'latency': {
        'add': 1,
        'addi': 1,
        'sub': 1,
        'subi': 1,
        'mul': 3,
        'muli': 3,
        'div': 10,
        'divi': 4,
        'and': 1,
        'andi': 1,
        'or': 1,
        'ori': 1,
        'xor': 1,
        'xori': 1,
        'shr': 1,
        'shl': 1,
        'lw': 5,
        'li': 5,
        'sw': 5,
        'jne': 1,
        'jie': 1,
        'jgt': 1,
        'jge': 1,
        'jle': 1,
        'jlt': 1,
        'jmp': 1
    },
    'op_to_unit': {
        'add': 'ALU',
        'addi': 'ALU',
        'sub': 'ALU',
        'subi': 'ALU',
        'shl': 'ALU',
        'shr': 'ALU',
        'mul': 'MUL_DIV',
        'muli': 'MUL_DIV',
        'div': 'MUL_DIV',
        'divi': 'MUL_DIV',
        'and': 'ALU',
        'andi': 'ALU',
        'or': 'ALU',
        'ori': 'ALU',
        'xor': 'ALU',
        'xori': 'ALU',
        'lw': 'LOAD_STORE',
        'li': 'ALU',
        'sw': 'LOAD_STORE',
        'jne': 'INF',
        'jie': 'INF',
        'jgt': 'INF',
        'jge': 'INF',
        'jle': 'INF',
        'jlt': 'INF',
        'jmp': 'INF'
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
    target: str = ""
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
        self.labels: Dict[str, int] = {}
        
        self.registers: Dict[str, int] = {}
        self.memory: Dict[int, int] = {}
        
        self.waiting_instructions: List[Instruction] = []
        self.executing_instructions: List[Instruction] = []
        
        self.free_units: Dict[str, int] = dict(self.config['units'])
        self.register_writeback_cycle: Dict[str, int] = {}

    def load(self, file):
        instruction_index = 0
        with open(file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.endswith(':'):
                    label_name = line[:-1].strip()
                    if label_name in self.labels:
                        raise ValueError(f"Дублирующаяся метка: {label_name}")
                    self.labels[label_name] = instruction_index
                else:
                    instruction_index += 1

        r_type_regex = re.compile(r"^\s*(\w+)\s+(\w+),\s*(\w+),\s*(\w+)\s*$")
        mem_type_regex = re.compile(r"^\s*(\w+)\s+(\w+),\s*(-?\d+)\((\w+)\)\s*$")
        imm_type_regex = re.compile(r"^\s*(\w+)\s+(\w+),\s*(\w+),\s*#(-?\d+)\s*$")
        loadi_regex = re.compile(r"^\s*(\w+)\s+(\w+),\s*#(-?\d+)\s*$")
        branch_regex = re.compile(r"^\s*(jie|jne|jge|jgt|jlt|jle)\s+(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*$")
        jmp_regex = re.compile(r"^\s*(jmp)\s+(\w+)\s*$")
        shift_regex = re.compile(r"^\s*(shl|shr)\s+(\w+),\s*#(\d+)\s*$")

        with open(file) as f:
            for i, line in enumerate(f):
                line = line.strip()
                r_match = r_type_regex.match(line)
                mem_match = mem_type_regex.match(line)
                imm_match = imm_type_regex.match(line)
                loadi_match = loadi_regex.match(line)
                branch_match = branch_regex.match(line)
                jmp_match = jmp_regex.match(line)
                shift_match = shift_regex.match(line)

                if shift_match:
                    op, rd, imm_str = shift_match.groups()
                    if op not in self.config['op_to_unit']:
                        raise ValueError(f"Строка {i}: Недоступная операция '{op}' в {line}")
                    self.program.append(Instruction(op=op, rd=rd, rs1=rd, imm=int(imm_str), raw_text=line))
                elif jmp_match:
                    op, target_label = jmp_match.groups()
                    if target_label not in self.labels:
                        raise ValueError(f"Строка {i+1}: Неизвестная метка '{target_label}'")
                    self.program.append(Instruction(op=op, target=target_label, raw_text=line))
                elif branch_match:
                    op, rs1, rs2, target_label = branch_match.groups()
                    if target_label not in self.labels:
                        raise ValueError(f"Строка {i+1}: Неизвестная метка '{target_label}'")
                    self.program.append(Instruction(op=op, rs1=rs1, rs2=rs2, target=target_label, raw_text=line))
                elif r_match:
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
                    if op not in self.config['op_to_unit']:
                        raise ValueError(f"Строка {i}: Недоступная операция '{op}' в {line}")
                    self.program.append(Instruction(op=op, rd=rd, rs1=rs1, imm=int(imm_str), raw_text=line))
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

        self.execution_trace: List[Instruction] = []
        pc = 0
        while pc < len(self.program):
            instr = self.program[pc]
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
            self.execution_trace.append(copy.copy(instr))

            if instr.rd and instr.op != 'sw':
                register_ready_at[instr.rd] = end_time

            units_free_at[unit_type][unit_index_to_use] = end_time

            total_time = max(total_time, end_time)

            self.compute_and_commit(instr)

            next_pc = pc + 1
            if instr.op == 'jmp':
                next_pc = self.labels[instr.target]
            elif instr.op == 'jie' and self.registers.get(instr.rs1, 0) == self.registers.get(instr.rs2, 0):
                next_pc = self.labels[instr.target]
            elif instr.op == 'jne' and self.registers.get(instr.rs1, 0) != self.registers.get(instr.rs2, 0):
                next_pc = self.labels[instr.target]
            elif instr.op == 'jgt' and self.registers.get(instr.rs1, 0) > self.registers.get(instr.rs2, 0):
                next_pc = self.labels[instr.target]
            elif instr.op == 'jge' and self.registers.get(instr.rs1, 0) >= self.registers.get(instr.rs2, 0):
                next_pc = self.labels[instr.target]
            elif instr.op == 'jlt' and self.registers.get(instr.rs1, 0) < self.registers.get(instr.rs2, 0):
                next_pc = self.labels[instr.target]
            elif instr.op == 'jle' and self.registers.get(instr.rs1, 0) <= self.registers.get(instr.rs2, 0):
                next_pc = self.labels[instr.target]

            pc = next_pc

        self.total_cycles = total_time

    def compute_and_commit(self, instr):
        op = instr.op

        if op[0] == 'j' and len(op) == 3:
            return

        val1 = self.registers.get(instr.rs1, 0)
        val2 = self.registers.get(instr.rs2, 0)

        result = None

        if op == 'li':
            result = instr.imm
        elif op == 'shl':
            result = val1 << instr.imm
        elif op == 'shr':
            result = val1 >> instr.imm
        elif op == 'addi':
            result = val1 + instr.imm
        elif op == 'subi':
            result = val1 - instr.imm
        elif op == 'muli':
            result = val1 * instr.imm
        elif op == 'divi':
            result = val1 // instr.imm
        elif op == 'andi':
            result = val1 & instr.imm
        elif op == 'ori':
            result = val1 | instr.imm
        elif op == 'xori':
            result = val1 ^ instr.imm
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
        elif op == 'and':
            result = val1 & val2
        elif op == 'or':
            result = val1 | val2
        elif op == 'xor':
            result = val1 ^ val2
        elif op == 'sw':
            pass 
        else:
            print(f"Операция '{op}' не реализована")
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

    def print_trace(self):
        header_text = "Результаты симуляции (Трейс)"
        width = 80
        print(f"\n{'=' * width}")
        print(f"{header_text.center(width)}")
        print(f"{'=' * width}")
        for instr in self.execution_trace:
            print(f"[{instr.start_cycle:03d}-{instr.complete_cycle:03d}] {instr.raw_text}")

        print(f"\nИТОГО ЦИКЛОВ: {self.total_cycles}")
