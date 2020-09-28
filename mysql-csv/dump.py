#! /usr/bin/env python
# -*- coding: utf-8 -*-

# pip install mysqlclient (https://pypi.org/project/mysqlclient/)
import MySQLdb
import csv

# connect to database, set mysql_use_results mode for streaming
db_config = dict(
    host="localhost",
    user="kris",
    passwd="geheim",
    db="kris",
)

db = MySQLdb.connect(**db_config)


# Default is db.store_result(), which would buffer the
# result set in memory in the client. This won't work
# for a full table download, so we switch to streaming
# mode aka db.use_result(). That way we keep at most
# one result row in memory at any point in time.
db.use_result()

# Get a list of all tables in database
tables = db.cursor()
tables.execute("show tables")

# for each table, dump it to csv file
for t in tables:
    table = t[0]
    print(f"table = {table}")

    data = db.cursor()
    data.execute(f"select * from `{table}`")

    with open(f"{table}.csv", "w") as csvfile:
        w = csv.writer(csvfile)
        w.writerows(data)
