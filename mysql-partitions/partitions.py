#! /usr/bin/env python3

from time import sleep
from random import randint
from multiprocessing import Process

import click
import MySQLdb
import MySQLdb.cursors


db_config = dict(
    host="127.0.0.1",
    port=8023,
    user="kris",
    passwd="geheim",
    db="kris",
    cursorclass=MySQLdb.cursors.DictCursor,
)

def create_partition(db, next_name, next_limit):
    cmd = f"alter table data add partition ( partition {next_name} values less than ( {next_limit}))"
    print(f"cmd = {cmd}")
    c = db.cursor()
    c.execute(cmd)


def partitioner():
    db = MySQLdb.connect(**db_config)
    c = db.cursor()

    while True:
        # force stats refresh
        c.execute("analyze table kris.data")

        # find the five highest partitions
        cmd = """select
          partition_name,
          partition_ordinal_position,
          partition_description,
          table_rows
        from
          information_schema.partitions
        where
          table_schema = "kris" and
          table_name = "data"
        order by
          partition_ordinal_position desc
        limit 5
        """
        c.execute(cmd)
        rows = c.fetchall()
        next_limit = int(rows[0]["PARTITION_DESCRIPTION"]) + 10000
        next_name = "p" + str(int(next_limit / 10000))

        if len(rows) < 5:
            print(f"create {next_name} reason: not enough partitions")
            create_partition(db, next_name, next_limit)
            continue

        sum = 0
        for row in rows:
            sum += int(row["TABLE_ROWS"])
        if sum > 0:
            print(f"create {next_name} reason: not enough empty partitions")
            create_partition(db, next_name, next_limit)
            continue

        sleep(0.1)


def drop_partition(db, partition_name):
    cmd = f"alter table data drop partition {partition_name}"
    c = db.cursor()
    print(f"cmd = {cmd}")
    c.execute(cmd)


def dropper():
    db = MySQLdb.connect(**db_config)
    c = db.cursor()

    while True:
        # force stats refresh
        c.execute("analyze table kris.data")

        #
        cmd = """ select
          partition_name,
          partition_ordinal_position,
          partition_description,
          table_rows
        from
          information_schema.partitions
        where
          table_schema = "kris" and
          table_name = "data" and
          table_rows > 0
        order by
          partition_ordinal_position asc
        """
        c.execute(cmd)
        rows = c.fetchall()
        if len(rows) >= 10:
            partition_name = rows[0]["PARTITION_NAME"]
            print(f"drop {partition_name} reason: too many partitions with data")
            drop_partition(db, partition_name)
            continue

        sleep(0.1)


def inserter():
    counter = 0
    step = 10

    cmd = "insert into data (id, d, e) values( NULL, %(d)s, %(e)s )"

    db = MySQLdb.connect(**db_config)
    c = db.cursor()

    while True:
        data = {
            "d": "".join([chr(randint(97, 97 + 26)) for x in range(64)]),
            "e": "".join([chr(randint(97, 97 + 26)) for x in range(64)]),
        }
        c.execute(cmd, data)
        counter += 1
        if counter % step == 0:
            db.commit()

        if counter % 1000 == 0:
            print(f"counter = {counter}")


@click.group(help="Load and delete data using partitions")
def sql():
    pass


@sql.command()
def start_processing():
    proc_partition = Process(target=partitioner)
    proc_partition.start()
    proc_drop = Process(target=dropper)
    proc_drop.start()
    proc_insert = Process(target=inserter)
    proc_insert.start()


@sql.command()
def setup_tables():
    sql_setup = [
        "drop table if exists data",
        """ create table data (
                id integer not null primary key auto_increment,
                d varchar(64) not null,
                e varchar(64) not null
        )""",
        "alter table data partition by range (id) ( partition p1 values less than (10000))",
        "insert into data (id, d, e) values ( 1, 'keks', 'keks' )",
        "commit",
    ]

    db = MySQLdb.connect(**db_config)

    for cmd in sql_setup:
        try:
            c = db.cursor()
            c.execute(cmd)
        except MySQLdb.OperationalError as e:
            click.echo(f"setup_tables: failed {e} with {cmd}.")


sql()
