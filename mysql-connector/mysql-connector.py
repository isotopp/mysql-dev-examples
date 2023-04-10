#! /usr/bin/env python3

import mysql.connector

db_config = dict(
    host="127.0.0.1",
    user="kris",
    passwd="geheim",
    db="kris",
    # cursorclass=MySQLdb.cursors.DictCursor,
)

db = mysql.connector.connect(**db_config)
print(db)
db.close()