#! /usr/bin/env python
# -*- coding: utf-8 -*-

# pip install mysqlclient (https://pypi.org/project/mysqlclient/)
import MySQLdb
import csv

# config here:

# table to load into
table = "data"

# column names to load into
columns = [
    "id",
    "d",
    "e",
]

# formatting options
delimiter = ","
quotechar = '"'

# commit every commit_interval lines
commit_interval = 1000

# connect to database, set mysql_use_results mode for streaming
db_config = dict(
    host="localhost",
    user="kris",
    passwd="geheim",
    db="kris",
)

db = MySQLdb.connect(**db_config)

# build a proper insert command
cmd = f"insert into {table} ( "
cmd += ", ".join(columns)
cmd += ") values ("
cmd += "%s," * len(columns)
cmd = cmd[:-1] + ")"
print(f"cmd = {cmd}")

with open(f"{table}.csv", "r") as csvfile:
    reader = csv.reader(csvfile, delimiter=delimiter, quotechar=quotechar)

    c = db.cursor()
    counter = 0

    # insert the rows as we read them
    for row in reader:
        c.execute(cmd, row)

        # ever commit_interval we issue a commit
        counter += 1
        if (counter % commit_interval) == 0:
            db.commit()

    # final commit to the remainder
    db.commit()
