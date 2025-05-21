#! /usr/bin/env python

import sys

import MySQLdb
import MySQLdb.cursors
import click

db_config = dict(
    host="192.168.1.10",
    user="kris",
    passwd="geheim",
    db="million",
    cursorclass=MySQLdb.cursors.DictCursor,
)

db = MySQLdb.connect(**db_config)

@click.group(help="Create a million tables")
def sql():
    pass

def run_template(template: str, basename: str, count: int) -> None:
    for i in range(count):
        cmd = template.format(basename=basename, count=i)
        if i % 100 == 0:
            print(f"{cmd}", end="\r")

        try:
            c = db.cursor()
            c.execute(cmd)
        except MySQLdb.Error as e:
            click.echo(f"MySQL Error: {e}")
            sys.exit()
    print()


@sql.command()
@click.option("--count", default=1000000, help="number of tables to drop.")
@click.option("--basename", default="testtable", help="base name of tables.")
def drop(count: int, basename: str) -> None:
    """
    The drop function drops all the tables we created in the create function.

    The function will drop count many tables of the name "testtable_xxxxxxx",
    with "testtable" being whatever the basename is, and xxxxxx counting up to count.
    """
    template = "drop table if exists {basename}_{count:06d}"
    run_template(template=template, basename=basename, count=count)


@sql.command()
@click.option("--count", default=1000000, help="number of tables to drop.")
@click.option("--basename", default="testtable", help="base name of tables.")
def create(count: int, basename: str) -> None:
    """
    The create function creates all the tables we created in the create function.

    The function will create count many tables of the name "testtable_xxxxxxx",
    with "testtable" being whatever the basename is, and xxxxxx counting up to count.
    """
    template = "create table if not exists {basename}_{count:06d} (id serial, d varchar(200), e varchar(200), f varchar(200), i integer, j integer)"
    run_template(template=template, basename=basename, count=count)

sql()
