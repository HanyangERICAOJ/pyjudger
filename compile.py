import subprocess

def compile(submission_path: str, compile_command: str) -> bool:
    compile_process = subprocess.Popen(compile_command, shell=True, cwd=submission_path)
    compile_process.communicate()
    return compile_process.returncode == 0