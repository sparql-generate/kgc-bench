"""Local databases for the conformance cases that read SQL tables: the PostgreSQL and
MySQL and SQL Server tracks of RMLio/rml-test-cases (a resource.sql per case) and RMLSTC0006a of
kg-construct/rml-io (a D2RQ source with placeholders, $CONNECTIONDSN; the CG does
not say which database, kg-construct/rml-io#147: PostgreSQL here, loaded with the
case's Friends.csv).

One container per kind and per harness command, from an image pinned by digest
(versions.env: POSTGRES_IMAGE, MYSQL_IMAGE), started on first use on a free port
of 127.0.0.1 and removed when the command exits: on the default port of its kind (5432,
3306, 1433), as the CG's test cases assume, one at a time on the machine (an inter-process
file lock; the command refuses to start a server whose port another program holds). Each case gets a database of its
own (cases run in parallel), created, loaded and dropped around the case.

The credentials are those the mappings of rml-test-cases give: postgres with an
empty password (trust authentication), root with an empty password.
"""

import atexit
import fcntl
import tempfile
import csv
import itertools
import os
import re
import shutil
import socket
import subprocess
import threading
import time

from harness import VERSIONS

_lock = threading.Lock()
_servers = {}
_counter = itertools.count()

USER = {"postgres": "postgres", "mysql": "root", "sqlserver": "sa"}
# the SQL Server mappings of rml-test-cases give the password "YourSTRONG!Passw0rd;":
# its ";" breaks an ODBC connection string built without quoting (SDM-RDFizer: login
# failed), so the container has another one, written into the mappings (fill_mapping)
SUITE_PASSWORD = "YourSTRONG!Passw0rd;"
PASSWORD = {"postgres": "", "mysql": "", "sqlserver": "YourSTRONG!Passw0rd1"}
PORT = {"postgres": 5432, "mysql": 3306, "sqlserver": 1433}
DRIVER = {"postgres": "org.postgresql.Driver", "mysql": "com.mysql.cj.jdbc.Driver",
          "sqlserver": "com.microsoft.sqlserver.jdbc.SQLServerDriver"}
IMAGE_KEY = {"postgres": "POSTGRES_IMAGE", "mysql": "MYSQL_IMAGE", "sqlserver": "SQLSERVER_IMAGE"}
SQLCMD = "/opt/mssql-tools18/bin/sqlcmd"


def available():
    """Whether Docker can be used without sudo."""
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_free(port):
    with socket.socket() as s:
        # SO_REUSEADDR: a port left in TIME_WAIT by an earlier server is free
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


