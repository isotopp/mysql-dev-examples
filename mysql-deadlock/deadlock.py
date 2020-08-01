#! /usr/bin/env python3

import sys
import random
import string

import click
import MySQLdb
import MySQLdb.cursors

from time import sleep
from pprint import pprint

db_config = dict(
    host="localhost",
    user="kris",
    passwd="geheim",
    db="kris",
    cursorclass=MySQLdb.cursors.DictCursor,
)

sql_insert_into = "insert into %s ( id, counter) values ( %d, %d )"

sql_update = "update %s set counter = counter + 1 where id = %d"

db = MySQLdb.connect(**db_config)


def ddl(sql, okmsg, failmsg):
    """ Execute a DDL command """
    try:
        c = db.cursor()
        c.execute(sql)
        click.echo(okmsg)
    except MySQLdb.OperationalError as e:
        click.echo(failmsg)


@click.group(help="Test with multiple connections")
def sql():
    pass


@sql.command()
@click.option("--name", default="demo", help="Table name to drop")
def drop(name):
    """ Drop the demo table """
    cmd = f"drop table {name}"
    ddl(cmd, f"Table {name} dropped.", f"Table {name} did not exist.")


@sql.command()
@click.option("--name", default="demo", help="Table name to create")
def create(name):
    """ Create the demo table empty. """
    cmd = f"""create table {name} ( id serial, counter integer not null default '0' )"""
    ddl(cmd, f"Table {name} created.", f"Table {name} did already exist.")


@sql.command()
@click.option("--name", default="demo", help="Table name to truncate here")
def truncate(name):
    """ Truncate the demo table. """
    cmd = f"truncate table {name}"
    ddl(cmd, f"Table {name} truncated.", f"Table {name} did not exist.")


@sql.command()
@click.option("--name", default="demo", help="Table name to insert into")
@click.option("--size", default=1000, help="Number of rows to create in total")
def setup(name, size):
    """ Write test records into the demo table. """
    for i in range(1, size + 1):
        cmd = f"replace into {name} (id, counter) values ( {i}, 0)"

        c = db.cursor()
        try:
            c.execute(cmd)
        except MySQLdb.Error as e:
            click.echo(f"MySQL Error: {e}")
            sys.exit()

    click.echo(f"Counters 1 to {size} set to 0.")
    db.commit()


def select_update(name, id):
    cmd = f"select counter from {name} where id = {id} for update"
    c = db.cursor()
    try:
        c.execute(cmd)
    except MySQLdb.OperationalError as e:
        click.echo(f"MySQL Error: {e}")
        return None

    row = c.fetchone()
    return row["counter"]

def update(name, id, counter):
    cmd = f"update {name} set counter = {counter} where id = {id}"
    c = db.cursor()
    try:
        c.execute(cmd)
    except MySQLdb.Error as e:
        click.echo(f"MySQL Error: {e}")
        sys.exit(0)

def count_with_locking(name, tag, position1, position2, verbose=False):
        # I would rather have a START TRANSACTION READ WRITE
        # but MySQLdb does not offer this natively.
        db.begin()

        # read, with FOR UPDATE
        done = False
        while not done:
            counter1 = select_update(name, position1)
            sleep(1)
            counter2 = select_update(name, position2)
            if counter1 is not None and counter2 is not None:
                done = True
            else:
                if verbose:
                    print(f"{tag} *** Retry *** {position1}, {position2} = {counter1}, {counter2}")

        if verbose:
            print(f"{tag} {position1}, {position2} = {counter1}, {counter2}")

        # modify
        counter1 += 1
        counter2 += 1

        # write
        update(name, position1, counter1)
        update(name, position2, counter2)

        # and release the locks, too
        db.commit()

@sql.command()
@click.option("--name", default="demo", help="Table name to count in")
@click.option("--size", default=1000, help="Number rows in counter table")
@click.option("--iterations", default=10000, help="Number of increments")
@click.option("--verbose/--no-verbose", default=False, help="Log each commit?")
def count_up(name, size, iterations, verbose):
    """  Increment counters i and i+1, across an array, counting i upwards """
    for i in range(0, iterations):

        # We will count up position1 and position2
        position1 = (i % size) + 1
        position2 = ((i + 1) % size) + 1

        count_with_locking(name, "up  ", position1, position2, verbose)


@sql.command()
@click.option("--name", default="demo", help="Table name to count in")
@click.option("--size", default=1000, help="Number rows in counter table")
@click.option("--iterations", default=10000, help="Number of increments")
@click.option("--verbose/--no-verbose", default=False, help="Log each commit?")
def count_down(name, size, iterations, verbose):
    """  Increment counters i and i+1, across an array, counting i upwards """
    for i in range(iterations, 0, -1):

        # We will count down position1 and position2
        position1 = (i % size) + 1
        position2 = ((i - 1) % size) + 1

        count_with_locking(name, "down", position1, position2, verbose)

sql()
