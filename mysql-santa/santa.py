#! /usr/bin/env python3

from random import randint, random

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



@click.group(help="SQL clause is coming to town")
def sql():
    pass


@sql.command()
@click.option("--size", default=1000000, help="Number of rows to create in total")
@click.option("--nicelevel", default=0.9, help="Level of niceness in population(double: 0-1)")
def setup_tables(size, nicelevel):
    sql_setup = [
        "drop table if exists santa",
        """ create table santa (
                id integer not null primary key auto_increment,
                name varchar(64) not null,
                loc point srid 0 not null,
                age integer not null,
                behavior enum('naughty', 'nice') not null,
                wish varchar(64) not null,
                index(niceflag, name),
                spatial index(loc)
        )""",
    ]

    db = MySQLdb.connect(**db_config)
    sql = """insert into santa
             (id, name, loc, age, niceflag, wish )
      values (%(id)s, %(name)s, ST_GeomFromText('Point(%(xloc)s %(yloc)s)'), %(age)s, %(niceflag)s, %(wish)s)"""

    for cmd in sql_setup:
        try:
            c = db.cursor()
            c.execute(cmd)
        except MySQLdb.OperationalError as e:
            click.echo(f"setup_tables: failed {e} with {cmd}.")

    for i in range(1, size):
        data = {
            "id": i,
            "name": "".join([chr(randint(97, 97 + 26)) for x in range(64)]),
            "xloc": random()*360-180,
            "yloc": random()*180-90,
            "age": randint(1, 100),
            "behavior": "naughty" if random() > nicelevel else "nice",
            "wish": "".join([chr(randint(97, 97 + 26)) for x in range(64)]),
        }

        c.execute(sql, data)
        if i%1000 == 0:
            print(f"{i=}")
            db.commit()

    db.commit()

sql()
