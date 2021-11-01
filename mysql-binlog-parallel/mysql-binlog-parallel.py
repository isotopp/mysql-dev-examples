#! /usr/bin/env python3

import re
from collections import defaultdict


class Transaction:
    """
    A transaction has a last_committed value (lc) and a sequence_number (sn).
    The sn is the unique identifier of the txn in a binlog file, starting at 1 for each logfile.
    The lc is the sn of the transaction this one is dependent on.
    """

    def __init__(self, lc: int, sn: int):
        """ Build a transaction represented by a lc/sn pair. """
        self.lc = lc
        self.sn = sn

    def __repr__(self):
        """ For debug, print the transaction as a sn/lc pair. """
        return f"T({self.sn}/{self.lc})"


class Schedule:
    """
    The schedule is the list of open transactions.
    We will add() transactions to the schedule,
    unless we find that the transaction we want to add is blocked by a previous open transaction.

    If that is the case, we commit() what we have. That will also update a number of statistics.

    On commit, we update the number of transactions (count) and the committed rows so far.
    sum/count is the average degree of parallelism.
    """

    def __init__(self):
        """
        open - list of open transactions
        sum  - committed row count
        count- commit count
        hist - a histogram of commit sizes
        """
        self.open = dict()
        self.sum = 0
        self.count = 0
        self.hist = defaultdict(int)

    def show_hist(self):
        for i in sorted(self.hist):
            print(f"{i}: {self.hist[i]}")

    def avg(self):
        return self.sum / self.count

    def max(self):
        return max(self.hist)

    def commit(self):
        self.sum += len(self.open)
        self.count += 1
        self.hist[len(self.open)] += 1
        if debug or incremental:
            print(f"Commit: {len(self.open)} {self.sum=} {self.count=} Avg={self.sum / self.count}")
        self.open = dict()

    def add(self, t: Transaction):
        wait_for = t.lc

        if self.open.get(wait_for, None) is not None:
            blocker = self.open[lc]
            if debug:
                print(f"{t=} is blocked by {blocker=}")
            self.commit()

        if debug:
            print(f"adding {t=}")
        self.open[t.sn] = t


# Set to true for debug output
debug = False
# Set to true for incremental commit averages
incremental = True

# Input logfile (mysqlbinlog -vvv blalog.000000 | grep "last_committed=" > binlog-grep.log)
the_filename: str = "binlog-grep.log"

# Regex to extract lc and sn
pattern = r"last_committed=(\d+).*sequence_number=(\d+)"

# A global list of open transactions
sched = Schedule()

i = 0
with open(the_filename, "r") as f:
    while (line := f.readline()) and i < 100:
        m = re.search(pattern, line)
        lc = int(m.group(1))
        sn = int(m.group(2))

        t = Transaction(lc, sn)
        sched.add(t)

        # i+= 1

sched.show_hist()
print(f"Avg = {sched.avg()}")
print(f"Max = {sched.max()}")
