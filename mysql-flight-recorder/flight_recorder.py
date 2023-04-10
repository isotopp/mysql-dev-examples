#! /usr/bin/env python3

import configparser
from datetime import datetime
import os
from typing import Dict, Optional, Any
from distutils.version import LooseVersion
import subprocess

import MySQLdb  # type: ignore
import MySQLdb.cursors  # type: ignore


config_defaults = {
    "logdir": "/var/log/mysql_flight_recorder",
    "pidfile": "/tmp/mysql_flight_recorder.pid",
    "compresscmd": "bzip2 -9",
}


class AlreadyRunningError(Exception):
    """ Exception raised by pidfile if an instance of the process is already running. """

    pass


class pidfile:
    """Contextmanager to ensure only one instance of a process is running.
    Uses a pidfile to lock, pidfile must have absolute pathname."""

    def __init__(self, filename="/tmp/pidfile"):
        self._file = filename

    def running_pid(self):
        """ Return pid if running process, if running, or 0 otherwise. """

        # Pidfile not present -> not running
        if not os.path.exists(self._file):
            return 0

        # Pidfile should contain a pid (integer)
        with open(self._file, "r") as f:
            try:
                pid = int(f.read())
            except (OSError, ValueError):
                return 0

        # We send a signal 0 (check presence and permissions, but no signal)
        # Can fail with ProcessLookupError -> pid does not exist
        # Can fail with PermissionError -> pid is not ours
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return 0

        # Return the actual pid
        return pid

    def __enter__(self):
        """ Contextmanager __enter__: Check if running, raise exception if so. Otherwise make pidfile. """
        pid = self.running_pid()
        if pid:
            raise AlreadyRunningError(f"Process {pid=} is already running.")

        with open(self._file, "w") as f:
            f.write(str(os.getpid()))

        return self

    def __exit__(self, *args):
        """Contextmanager __exit__: If pidfile exists, try to remove it. """
        if os.path.exists(self._file):
            try:
                os.remove(self._file)
            except OSError:
                pass


class Probe:
    db: MySQLdb
    version: str
    log: Dict

    def __init__(self, **kwargs):
        kwargs["cursorclass"] = MySQLdb.cursors.DictCursor
        try:
            self.db = MySQLdb.connect(**kwargs)
        except Exception as e:
            print(f"MySQLdb: cannot connect to {kwargs['host']}:{kwargs['port']}: {e=}")
            exit(1)

    def __repr__(self):
        str = ""
        for k in self.log:
            str += f"CMD: {k}\n"
            i = 0
            for line in self.log[k]:
                i += 1
                str += f"{i}: {line}\n"
            str += "\n"

        return str

    @classmethod
    def check_connparms(
        self, config: configparser.ConfigParser, section: str
    ) -> Optional[Dict]:
        """ Given a ConfigParser and a section name, make sure there is a set of db connection parameters in it."""
        config_valid: bool = True
        ret: Dict[str, Any] = {}

        for c in ["user", "passwd", "host"]:
            try:
                ret[c] = config[section][c]
            except KeyError:
                print(f"Config error[{section}]: mandatory entry {c}=<value> missing.")
                config_valid = False

        # port needs to be an integer
        try:
            port = int(config[section]["port"])
            ret["port"] = port
        except ValueError:
            print(
                f"Config error[{section}]: port={config[section]['port']} not an integer."
            )
            config_valid = False

        if not config_valid:
            return None

        return ret

    def _query(self, cmd: str) -> Any:
        c = self.db.cursor()
        try:
            c.execute(cmd)
        except (MySQLdb.OperationalError, MySQLdb.ProgrammingError) as e:
            print(f"MySQL Error: {cmd=}\n{e}\n")
            return None

        return c

    def update_version(self) -> None:
        cmd: str = "select version() as version"
        cursor = self._query(cmd)
        res = cursor.fetchone()

        self.version = res["version"]  # remember later for version comparisons

        self.log[cmd] = [res["version"]]

    def update_uptime(self) -> None:
        cmd: str = "show global status like 'Uptime'"
        cursor = self._query(cmd)
        res = cursor.fetchone()
        self.log[cmd] = [res["Value"]]

    def update_processlist(self) -> None:
        cmd: str = "show full processlist"
        cursor = self._query(cmd)
        self.log[cmd] = cursor.fetchall()

    def update_replica(self) -> None:
        cmd: str = "show slave status"
        cursor = self._query(cmd)
        res = cursor.fetchone()

        line = []
        for k, v in res.items():
            line.append(f"{k}: {v}")

        self.log[cmd] = line

    def update_innodb_status(self) -> None:
        cmd: str = "show engine innodb status"
        cursor = self._query(cmd)
        res = cursor.fetchone()

        self.log[cmd] = [res["Status"]]

    def update_innodb_trx(self) -> None:
        cmd: str = "select /*+ max_execution_time(10000) */ * from information_schema.innodb_trx"
        cursor = self._query(cmd)
        self.log[cmd] = cursor.fetchall()

    def update_innodb_locks(self) -> None:
        table = "information_schema.innodb_locks"
        if LooseVersion(self.version) > LooseVersion("8.0.1"):
            table = "performance_schema.data_locks"

        cmd = f"select /*+ max_execution_time(10000) */ * from {table}"
        cursor = self._query(cmd)
        self.log[cmd] = cursor.fetchall()

    def update_innodb_lock_waits(self) -> None:
        table = "information_schema.innodb_lock_waits"
        if LooseVersion(self.version) > LooseVersion("8.0.1"):
            table = "performance_schema.data_lock_waits"

        cmd = f"select /*+ max_execution_time(10000) */ * from {table}"
        cursor = self._query(cmd)
        self.log[cmd] = cursor.fetchall()

    def update_innodb_cmp(self) -> None:
        cmd: str = "select /*+ max_execution_time(10000) */ * from information_schema.innodb_cmp"
        cursor = self._query(cmd)
        self.log[cmd] = cursor.fetchall()

    def update_innodb_cmpmem(self) -> None:
        cmd: str = "select /*+ max_execution_time(10000) */ * from information_schema.innodb_cmpmem"
        cursor = self._query(cmd)
        self.log[cmd] = cursor.fetchall()

    def update_innodb_metrics(self) -> None:
        cmd: str = "select /*+ max_execution_time(10000) */ * from information_schema.innodb_metrics"
        cursor = self._query(cmd)
        self.log[cmd] = cursor.fetchall()

    def update_status(self) -> None:
        cmd: str = "show global status"
        cursor = self._query(cmd)
        self.log[cmd] = cursor.fetchall()

    def update_variables(self) -> None:
        cmd: str = "show global variables"
        cursor = self._query(cmd)
        self.log[cmd] = cursor.fetchall()

    def update_all(self) -> None:
        self.log = {}
        self.update_version()
        self.update_uptime()
        self.update_processlist()
        self.update_replica()
        self.update_innodb_status()
        self.update_innodb_trx()
        self.update_innodb_locks()
        self.update_innodb_lock_waits()
        self.update_innodb_locks()
        self.update_innodb_lock_waits()
        self.update_innodb_cmp()
        self.update_innodb_cmpmem()
        self.update_innodb_metrics()
        self.update_status()
        self.update_variables()

    def write(self, section: str) -> str:
        """ writes data to file ./section_hh_mm (current directory set by create_logdir() """
        hhmm = datetime.now().strftime("%H_%M")
        filename = f"{section}_{hhmm}"
        with open(filename, "w") as f:
            f.write(str(self))

        return filename

