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


db = MySQLdb.connect(**db_config)


def ddl(sql, okmsg, failmsg):
    """ Execute a DDL command """
    try:
        c = db.cursor()
        c.execute(sql)
        click.echo(okmsg)
    except MySQLdb.OperationalError as e:
        click.echo(failmsg)
        click.echo(sql)


@click.group(help="Test with foreign key constraints")
def sql():
    pass


@sql.command()
@click.option("--count", default=25, help="Number of tables to drop.")
def drop(count):
    """ Drop the demo table """
    for i in range(ord("a")+count, ord("a"), -1):
        t = chr(i-1)
        cmd = f"drop table if exists {t}"
        ddl(cmd, f"Table {t} dropped.", f"Table {t} did not exist.")


@sql.command()
@click.option("--count", default=25, help="Number of tables to create")
def create(count):
    """ Create count many tables with fk relationships. """
    cmd = f"create table a (id integer not null primary key )"
    ddl(cmd, "table a created.", "cannot create table a.")

    for i in range(ord("b"), ord("a")+count):
        t = chr(i)
        p = chr(i-1)
        cmd = f"""create table {t} ( 
    id integer not null primary key,
    p integer null,
    constraint {p}_link foreign key (p) references {p} (id)
)
        """
        ddl(cmd, f"table {t} created.", f"cannot create table {t}.")


def insert(cmd):
    c = db.cursor()
    try:
        c.execute(cmd)
    except MySQLdb.Error as e:
        click.echo(f"MySQL Error: {e}")

@sql.command()
@click.option("--count", default=25, help="How many tables to fill")
@click.option("--size", default=100, help="Number of rows to create per table")
def setup(count, size):
    """ Write test records into the demo table. """
    for j in range(1, size):
        cmd = f"insert into a values ({j})"
        insert(cmd)
    db.commit()

    for i in range(ord("b"), ord("a")+count):
        t = chr(i)
        for j in range(1, size):
            cmd = f"insert into {t} values ({j}, {j})"
            insert(cmd)
        db.commit()

sql()