class Server:
    def __init__(self, kind):
        self.kind = kind
        self.image = VERSIONS[IMAGE_KEY[kind]]
        # the default port of the kind, as the cases of the CG assume (an engine that
        # ignores the configured port, SDM-RDFizer on PostgreSQL, still reaches the
        # case's server); one such server at a time on the machine: an inter-process lock,
        # held while the server runs, and the port must then be free
        self.port = PORT[kind]
        self._lock = open(os.path.join(tempfile.gettempdir(), "kgc-bench-db-%s.lock" % kind), "w")
        fcntl.flock(self._lock, fcntl.LOCK_EX)   # waits for another harness command's server
        if not _port_free(self.port):
            self._release()
            raise RuntimeError("port %d (%s) is used by another program: the SQL cases need it "
                               "free (the default port, as the CG's test cases assume)"
                               % (self.port, kind))
        self.name = "kgcb-%s-%d-%d" % (kind, os.getpid(), self.port)
        env = {"postgres": ["-e", "POSTGRES_HOST_AUTH_METHOD=trust"],
               "mysql": ["-e", "MYSQL_ALLOW_EMPTY_PASSWORD=yes", "-e", "MYSQL_ROOT_HOST=%"],
               # ACCEPT_EULA=Y: the licence of the image, accepted by the benchmark's owner;
               # the Express edition, its memory bounded
               "sqlserver": ["-e", "ACCEPT_EULA=Y", "-e", "MSSQL_PID=Express",
                             "-e", "MSSQL_SA_PASSWORD=" + PASSWORD["sqlserver"],
                             "-e", "MSSQL_MEMORY_LIMIT_MB=1536"]}[kind]
        subprocess.run(["docker", "run", "-d", "--rm", "--name", self.name, "-m", "2g",
                        "-p", "127.0.0.1:%d:%d" % (self.port, PORT[kind])] + env + [self.image],
                       check=True, capture_output=True)
        atexit.register(self.stop)
        self._wait()

    def _client(self, db=None):
        if self.kind == "sqlserver":
            # a script file of its own per call: the cases run in parallel
            return ["docker", "exec", "-i", self.name, "sh", "-c",
                    "f=$(mktemp) && cat > $f && %s -C -b -I -S localhost -U sa -P '%s' -d %s -i $f;"
                    " r=$?; rm -f $f; exit $r" % (SQLCMD, PASSWORD["sqlserver"], db or "master")]
        if self.kind == "postgres":
            return ["docker", "exec", "-i", self.name, "psql", "-q", "-v", "ON_ERROR_STOP=1",
                    # over TCP: the server of the image's initialisation listens on its socket only
                    "-h", "127.0.0.1", "-U", "postgres", "-d", db or "postgres"]
        return ["docker", "exec", "-i", self.name, "mysql", "-uroot", "-h127.0.0.1"] + (
            [db] if db else [])

    def _wait(self, timeout=180):
        t0 = time.time()
        while time.time() - t0 < timeout:
            r = subprocess.run(self._client(), input="SELECT 1;", capture_output=True, text=True)
            if r.returncode == 0:
                return
            time.sleep(1)
        raise RuntimeError("database %s not ready: %s" % (self.name, r.stderr[-300:]))

    def sql(self, text, db=None):
        r = subprocess.run(self._client(db), input=text, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("SQL on %s: %s" % (self.name, (r.stderr + r.stdout)[-300:]))

    def stop(self):
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
        self._release()

    def _release(self):
        lock = getattr(self, "_lock", None)
        if lock:
            self._lock = None
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()


def server(kind):
    with _lock:
        if kind not in _servers:
            _servers[kind] = Server(kind)
        return _servers[kind]


class CaseDatabase:
    """A database of its own for one case: kind (postgres, mysql), name, the JDBC DSN,
    the SQLAlchemy URL (Morph-KGC), host and port (SDM-RDFizer)."""

    def __init__(self, kind, sql):
        self.kind = kind
        self.server = server(kind)
        self.name = "c%d_%d" % (os.getpid(), next(_counter))
        if kind == "mysql":
            # the MySQL scripts of rml-test-cases name their database test
            sql = re.sub(r"(?im)^\s*USE\s+test\s*;", "", sql)
            sql = re.sub(r"\btest\.(\w)", self.name + r".\1", sql)
        if kind == "sqlserver":
            # the SQL Server scripts of rml-test-cases name their database TestDB
            sql = re.sub(r"(?im)^\s*USE\s+TestDB\s*;", "", sql)
        self.server.sql("CREATE DATABASE %s;" % self.name)
        self.server.sql(sql, self.name)
        self.user, self.password = USER[kind], PASSWORD[kind]
        self.host, self.port = "127.0.0.1", self.server.port
        if kind == "sqlserver":
            self.dsn = "jdbc:sqlserver://%s:%d;databaseName=%s;encrypt=false" % (
                self.host, self.port, self.name)
            self.url = "mssql+pyodbc://sa:%s@%s:%d/%s?driver=ODBC+Driver+18+for+SQL+Server" \
                "&TrustServerCertificate=yes" % (
                    PASSWORD[kind].replace("!", "%21"), self.host, self.port, self.name)
        else:
            self.dsn = "jdbc:%s://%s:%d/%s" % ("postgresql" if kind == "postgres" else "mysql",
                                               self.host, self.port, self.name)
            self.url = "%s://%s@%s:%d/%s" % ("postgresql+psycopg2" if kind == "postgres" else
                                             "mysql+mysqlconnector", self.user, self.host,
                                             self.port, self.name)

    def drop(self):
        try:
            self.server.sql("DROP DATABASE IF EXISTS %s;" % self.name)
        except RuntimeError:
            pass

    def fill_mapping(self, text):
        """The mapping with the placeholders of its D2RQ source filled in."""
        text = text.replace("$CONNECTIONDSN", self.dsn).replace("CONNECTIONDSN", self.dsn)
        text = text.replace('"$USERNAME"', '"%s"' % self.user).replace(
            '"$PASSWORD"', '"%s"' % self.password).replace(
            '"%s"' % SUITE_PASSWORD, '"%s"' % self.password)
        if "d2rq:jdbcDriver" not in text:
            text = re.sub(r'(d2rq:jdbcDSN\s+"[^"]*"\s*;)', r'\1 d2rq:jdbcDriver "%s";'
                          % DRIVER[self.kind], text, count=1)
        return text


def case_kind(suite, case, case_dir):
    """The database a case needs ("postgres", "mysql") or None."""
    if suite.startswith("rml-test-cases"):
        if case.endswith("-PostgreSQL"):
            return "postgres"
        if case.endswith("-MySQL"):
            return "mysql"
        if case.endswith("-SQLServer"):
            return "sqlserver"
        return None
    try:
        text = open(os.path.join(case_dir, "mapping.ttl"), encoding="utf-8").read()
    except OSError:
        return None
    return "postgres" if "CONNECTIONDSN" in text else None


def case_sql(case_dir, kind):
    """The SQL that loads a case: its resource.sql, else a table per CSV file of the
    case (RMLSTC0006a: Friends.csv), integer columns where every value is one."""
    p = os.path.join(case_dir, "resource.sql")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read()
    out = []
    q = '"%s"' if kind == "postgres" else "`%s`"
    for f in sorted(os.listdir(case_dir)):
        if not f.endswith(".csv"):
            continue
        rows = list(csv.reader(open(os.path.join(case_dir, f), encoding="utf-8", newline="")))
        head, body = rows[0], [r for r in rows[1:] if r]
        ints = [all(re.fullmatch(r"-?\d+", r[i] or "") for r in body) for i in range(len(head))]
        # unquoted (PostgreSQL folds it to lower case, as the engines' queries do)
        table = f[:-4]
        out.append("CREATE TABLE %s (%s);" % (table, ", ".join(
            "%s %s" % (q % h, "INTEGER" if ints[i] else "VARCHAR(200)") for i, h in enumerate(head))))
        for r in body:
            out.append("INSERT INTO %s VALUES (%s);" % (table, ", ".join(
                v if ints[i] else "'%s'" % v.replace("'", "''") for i, v in enumerate(r))))
    return "\n".join(out) + "\n"
