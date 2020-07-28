#! /usr/bin/env python3

import sys
import random
import string

import click
import MySQLdb
import MySQLdb.cursors

from pprint import pprint

db_config = dict(
    host="localhost",
    user="kris",
    passwd="geheim",
    db="kris",
    cursorclass=MySQLdb.cursors.DictCursor,
)

sql_drop_table = "drop table %s"

sql_create_table = """create table %s (
    id serial,
    data varbinary(255) not null
)"""

sql_truncate_table = "truncate table %s"

sql_insert_into = 'insert into %s ( id, data) values ( %d, "%s" )'


db = MySQLdb.connect(**db_config)


@click.group(help="Test database connections under adverse conditions")
def sql():
    pass


@sql.command()
@click.option("--name", default="demo", help="Table name to drop")
def drop(name):
    """ Drop the demo table """
    cmd = sql_drop_table % name

    try:
        c = db.cursor()
        c.execute(cmd)
        click.echo(f'Table "{name}" dropped.')
    except MySQLdb.OperationalError as e:
        click.echo(f'Table "{name}" did not exist.')


@sql.command()
@click.option("--name", default="demo", help="Table name to create")
def create(name):
    """ Create the demo table empty. """
    cmd = sql_create_table % name

    try:
        c = db.cursor()
        c.execute(cmd)
        click.echo(f'Table "{name}" created.')
    except MySQLdb.OperationalError as e:
        click.echo(f'Table "{name}" did already exist')


@sql.command()
@click.option("--name", default="demo", help="Table name to insert into")
@click.option("--size", default=1000000, help="Number of rows to create in total")
@click.option("--commit-size", default=1000, help="Commit batch size")
@click.option("--verbose/--no-verbose", default=False, help="Log each commit?")
def fill(name, size, commit_size, verbose):
    """ Write test records into the demo table. """
    for i in range(0, size):
        str = "".join(
            random.choice(string.ascii_uppercase + string.digits) for _ in range(20)
        )
        cmd = sql_insert_into % (name, i + 1, str)

        c = db.cursor()
        try:
            c.execute(cmd)
        except MySQLdb.Error as e:
            click.echo(f"MySQL Error: {e}")
            sys.exit()

        if i % commit_size == 0:
            if verbose:
                print(f"Commit at {i}...")
            db.commit()

    db.commit()


@sql.command()
@click.option("--name", default="demo", help="Table name to truncate here")
def truncate(name):
    """ Truncate the demo table. """
    cmd = sql_truncate_table % name

    try:
        c = db.cursor()
        c.execute(cmd)
        click.echo(f'Table "{name}" truncated.')
    except MySQL.OperationalError as e:
        click.echo(f'Table "{name}" does not exist.')


sql()
