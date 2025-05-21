import random
import sys

import MySQLdb
import MySQLdb.cursors
import click

db_config = dict(
    host="127.0.0.1",
    user="kris",
    passwd="geheim",
    db="kris",
    cursorclass=MySQLdb.cursors.DictCursor,
)

db = MySQLdb.connect(**db_config)

@click.group(help="Work with Queues in MySQL")
def sql():
    pass



@sql.command()
def drop() -> None:
    """
    The drop function executes a SQL command to drop a table named 'queue' if it exists in the database.

    @return None

    This function uses MySQLdb to interact with the database. If the SQL command execution fails,
    the function catches the MySQLdb.Error exception and prints an error message, then exits the program.

    Parameters:
    - None
    """
    cmd = "drop table if exists queue"
    try:
        c = db.cursor()
        c.execute(cmd)
    except MySQLdb.Error as e:
        click.echo(f"MySQL Error: {e}")
        sys.exit()

@sql.command()
def create() -> None:
    cmd = """create table if not exists queue (
  id integer not null primary key auto_increment,
  sender integer not null,
  worker integer null,
  workunit integer not null
)"""

    try:
        c = db.cursor()
        c.execute(cmd)
    except MySQLdb.Error as e:
        click.echo(f"MySQL Error: {e}")
        sys.exit()


def do_produce(id: int, work_unit: int) -> None:
    try:
        cmd = "insert into queue (id, sender, worker, workunit) values (NULL, %(sender)s, NULL, %(workunit)s )"
        c = db.cursor()
        c.execute(cmd, { "sender": id, "workunit": work_unit})
    except MySQLdb.Error as e:
        click.echo(f"MySQL Error: {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error inserting into queue: {e}")
        sys.exit(1)

@sql.command()
@click.option("--id", default=0, help="Worker id.")
@click.option("--work-unit", default=10, help="Up to this many seconds of work.")
@click.option("--count", default=100, help="This many items.")
def produce(id: int, work_unit: int, count: int) -> None:
    for i in range(0, count):
        do_produce(id, random.randint(1, work_unit))
    db.commit()

@sql.command()
def consume():
    pass

sql()
