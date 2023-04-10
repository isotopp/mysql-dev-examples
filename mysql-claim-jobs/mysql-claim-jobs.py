#! /usr/bin/env python3

from time import sleep
from random import randint
from sys import exit
from multiprocessing import Process

import click
import MySQLdb
import MySQLdb.cursors


db_config = dict(
    host="127.0.0.1",
    user="kris",
    passwd="geheim",
    db="kris",
    cursorclass=MySQLdb.cursors.DictCursor,
)


def find_candidates(cursor, wanted):
    candidate_cmd = "select id from jobs where d like %(search_string)s and status = %(wanted)s limit 100"
    search_string = chr(randint(97, 97 + 25)) + '%'
    try:
        cursor.execute(candidate_cmd, {"search_string": search_string, "wanted": wanted})
    except MySQLdb.OperationalError as e:
        click.echo(f"find_candidates: {e}")
        exit(1)

    candidate_ids = cursor.fetchall()

    return [c["id"] for c in candidate_ids]


def consumer(consumer_id):
    db = MySQLdb.connect(**db_config)
    c = db.cursor()

    while True:
        # find potential records to process with the status 'unclaimed'
        candidates = find_candidates(c, "unclaimed")

        # we did not find any
        if len(candidates) == 0:
            # this is important, it will drop the persistent read view.
            # not doing this means we will never see newly inserted records from the generator
            db.commit()
            continue

        # with the list of candidate ids, we select them for update, skipping locked records
        lock_cmd = "select id, d, e from jobs where status = 'unclaimed' and id in %(candidates)s for update skip locked"
        c.execute(lock_cmd, {"candidates": candidates})
        claimed_records = c.fetchall()  # these are the records we want to claim for processing

        # make us a list of ids of the claimed records
        claimed_ids = [ r["id"] for r in claimed_records]
        claimed_ids_count = len(claimed_ids)

        if len(claimed_ids) == 0:
            db.commit() # and drop the view
            continue

        # we claim the records, updating their status and owner
        claim_cmd = """update jobs 
           set status = 'claimed', 
           owner_date = now(), 
           owner_id = %(consumer_id)s
        where id in %(claimed_ids)s"""
        c.execute(claim_cmd, {"claimed_ids": claimed_ids, "consumer_id": consumer_id})
        db.commit()

        # doit(claimed_records) -- process the records, that takes some time
        print(f"consumer {consumer_id: } #records = {claimed_ids_count} - {claimed_ids}")
        sleep(0.1)

        # after processing we delete them
        done_cmd = "delete from jobs where id in %(claimed_ids)s"
        c.execute(done_cmd, {"claimed_ids": claimed_ids})
        db.commit()


def generator(generator_id):
    counter = 0
    step = 10

    cmd = "insert into jobs (id,d,e,status,owner_id,owner_date) values (NULL,%(d)s,%(e)s,'unclaimed',NULL,NULL)"

    db = MySQLdb.connect(**db_config)
    c = db.cursor()

    while True:
        data = {
            "d": "".join([chr(randint(97, 97 + 25)) for _ in range(64)]),
            "e": "".join([chr(randint(97, 97 + 25)) for _ in range(64)]),
        }
        c.execute(cmd, data)
        counter += 1
        if counter % step == 0:
            sleep(0.1)
            db.commit()

        if counter % 1000 == 0:
            print(f"counter = {counter}")


@click.group(help="Generate and consume jobs concurrently")
def sql():
    pass


@sql.command(help="Run job creation and consumer jobs")
def start_processing():
    proc_generator = []
    for i in range(1, 3):
        g = Process(target=generator, args=(i,))
        proc_generator.append(g)
        g.start()

    proc_consumer = []
    for i in range(1, 11):
        c = Process(target=consumer, args=(i,))
        proc_consumer.append(c)
        c.start()


@sql.command(help="Recreate jobs table")
def setup_tables():
    sql_setup = [
        "drop table if exists jobs",
        """ create table jobs (
                id integer not null primary key auto_increment,
                d varchar(64) not null,
                e varchar(64) not null,
                status enum("unclaimed", "claimed", "done") not null,
                owner_id integer null,
                owner_date datetime null,
                index(d),
                index(status)
        )""",
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
