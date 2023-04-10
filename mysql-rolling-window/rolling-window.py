#! /usr/bin/env python3

import datetime
from random import randint

import MySQLdb
import MySQLdb.cursors
import click

debugflag = False


class DebugCursor(MySQLdb.cursors.DictCursor):
    def _query(self, q):
        if debugflag:
            print(f"Debug: {q}")
        super()._query(q)


db_config = dict(
    host="127.0.0.1",
    user="kris",
    passwd="geheim",
    db="kris",
    cursorclass=DebugCursor,
)

db = MySQLdb.connect(**db_config)


@click.group(help="Use window functions for rolling sums")
def sql():
    pass


@sql.command(help="Group by day")
def daily_groups():
    sql = """
    select id
         , date(d) as d
         , count(m) as cnt
         , sum(m) as total
         , sum(m)/count(m) as av 
      from data 
    group by id, date(d)
    order by id, d
    """
    cursor = db.cursor()
    cursor.execute(sql)
    result = cursor.fetchall()
    for row in result:
        print(f'id: {row["id"]:2d} date: {row["d"]}  -  cnt: {row["cnt"]:6d} sum: {row["total"]} average: {row["av"]}')


@sql.command(help="Partition by day")
def daily_partitions():
    sql = """
    select id
         , d
         , count(m) over w as cnt
         , sum(m) over w as total
         , sum(m) over w/count(m) over w as av 
      from data
  window w as (
    partition by id, date(d)
    order by id, d)
    """
    cursor = db.cursor()
    cursor.execute(sql)
    result = cursor.fetchall()
    for row in result:
        print(f'id: {row["id"]:2d} date: {row["d"]}  -  cnt: {row["cnt"]:6d} sum: {row["total"]} average: {row["av"]}')


@sql.command(help="Sliding window query - 24h")
def daily_window():
    sql = """
    select id
         , d
         , count(m) over w as cnt
         , sum(m) over w as total
         , sum(m) over w/count(m) over w as av 
      from data
  window w as (order by d range between interval 1 day preceding and current row)
  """
    cursor = db.cursor()
    cursor.execute(sql)
    result = cursor.fetchall()
    for row in result:
        print(f'id: {row["id"]:2d} date: {row["d"]}  -  cnt: {row["cnt"]:6d} sum: {row["total"]} average: {row["av"]}')


@sql.command(help="Fill data table with test data")
@click.option("--start", default="2020-01-01 00:00:00", help="Start date and time yyyy-mm-dd hh:mm:ss")
@click.option("--end", default="2020-12-31 23:59:59", help="End date and time yyyy-mm-dd hh:mm:ss")
@click.option("--count", default=1000, help="Number of values per day")
def fill_table(start="2020-01-01 00:00:00", end="2020-12-31 23:59:59", count=1000):
    cursor = db.cursor()
    cursor.execute("truncate table data")
    db.commit()

    today = datetime.datetime.fromisoformat(start)
    end = datetime.datetime.fromisoformat(end)
    one_day = datetime.timedelta(days=1)
    while today < end:
        print(f"Date = {today}")
        for i in range(0, count):
            id = randint(0, 10)
            d = today + datetime.timedelta(seconds=randint(0, 86399))
            m = randint(0, 10000)
            sql = "insert into data (id, d, m) values (%(id)s, %(d)s, %(m)s)"
            try:
                cursor.execute(sql, {"id": id, "d": d, "m": m})
            except MySQLdb._exceptions.IntegrityError:
                # The Birthday Paradox in Action
                # print(e)
                pass
        db.commit()
        today += one_day


@sql.command(help="Create a data table")
def setup_tables():
    sql_setup = [
        "drop table if exists data",
        """ create table data (
                id integer not null,
                d datetime not null,
                m integer not null,
                primary key (id, d)
        )""",
    ]

    for cmd in sql_setup:
        try:
            c = db.cursor()
            c.execute(cmd)
        except MySQLdb.OperationalError as e:
            click.echo(f"setup_tables: failed {e} with {cmd}.")


sql()
