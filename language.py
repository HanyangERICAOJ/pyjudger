import os
import psycopg
from psycopg.rows import dict_row
from typing import Union
from compile import compile

class Language:
    def __init__(self, compile_command, execute_command, test_code, name, filename) -> None:
        self.compile_command = compile_command
        self.execute_command = execute_command
        self.test_code = test_code
        self.name = name
        self.filename = filename

def prepare_language(language_id: int) -> Union[Language, None]:
    try:
        with psycopg.connect(os.getenv('DB_CONNECTION_STRING', ''), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT language.id, language.compile, language.execute, language.name, language.file_name, language.example
                    FROM language
                    WHERE language.id=%s;
                """, (language_id,))

                record = cur.fetchone()

                if record == None:
                    # Language cannot find
                    return None

                return Language(record['compile'], record['execute'], record['example'], record['name'], record['file_name'])
    except:
        # DB Related Error
        return None

LANGUAGE_BASEPATH = '/home/jhsapps/langauge'

def test_language(language_id: int) -> bool:
    language = prepare_language(language_id)
    if language == None:
        return False
    
    if not os.path.exists(LANGUAGE_BASEPATH):
        os.mkdir(LANGUAGE_BASEPATH)

    language_path = os.path.join(LANGUAGE_BASEPATH, language.name)
    
    if not os.path.exists(language_path):
        os.mkdir(language_path)

    with open(os.path.join(LANGUAGE_BASEPATH, language.name, language.filename), 'w') as f:
        f.write(language.test_code)

    compile_result = compile(language_path, language.compile_command)
    return compile_result
