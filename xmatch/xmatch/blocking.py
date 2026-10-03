"""
DuckDB-based high-throughput candidate blocking engine.
Reduces O(N^2) search space to high-probability candidate pairs at billion-scale
using multi-pass inverted indexing on normalized blocking keys.
"""

import re
from typing import List, Dict, Any, Tuple
import duckdb


def create_blocking_keys(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate normalized blocking keys for candidate generation.
    """
    rec_id = record["id"]
    name = (record.get("name") or "").strip().lower()
    email = (record.get("email") or "").strip().lower()
    phone = re.sub(r"\D", "", record.get("phone") or "")

    # Phone blocks
    phone_7 = phone[-7:] if len(phone) >= 7 else phone
    phone_prefix_4 = phone_7[:4] if len(phone_7) >= 4 else ""
    phone_suffix_4 = phone_7[-4:] if len(phone_7) >= 4 else ""

    # Email username blocks
    email_user = email.split("@")[0] if "@" in email else email
    email_user_prefix_4 = email_user[:4] if len(email_user) >= 4 else email_user

    # Name tokens
    name_tokens = re.sub(r"[^\w\s]", "", name).split()
    first_token = name_tokens[0] if name_tokens else ""
    last_token = name_tokens[-1] if len(name_tokens) > 1 else ""
    first_initial = first_token[0] if first_token else ""

    return {
        "id": rec_id,
        "name": name,
        "email": email,
        "phone": phone,
        "phone_7": phone_7,
        "phone_prefix_4": phone_prefix_4,
        "phone_suffix_4": phone_suffix_4,
        "email_user": email_user,
        "email_user_prefix_4": email_user_prefix_4,
        "first_token": first_token,
        "last_token": last_token,
        "first_initial": first_initial,
    }


class DuckDBBlocker:
    """
    Columnar In-Memory SQL Blocker using DuckDB.
    """

    def __init__(self):
        self.con = duckdb.connect(database=":memory:")
        self._init_schema()

    def _init_schema(self):
        self.con.execute("""
            CREATE TABLE records (
                id INTEGER PRIMARY KEY,
                name VARCHAR,
                email VARCHAR,
                phone VARCHAR,
                phone_7 VARCHAR,
                phone_prefix_4 VARCHAR,
                phone_suffix_4 VARCHAR,
                email_user VARCHAR,
                email_user_prefix_4 VARCHAR,
                first_token VARCHAR,
                last_token VARCHAR,
                first_initial VARCHAR
            );
        """)

    def load_records(self, records: List[Dict[str, Any]]):
        """Insert records with generated blocking keys into DuckDB."""
        keys_list = [create_blocking_keys(r) for r in records]
        
        for k in keys_list:
            self.con.execute("""
                INSERT INTO records VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                k["id"], k["name"], k["email"], k["phone"], k["phone_7"],
                k["phone_prefix_4"], k["phone_suffix_4"],
                k["email_user"], k["email_user_prefix_4"],
                k["first_token"], k["last_token"], k["first_initial"]
            ))

    def generate_candidate_pairs(self) -> List[Tuple[int, int, str]]:
        """
        Execute multi-pass blocking queries in DuckDB.
        Returns unique pairs (id1, id2, blocking_rule) where id1 < id2.
        """
        query = """
        WITH candidate_pairs AS (
            -- Rule 1: Shared phone exchange (first 4 digits of 7-digit local number)
            SELECT a.id as id1, b.id as id2, 'shared_phone_prefix_4' as rule
            FROM records a
            JOIN records b ON a.phone_prefix_4 = b.phone_prefix_4
            WHERE a.id < b.id AND LENGTH(a.phone_prefix_4) >= 3

            UNION

            -- Rule 2: Shared email username prefix (first 4 characters)
            SELECT a.id as id1, b.id as id2, 'shared_email_prefix_4' as rule
            FROM records a
            JOIN records b ON a.email_user_prefix_4 = b.email_user_prefix_4
            WHERE a.id < b.id AND LENGTH(a.email_user_prefix_4) >= 3

            UNION

            -- Rule 3: Shared surname token
            SELECT a.id as id1, b.id as id2, 'shared_surname' as rule
            FROM records a
            JOIN records b ON a.last_token = b.last_token
            WHERE a.id < b.id AND LENGTH(a.last_token) >= 3

            UNION

            -- Rule 4: Shared first name token (e.g. kaan)
            SELECT a.id as id1, b.id as id2, 'shared_first_token' as rule
            FROM records a
            JOIN records b ON a.first_token = b.first_token
            WHERE a.id < b.id AND LENGTH(a.first_token) >= 3

            UNION

            -- Rule 5: Compact handle match (initial + surname == compact name)
            SELECT a.id as id1, b.id as id2, 'initial_surname_block' as rule
            FROM records a
            JOIN records b ON (
                (a.first_initial || a.last_token = b.first_token AND LENGTH(a.last_token) >= 3) OR
                (b.first_initial || b.last_token = a.first_token AND LENGTH(b.last_token) >= 3)
            )
            WHERE a.id < b.id
        )
        SELECT id1, id2, STRING_AGG(rule, ', ') as matched_rules
        FROM candidate_pairs
        GROUP BY id1, id2
        ORDER BY id1, id2;
        """
        return self.con.execute(query).fetchall()
