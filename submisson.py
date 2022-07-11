import os
from typing import Union
import psycopg
from psycopg.rows import dict_row

SUBMISSION_BASEPATH = '/home/jhsapps/submission'

class Submission:
    def __init__(self, id, problem_id, language_id, filename) -> None:
        self.id = id
        self.problem_id = problem_id
        self.language_id = language_id
        self.path = os.path.join(SUBMISSION_BASEPATH, str(id))
        self.filename = filename

        self.memory: Union[None, int] = None
        self.time: Union[None, int] = None
        self.is_accepted: bool = False

def prepare_submission(submission_id: int):
    try:
        with psycopg.connect(os.getenv('DB_CONNECTION_STRING', ''), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT submission.id, submission.code, submission.language_id, submission.problem_id, language.file_name
                    FROM submission LEFT JOIN language ON submission.language_id = language.id
                    WHERE submission.id=%s;
                """, (submission_id,))

                record = cur.fetchone()

                if record == None:
                    # Submission cannot find
                    return None
    
                if not os.path.exists(SUBMISSION_BASEPATH):
                    os.mkdir(SUBMISSION_BASEPATH)

                submission_path = os.path.join(SUBMISSION_BASEPATH, str(submission_id))
                
                if not os.path.exists(submission_path):
                    os.mkdir(submission_path)

                with open(os.path.join(SUBMISSION_BASEPATH, str(submission_id), record['file_name']), 'w') as f:
                    f.write(record['code'])

                return Submission(record['id'], record['problem_id'], record['language_id'], os.path.join(SUBMISSION_BASEPATH, str(submission_id), record['file_name']))
    except:
        # DB Connect Error
        return None

def send_submission_result(submission: Submission):
    try:
        with psycopg.connect(os.getenv('DB_CONNECTION_STRING', ''), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE submission
                    SET
                        time=%s,
                        memory=%s,
                        is_accepted=%s
                    WHERE submission.id = %s;
                """, (submission.time, submission.memory, submission.is_accepted, submission.id))
            conn.commit()
    except:
        # DB Related Error
        return None