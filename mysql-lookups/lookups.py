#! /usr/bin/env python3

import sys
import random
import string

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

sql_setup = [
    "drop table if exists log, map",
    "create table log (id integer not null auto_increment primary key, device_id integer not null,change_time datetime not null, old_state varchar(64) not null, new_state varchar(64))",
    "create table map (id integer not null auto_increment primary key, state varchar(64) not null, index(state))",
]

states = [
    "racked",
    "burn-in",
    "provisionable",
    "setup",
    "installed",
    "live",
    "burn-in failed",
    "setup failed",
    "install failed",
    "broken",
    "to deprovision",
    "deprovisioned",
    "decommissioned",
]

db = MySQLdb.connect(**db_config)


@click.group(help="Data Warehouse Lookup Encoding Demo")
def sql():
    pass

@sql.command()
def prepare_log_transformation():
    cmd = "alter table log add column old_state_id integer not null after old_state, add column new_state_id integer not null after new_state, add index(old_state), add index(new_state)"
    c = db.cursor()
    print("Adding id columns and indexes")
    c.execute(cmd)

@sql.command()
def perform_log_transformation():
    cmd = "insert into map select cast(NULL as signed) as id, old_state as state from log group by state union select cast(NULL as signed) as id, new_state as state from log group by state"
    c = db.cursor()
    print("Populating map")
    c.execute(cmd)
    db.commit()

    cmd = "update log set log.old_state_id = ( select id from map where log.old_state = map.state)"
    print("Converting old_states")
    c.execute(cmd)
    db.commit()

    cmd = "update log set log.new_state_id = ( select id from map where log.new_state = map.state)"
    print("Converting new_states")
    c.execute(cmd)
    db.commit()

@sql.command()
def finish_log_transformation():
    cmd = "alter table log drop column old_state, drop column new_state"
    c = db.cursor()
    print("Removing string columns")
    c.execute(cmd)
 
@sql.command()
@click.option("--devicecount", default=1000, help="Number of device ids to create")
@click.option(
    "--statecount", default=10000, help="Number of state changes to create, per device"
)
def create_log_data(devicecount, statecount):
    for d in range(0, devicecount):
        for s in range(0, statecount):
            old_state = random.choice(states)
            new_state = random.choice(states)

            cmd = (
                "insert into log values (NULL, %(d)s, now(), %(old_state)s, %(new_state)s)"
            )
            c = db.cursor()
            c.execute(cmd, { "d": d, "old_state": old_state, "new_state": new_state})
        db.commit()

@sql.command()
def setup_tables():
    for cmd in sql_setup:
        try:
            c = db.cursor()
            c.execute(cmd)
        except MySQLdb.OperationalError as e:
            click.echo(f"setup_tables: failed {e} with {cmd}.")


sql()
