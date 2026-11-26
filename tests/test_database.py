"""Tests of harness.database: the SQL conformance cases on local databases.

    python -m unittest discover tests

The tests that start a container run only when Docker can be used.
"""

import os
import shutil
import tempfile
import unittest

from harness import SUITES, database


class Offline(unittest.TestCase):
    def test_case_kind(self):
        d = SUITES["rml-test-cases-sql"]
        self.assertEqual(database.case_kind("rml-test-cases-sql", "RMLTC0001a-PostgreSQL", d), "postgres")
        self.assertEqual(database.case_kind("rml-test-cases-sql", "RMLTC0001a-MySQL", d), "mysql")
        self.assertIsNone(database.case_kind("rml-test-cases", "RMLTC0001a-CSV", d))
        io = os.path.join(SUITES["rml-io"], "RMLSTC0006a")
        if os.path.isdir(io):
            self.assertEqual(database.case_kind("rml-io", "RMLSTC0006a", io), "postgres")
            self.assertIsNone(database.case_kind("rml-io", "RMLSTC0001a",
                                                 os.path.join(SUITES["rml-io"], "RMLSTC0001a")))

    def test_case_sql_from_csv(self):
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, "Friends.csv"), "w").write("id,name,age\n0,Monica O'Neil,33\n")
            sql = database.case_sql(d, "postgres")
            self.assertIn('CREATE TABLE Friends ("id" INTEGER, "name" VARCHAR(200), "age" INTEGER);', sql)
            self.assertIn("INSERT INTO Friends VALUES (0, 'Monica O''Neil', 33);", sql)
        finally:
            shutil.rmtree(d)

    def test_fill_mapping(self):
        db = database.CaseDatabase.__new__(database.CaseDatabase)
        db.kind, db.user, db.password, db.dsn = "postgres", "postgres", "", "jdbc:postgresql://127.0.0.1:1/c1"
        text = db.fill_mapping('<#S> d2rq:jdbcDSN "$CONNECTIONDSN";\n  d2rq:username "$USERNAME";\n'
                               '  d2rq:password "$PASSWORD" .\n')
        self.assertIn('d2rq:jdbcDSN "jdbc:postgresql://127.0.0.1:1/c1"; d2rq:jdbcDriver '
                      '"org.postgresql.Driver";', text)
        self.assertIn('d2rq:username "postgres"', text)
        self.assertIn('d2rq:password ""', text)
        db.password = "p1"
        self.assertIn('d2rq:password "p1"', db.fill_mapping('d2rq:password "YourSTRONG!Passw0rd;" .'))
        legacy = db.fill_mapping('d2rq:jdbcDSN "CONNECTIONDSN";\nd2rq:jdbcDriver "org.postgresql.Driver";\n')
        self.assertEqual(legacy.count("jdbcDriver"), 1)


@unittest.skipUnless(database.available() and not database.busy("postgres")
                     and database._port_free(database.PORT["postgres"])
                     and not (os.environ.get("KGC_BENCH_TEST_SQLSERVER") and database.busy("sqlserver")),
                     "Docker not usable, or a harness command (or another program) holds the database servers")
class Live(unittest.TestCase):
    def test_default_port_and_busy_port_refused(self):
        import socket
        srv = database.server("postgres")
        self.assertEqual(srv.port, 5432)
        srv.stop()
        database._servers.pop("postgres", None)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 5432))
            s.listen(1)
            with self.assertRaisesRegex(RuntimeError, "port 5432"):
                database.Server("postgres")

    def test_parallel_loads_do_not_mix(self):
        """Cases load their databases in parallel (SQL Server: one script file per call)."""
        import concurrent.futures as cf
        kind = "sqlserver" if os.environ.get("KGC_BENCH_TEST_SQLSERVER") else "postgres"

        def one(i):
            db = database.CaseDatabase(kind, "CREATE TABLE t%d (a INTEGER);" % i)
            try:
                db.server.sql("SELECT a FROM t%d;" % i, db.name)
            finally:
                db.drop()
            return True
        with cf.ThreadPoolExecutor(4) as ex:
            self.assertTrue(all(ex.map(one, range(8))))

    def test_postgres_case_database(self):
        db = database.CaseDatabase("postgres", 'CREATE TABLE t ("a" INTEGER); INSERT INTO t VALUES (1);')
        try:
            db.server.sql("SELECT a FROM t;", db.name)
            self.assertTrue(db.dsn.startswith("jdbc:postgresql://127.0.0.1:"))
        finally:
            db.drop()


if __name__ == "__main__":
    unittest.main()
