import os
from pty import STDERR_FILENO, STDIN_FILENO, STDOUT_FILENO
import resource
import signal
from stat import S_IRUSR, S_IWUSR
import os
import ctypes

from language import prepare_language
from submisson import prepare_submission, send_submission_result
import syscallnames
from testcase import Result, Testcase, prepare_testcase, send_testcase_result
from compile import compile

SUBMISSION_BASEPATH = '/home/jhsapps/submission'

libc = ctypes.CDLL('/lib/x86_64-linux-gnu/libc.so.6')
ptrace = libc.ptrace
ptrace.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
ptrace.restype = ctypes.c_int

class user_regs_struct(ctypes.Structure):
    _fields_ = [
        ("r15", ctypes.c_ulonglong),
        ("r14", ctypes.c_ulonglong),
        ("r13", ctypes.c_ulonglong),
        ("r12", ctypes.c_ulonglong),
        ("rbp", ctypes.c_ulonglong),
        ("rbx", ctypes.c_ulonglong),
        ("r11", ctypes.c_ulonglong),
        ("r10", ctypes.c_ulonglong),
        ("r9", ctypes.c_ulonglong),
        ("r8", ctypes.c_ulonglong),
        ("rax", ctypes.c_ulonglong),
        ("rcx", ctypes.c_ulonglong),
        ("rdx", ctypes.c_ulonglong),
        ("rsi", ctypes.c_ulonglong),
        ("rdi", ctypes.c_ulonglong),
        ("orig_rax", ctypes.c_ulonglong),
        ("rip", ctypes.c_ulonglong),
        ("cs", ctypes.c_ulonglong),
        ("eflags", ctypes.c_ulonglong),
        ("rsp", ctypes.c_ulonglong),
        ("ss", ctypes.c_ulonglong),
        ("fs_base", ctypes.c_ulonglong),
        ("gs_base", ctypes.c_ulonglong),
        ("ds", ctypes.c_ulonglong),
        ("es", ctypes.c_ulonglong),
        ("fs", ctypes.c_ulonglong),
        ("gs", ctypes.c_ulonglong),
    ]

def parse_memory(pid):
    total = 0
    with open('/proc/{}/maps'.format(pid), 'r') as f:
        for line in f.readlines():
            sline = line.split()
            start, end = sline[0].split('-')
            
            start = int(start, 16)
            end = int(end, 16)

            total += end - start
    return total // 1024

def set_resource_limit(time_limit, memory_limit):
    time_limit = time_limit # second
    memory_limit = memory_limit * 1024 * 1024 # mb to byte

    resource.setrlimit(resource.RLIMIT_CPU, (time_limit, time_limit + 1))
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024, 64 * 1024)) # 64 KB

def judge(submission_id: int) -> bool:
    submission = prepare_submission(submission_id)
    if submission == None:
        return False
    
    language = prepare_language(submission.language_id)
    if language == None:
        return False
    testcases = prepare_testcase(submission.problem_id)

    compile(submission.path, language.compile_command)

    accepted_count = 0
    
    for index, testcase in enumerate(testcases):
        testcase_with_result = run_testcase(testcase, os.path.join(SUBMISSION_BASEPATH, str(submission_id)), os.path.join(SUBMISSION_BASEPATH, str(submission_id), '{}.out'.format(index)), language.execute_command)
        
        if testcase_with_result.result == Result.ACCEPTED:
            accepted_count += 1

            if submission.memory == None:
                submission.memory = testcase_with_result.memory
            elif testcase_with_result.memory != None:
                submission.memory = max(submission.memory, testcase_with_result.memory)

            if submission.time == None:
                submission.time = testcase_with_result.time
            elif testcase_with_result.time != None:
                submission.time = max(submission.time, testcase_with_result.time)
        
        send_testcase_result(testcase_with_result, submission_id)
    
    submission.is_accepted = (accepted_count == len(testcases))
    send_submission_result(submission)

    return True

def run_testcase(testcase: Testcase, submission_path: str, output_path: str, execute_command: str) -> Testcase:
    child = os.fork()
    if child == 0:
        fdin = os.open(testcase.input_path, os.O_RDONLY)
        os.dup2(fdin, STDIN_FILENO)
        os.close(fdin)

        fdout = os.open(output_path, os.O_RDWR | os.O_CREAT, S_IRUSR | S_IWUSR)
        os.dup2(fdout, STDOUT_FILENO)
        os.close(fdout)

        fderr = os.open(os.devnull, os.O_WRONLY)
        os.dup2(fderr, STDERR_FILENO)
        os.close(fderr)

        set_resource_limit(1, 512)

        ptrace(0, 0, None, None)

        # execute command
        os.chdir(submission_path)
        os.execvp(execute_command.split(' ')[0], execute_command.split(' '))
    else:
        _status = 1
        _rusage = None
        memory = 0
        memory_syscall = ['mmap', 'brk', 'munmap', 'mremap', 'execve']

        while True:
            _, status, rusage = os.wait4(child, 0)
            _status = status
            _rusage = rusage
            if os.WIFEXITED(status):
                break

            if os.WIFSTOPPED(status):
                if os.WSTOPSIG(status) == signal.SIGXCPU:
                    testcase.result = Result.TIME_LIMIT_EXCEED
                    os.kill(child, signal.SIGXCPU)
                    break
                elif os.WSTOPSIG(status) == signal.SIGSEGV:
                    testcase.result = Result.MEMORY_LIMIT_EXCEED
                    os.kill(child, signal.SIGSEGV)
                    break
                elif os.WSTOPSIG(status) == signal.SIGXFSZ:
                    testcase.result = Result.OUTPUT_LIMIT_EXCEED
                    os.kill(child, signal.SIGXFSZ)
                    break
            
            if os.WIFSIGNALED(status):
                testcase.result = Result.RUNTIME_ERROR
                break

            regs = user_regs_struct()
            ptrace(12, child, None, ctypes.byref(regs))

            # Check memory usage from memory map
            if syscallnames.syscallnames[regs.orig_rax] in memory_syscall:
                now_memory = parse_memory(child)
                memory = max(memory, now_memory)
            
            # Check system call

            ptrace(24, child, None, None)

        exitcode = os.WEXITSTATUS(_status)

        if exitcode == 0:
            testcase.result = Result.ACCEPTED if grade_output(testcase, output_path) else Result.WRONG_ANSWER

            if testcase.result == Result.ACCEPTED:
                testcase.memory = memory
                testcase.time = int((_rusage.ru_utime + _rusage.ru_stime) * 1000)

            return testcase
        else:
            if testcase.result == -1:
                testcase.result = Result.RUNTIME_ERROR
        
        return testcase

def grade_output(testcase: Testcase, output_path: str) -> bool:
    try:
        with open(output_path, 'r') as output, open(testcase.output_path, 'r') as answer:
            output_lines = [line.strip()+'\n' for line in output.read().strip().splitlines()]
            answer_lines = [line.strip()+'\n' for line in answer.read().strip().splitlines()]

            if len(output_lines) != len(answer_lines):
                return False
            
            for output_line, answer_line in zip(output_lines, answer_lines):
                if output_line != answer_line:
                    return False
            return True
    except:
        return False