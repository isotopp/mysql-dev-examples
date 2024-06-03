#! /usr/bin/env python

import random
import sys
import uuid

import MySQLdb
import MySQLdb.cursors
import click

db_config = dict(
    host="192.168.1.10",
    user="kris",
    passwd="geheim",
    port=3306,
    db="kris",
    cursorclass=MySQLdb.cursors.DictCursor,
)

db = MySQLdb.connect(**db_config)


@click.group(help="Work with Queues in MySQL")
def sql():
    pass


@sql.command()
def drop():
    """ Drop the test table tbl """
    cmd = "drop table if exists tbl"
    try:
        c = db.cursor()
        c.execute(cmd)
    except MySQLdb.Error as e:
        click.echo(f"MySQL Error: {e}")
        sys.exit()


@sql.command()
def create():
    """ Create the test table tbl """
    sqlcmds = [
        """create table if not exists tbl (
          id integer not null,
          d varchar(200),
          primary key (id),
          index(d))
        """,
    ]

    for sqlcmd in sqlcmds:
        try:
            click.echo(f"Run {sqlcmd}: ", nl=False)
            c = db.cursor()
            c.execute(sqlcmd)
        except MySQLdb.Error as e:
            click.echo(f"MySQL Error: {e}")
            sys.exit()
        click.echo(" ok")


@sql.command()
@click.option("--count", default=100000, help="This many items.")
def generate(count):
    """ Generate some test data """
    sqlcmd = "insert into tbl (id, d) values ( %(id)s, %(d)s )"

    counter = 0
    data = []

    for i in range(0,count):
        item = {"id": i, "d": uuid.uuid4()}
        data.append(item)
        counter += 1

        if (counter % 1000) == 0:
            try:
                c = db.cursor()
                c.executemany(sqlcmd, data)
                click.echo(f"{counter=}")
            except MySQLdb.Error as e:
                click.echo(f"MySQL Error: {e}")
                sys.exit()

            data = []
            db.commit()

    db.commit()
    click.echo("complete.")

if __name__ == "__main__":
    sql()