def which(program: str) -> Optional[str]:
    fpath, fname = os.path.split(program)

    if fpath:
        # Absolute Pathname -> must exist and be executable
        if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
            return program
        else:
            return None

    # Relative Pathname -> check each search path
    for path in os.environ["PATH"].split(os.pathsep):
        exe_file = os.path.join(path, program)
        if os.path.isfile(exe_file) and os.access(exe_file, os.X_OK):
            return exe_file

    return None


def create_logdir(logdir: str) -> None:
    """The flight recorder writes data to a directory logdir/current_weekday.
    By default, this is /var/log/mysql_flight_recorder/Thu or similar.
    """
    try:
        os.makedirs(logdir, mode=0o755, exist_ok=True)
    except Exception as e:
        print(f"Cannot make {logdir=}: {e=}")
        exit(1)

    os.chdir(logdir)

    try:
        subdir = datetime.now().strftime("%a")
        os.makedirs(subdir, mode=0o755, exist_ok=True)
    except Exception as e:
        print(f"Cannot make {subdir=} in {logdir=}: {e=}")
        exit(1)

    os.chdir(subdir)


def getconfig(defaults: dict) -> configparser.ConfigParser:
    config = configparser.ConfigParser(defaults=defaults)
    config.read(
        [
            "/etc/mysql/mysql-flight-recorder.ini",
            "/etc/mysql/mysql_flight_recorder.ini",
            os.path.expanduser("~/.mysql-flight-recorder.ini"),
            os.path.expanduser("~/.mysql_flight_recorder.ini"),
            os.path.expanduser("~/mysql-flight-recorder.ini"),
            os.path.expanduser("~/mysql_flight_recorder.ini"),
            "./.mysql-flight-recorder.ini",
            "./.mysql_flight_recorder.ini",
            "./mysql-flight-recorder.ini",
            "./mysql_flight_recorder.ini",
        ]
    )

    return config


config = getconfig(config_defaults)
with pidfile(config["DEFAULT"]["pidfile"]):
    create_logdir(config["DEFAULT"]["logdir"])

    probes = {}
    for section in config.sections():
        connparms = Probe.check_connparms(config, section)
        if not connparms:
            print(f"No config for {section=}.")
            continue

        probes[section] = Probe(**connparms)

    for probe in probes:
        # collect data from MySQL
        probes[probe].update_all()

        # Write data to file
        file = probes[probe].write(probe)

        # Compress data]
        cmd = f"{config[probe]['compresscmd']} {file}"
        if cmd:
            subprocess.run(cmd.split(" "))
