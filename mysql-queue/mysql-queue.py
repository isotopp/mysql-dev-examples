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
def drop():
    cmd = "drop table if exists queue"
    try:
        c = db.cursor()
        c.execute(cmd)
    except MySQLdb.Error as e:
        click.echo(f"MySQL Error: {e}")
        sys.exit()

@sql.command()
def create():
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


def do_produce(id, work_unit):
    cmd = "insert into queue (id, sender, worker, workunit) values (NULL, %(sender)s, NULL, %(workunit)s )"
    c = db.cursor()
    c.execute(cmd, { "sender": id, "workunit": work_unit})

@sql.command()
@click.option("--id", default=0, help="Worker id.")
@click.option("--work-unit", default=10, help="Up to this many seconds of work.")
@click.option("--count", default=100, help="This many items.")
def produce(id, work_unit, count):
    for i in range(0, count):
        do_produce(id, random.randint(1, work_unit))
    db.commit()

@sql.command()
def consume():
    pass

sql()
