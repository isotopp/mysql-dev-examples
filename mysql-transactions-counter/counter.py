#! /usr/bin/env python3

import sys

import click
import MySQLdb
import MySQLdb.cursors


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
        click.echo(f"{failmsg}: {e}")


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
    for i in range(0, size):
        cmd = f"insert into {name} (id, counter) values ( {i+1}, 0)"

        c = db.cursor()
        try:
            c.execute(cmd)
        except MySQLdb.Error as e:
            click.echo(f"MySQL Error: {e}")
            sys.exit()

    db.commit()


@sql.command()
@click.option("--name", default="demo", help="Table name to count in")
@click.option("--id", default=0, help="Counter to use")
@click.option("--count", default=1000, help="Number of increments")
def count(name, id, count):
    """ Increment counter --id by --count many steps in table --name """
    for i in range(0, count):
        cmd = f"update {name} set counter=counter+1 where id = {id}"

        c = db.cursor()
        c.execute(cmd)
        db.commit()


@sql.command()
@click.option("--name", default="demo", help="Table name to count in")
@click.option("--id", default=0, help="Counter to use")
@click.option("--count", default=1000, help="Number of increments")
def rmw_false(name, id, count):
    """ Increment counter using rmw logic """
    for i in range(0, count):

        # read
        cmd = f"select counter from {name} where id = {id}"
        c = db.cursor()
        c.execute(cmd)
        row = c.fetchone()

        # modify
        counter = row["counter"] + 1

        # write
        cmd = f"update {name} set counter = {counter} where id = {id}"
        c.execute(cmd)
        db.commit()


@sql.command()
@click.option("--name", default="demo", help="Table name to count in")
@click.option("--id", default=0, help="Counter to use")
@click.option("--count", default=1000, help="Number of increments")
def rmw_correct(name, id, count):
    """ Increment counter using rmw logic """
    for i in range(0, count):

        # I would rather have a START TRANSACTION READ WRITE
        # but MySQLdb does not offer this natively.
        db.begin() 

        # read, with FOR UPDATE
        cmd = f"select counter from {name} where id = {id} for update"
        c = db.cursor()
        c.execute(cmd)
        row = c.fetchone()

        # modify
        counter = row["counter"] + 1

        # write
        cmd = f"update {name} set counter = {counter} where id = {id}"
        c.execute(cmd)
        db.commit()


sql()
