import os
from typing import Union
import psycopg
from psycopg.rows import dict_row
import boto3

TESTCASE_BASEPATH = '/home/jhsapps/testcase'

# Non pair input, output
class LocalTestcase:
    def __init__(self, filename: str) -> None:
        self.filename = filename

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, ServerTestcase):
            return self.filename == __o.input_filename or self.filename == __o.output_filename
        else:
            return False

# pair input, output
class ServerTestcase:
    def __init__(self, id, input_url: str, output_url: str) -> None:
        self.id = id
        self.input_filename = input_url.split('/')[-1]
        self.output_filename = output_url.split('/')[-1]

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, LocalTestcase):
            return __o.filename == self.input_filename or __o.filename == self.output_filename
        else:
            return False

# pair input, output
# Testcase Result
# 0 -> Accepted
# 1 -> Wrong Answer
# 2 -> Time Limit Exceed
# 3 -> Memory Limit Exceed
# 4 -> Runtime Error
# 5 -> Compile Error
# 6 -> Output Limit Exceed
# 100xxx -> Syscall Error

class Testcase:
    def __init__(self, id, input_path, output_path) -> None:
        self.id = id
        self.input_path = input_path
        self.output_path = output_path

        self.result = -1

        self.memory: Union[None, int] = None
        self.time: Union[None, int] = None

class Result:
    ACCEPTED = 0
    WRONG_ANSWER = 1
    TIME_LIMIT_EXCEED = 2
    MEMORY_LIMIT_EXCEED = 3
    RUNTIME_ERROR = 4
    COMPILE_ERROR = 5
    OUTPUT_LIMIT_EXCEED = 6


def prepare_testcase(problem_id: int) -> 'list[Testcase]':
    server_testcases: list[ServerTestcase] = []

    problem_number = 0

    try:
        with psycopg.connect("dbname=heoj user=postgres password=rkwkjanghs64 hostaddr=127.0.0.1 port=5432", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT testcase.id, testcase.input_url, testcase.output_url, testcase.problem_id, problem.number
                    FROM testcase LEFT JOIN problem ON testcase.problem_id = problem.id 
                    WHERE problem.id=%s;
                """, (problem_id,))

                records = cur.fetchall()
                

                for record in records:
                    problem_number = record['number']
                    server_testcases.append(ServerTestcase(record['id'], record['input_url'], record['output_url']))
    except:
        # DB Connect Error
        return []

    if not os.path.exists(TESTCASE_BASEPATH):
        os.mkdir(TESTCASE_BASEPATH)

    problem_testcase_path = os.path.join(TESTCASE_BASEPATH, str(problem_number))
    
    if not os.path.exists(problem_testcase_path):
        os.mkdir(problem_testcase_path)

    # 2. Get local testcases
    local_testcases: list[LocalTestcase] = [LocalTestcase(f) for f in os.listdir(problem_testcase_path) if os.path.isfile(os.path.join(problem_testcase_path, f))]
    
    # 4. Compare
    only_local_testcases = [tc for tc in local_testcases if tc not in server_testcases]
    only_server_testcases = [tc for tc in server_testcases if tc not in local_testcases]

    # 5. Download
    s3 = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_KEY'),
        region_name=os.getenv('AWS_REGION'),
    )
    for server_testcase in only_server_testcases:
        s3.download_file(
            os.getenv('AWS_S3_BUCKET_NAME'),
            "{}/{}".format(problem_number, server_testcase.input_filename),
            os.path.join(problem_testcase_path, server_testcase.input_filename),
        )
        s3.download_file(
            os.getenv('AWS_S3_BUCKET_NAME'),
            "{}/{}".format(problem_number, server_testcase.output_filename),
            os.path.join(problem_testcase_path, server_testcase.output_filename),
        )
        # 6. Data formatting
        with open(os.path.join(problem_testcase_path, server_testcase.input_filename), 'r+') as f:
            lines = [line.strip()+'\n' for line in f.read().strip().splitlines()]
            f.seek(0)
            f.writelines(lines)
            f.truncate()
        
        with open(os.path.join(problem_testcase_path, server_testcase.output_filename), 'r+') as f:
            lines = [line.strip()+'\n' for line in f.read().strip().splitlines()]
            f.seek(0)
            f.writelines(lines)
            f.truncate()

    # 7. Remove
    for local_testcase in only_local_testcases:
        os.remove(os.path.join(problem_testcase_path, local_testcase.filename))

    # 8. Return testcases
    return [
        Testcase(
            server_testcase.id,
            os.path.join(problem_testcase_path, server_testcase.input_filename),
            os.path.join(problem_testcase_path, server_testcase.output_filename),
        ) for server_testcase in server_testcases
    ]

def send_testcase_result(testcase: Testcase, submission_id: int):
    try:
        with psycopg.connect(os.getenv('DB_CONNECTION_STRING', ''), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO testcase_result(submission_id, testcase_id, result, memory, time)
                    VALUES ( %s, %s, %s, %s, %s );
                """, (submission_id, testcase.id, testcase.result, testcase.memory, testcase.time))
            conn.commit()
    except (BaseException) as err:
        # DB Related Error
        return None